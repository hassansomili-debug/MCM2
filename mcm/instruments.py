from __future__ import annotations

import base64
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from .config import MAX_DOCX_BYTES


SUPPORTED_TABLES = {
    "INSTRUMENT_METADATA",
    "SCALE_VALUES",
    "DIMENSIONS",
    "ITEMS",
    "ITEM_SETTINGS",
    "PROFILE_FIELDS",
    "MATURITY_LEVELS",
}
SUPPORTED_SCHEMAS = {"MCM_IMPORT_DOCX_1.1"}
CONSTRUCT_ALIASES = {
    "MCM": "MCM",
    "SMCE": "SMCE",
    "ENABLER": "ENABLER",
    "OUTCOME": "OUTCOME",
    "OPTIONAL_OUTCOME": "OUTCOME",
}
SCALE_RESPONSE_TYPES = {
    "LIKERT_5_EXTENT": "LIKERT_EXTENT",
    "RELATIVE_5_COMPETITOR": "LIKERT_RELATIVE",
}
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CANONICAL_MATURITY_LABELS_AR = (
    "عشوائي",
    "ناشئ",
    "متكامل",
    "استباقي ومتكيف",
    "مؤسسي وذكي",
)


class InstrumentImportError(ValueError):
    def __init__(self, code: str, details=None):
        super().__init__(code)
        self.code = code
        self.details = details


def _text(node) -> str:
    return "".join(part.text or "" for part in node.iter(f"{NS}t")).strip()


def _table(node) -> list[dict]:
    raw_rows = []
    for row in node.findall(f"{NS}tr"):
        values = [_text(cell) for cell in row.findall(f"{NS}tc")]
        if any(values):
            raw_rows.append(values)
    if not raw_rows:
        return []
    headers = [value.strip() for value in raw_rows.pop(0)]
    return [
        {header: (values[index].strip() if index < len(values) else "") for index, header in enumerate(headers) if header}
        for values in raw_rows
    ]


def _first(row: dict, *keys: str, default=""):
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return default


def _construct(value) -> str:
    raw = str(value or "").strip().upper()
    return CONSTRUCT_ALIASES.get(raw, raw)


def _metadata_rows(rows) -> list[dict]:
    if isinstance(rows, dict):
        return [dict(rows)]
    rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    if rows and all("key" in row and "value" in row for row in rows):
        return [{str(row["key"]).strip(): row.get("value", "") for row in rows if str(row["key"]).strip()}]
    return rows


def _provisional_bands(level_count: int) -> list[tuple[float, float]]:
    if level_count <= 0:
        return []
    step = 100.0 / level_count
    return [
        (round(index * step, 10), 100.01 if index == level_count - 1 else round((index + 1) * step, 10))
        for index in range(level_count)
    ]


def _normalize_tables(tables: dict) -> dict:
    """Map upload-package headers onto the platform's stable import aliases."""
    normalized = {
        name: [dict(row) for row in rows or [] if isinstance(row, dict)]
        for name, rows in tables.items()
        if name in SUPPORTED_TABLES and isinstance(rows, (list, tuple))
    }
    normalized["INSTRUMENT_METADATA"] = _metadata_rows(tables.get("INSTRUMENT_METADATA", []))

    for row in normalized.get("DIMENSIONS", []):
        source_construct = _first(row, "construct", "construct_type", "measure")
        row.update(
            code=_first(row, "code", "dimension_code"),
            construct=_construct(source_construct),
            name_ar=_first(row, "name_ar", "arabic_name", "name"),
            name_en=_first(row, "name_en", "english_name"),
            display_order=_first(row, "display_order", "sort_order", "order", default="0"),
        )
        if str(source_construct).strip().upper() == "OPTIONAL_OUTCOME":
            row["source_construct"] = "OPTIONAL_OUTCOME"

    for row in normalized.get("ITEMS", []):
        source_construct = _first(row, "construct", "construct_type", "measure")
        row.update(
            code=_first(row, "code", "item_code"),
            item_code=_first(row, "item_code", "code"),
            dimension_code=_first(row, "dimension_code", "dimension"),
            construct=_construct(source_construct),
            prompt_ar=_first(row, "prompt_ar", "arabic_item", "wording_ar", "prompt"),
            prompt_en=_first(row, "prompt_en", "english_item", "wording_en"),
            display_order=_first(row, "display_order", "sort_order", "order", default="0"),
        )
        if str(source_construct).strip().upper() == "OPTIONAL_OUTCOME":
            row["source_construct"] = "OPTIONAL_OUTCOME"

    scale_ranges: dict[str, tuple[float, float]] = {}
    for row in normalized.get("SCALE_VALUES", []):
        scale_code = str(_first(row, "scale_code", "scale")).strip()
        row["scale_code"] = scale_code
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        minimum, maximum = scale_ranges.get(scale_code, (value, value))
        scale_ranges[scale_code] = (min(minimum, value), max(maximum, value))

    for row in normalized.get("ITEM_SETTINGS", []):
        item_code = _first(row, "item_code", "code")
        scale_code = str(_first(row, "scale_code", "scale")).strip()
        response_type = str(_first(row, "response_type", default="LIKERT")).strip().upper()
        if response_type == "LIKERT" and scale_code in SCALE_RESPONSE_TYPES:
            response_type = SCALE_RESPONSE_TYPES[scale_code]
        row.update(item_code=item_code, code=item_code, scale_code=scale_code, response_type=response_type)
        if scale_code in scale_ranges:
            row.setdefault("min_value", scale_ranges[scale_code][0])
            row.setdefault("max_value", scale_ranges[scale_code][1])

    settings_by_code = {
        row.get("item_code"): row
        for row in normalized.get("ITEM_SETTINGS", [])
        if row.get("item_code")
    }
    for row in normalized.get("ITEMS", []):
        setting = settings_by_code.get(row.get("code"), {})
        source_type = _first(setting, "source_type", default=_first(row, "source_type"))
        source_reference = _first(setting, "source_reference", default=_first(row, "source_reference"))
        row.update(
            scale_code=setting.get("scale_code"),
            response_type=setting.get("response_type", row.get("response_type", "LIKERT")),
            source_type=source_type,
            source_reference=source_reference,
            source=":".join(filter(None, (str(source_type), str(source_reference)))) or None,
            lifecycle_status=_first(setting, "item_status", default=_first(row, "lifecycle_status", default="EXPERT_REVIEW")),
        )

    for row in normalized.get("PROFILE_FIELDS", []):
        row.update(
            code=_first(row, "code", "field_code"),
            construct=_construct(_first(row, "construct", "construct_type", default="CONTEXT")),
            label_ar=_first(row, "label_ar", "arabic_label", "label"),
            label_en=_first(row, "label_en", "english_label"),
        )

    levels = normalized.get("MATURITY_LEVELS", [])
    bands = _provisional_bands(len(levels))
    for index, row in enumerate(levels):
        source_minimum = _first(row, "min_score", "min")
        source_maximum = _first(row, "max_score", "max")
        source_label_ar = _first(row, "label_ar", "name_ar")
        threshold_status = str(_first(row, "threshold_status")).strip().upper()
        row.update(
            code=_first(row, "code", "level_code"),
            level_order=_first(row, "level_order", "level_number", "order", default=str(index + 1)),
            label_ar=(CANONICAL_MATURITY_LABELS_AR[index] if len(levels) == 5 else source_label_ar),
            label_en=_first(row, "label_en", "name_en"),
            source_label_ar=source_label_ar,
            threshold_status=threshold_status,
            source_min_score=source_minimum,
            source_max_score=source_maximum,
        )
        if not source_minimum and not source_maximum and threshold_status == "PROVISIONAL_LABEL_ONLY":
            row["min_score"], row["max_score"] = bands[index]
            row["provisional_threshold_applied"] = True
        else:
            row["min_score"] = source_minimum
            row["max_score"] = source_maximum
    return normalized


def parse_docx_base64(encoded: str, filename: str, mime_type: str | None = None) -> dict:
    if not filename.lower().endswith(".docx"):
        raise InstrumentImportError("docx_extension_required")
    allowed_mime = {
        None,
        "",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    }
    if mime_type not in allowed_mime:
        raise InstrumentImportError("unsupported_docx_mime")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise InstrumentImportError("invalid_base64") from exc
    if not payload or len(payload) > MAX_DOCX_BYTES:
        raise InstrumentImportError("docx_size_invalid", {"max_bytes": MAX_DOCX_BYTES})
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise InstrumentImportError("invalid_docx_archive") from exc
    names = archive.namelist()
    if any(name.startswith("/") or ".." in name.split("/") for name in names):
        raise InstrumentImportError("unsafe_docx_path")
    total_uncompressed = sum(info.file_size for info in archive.infolist())
    if total_uncompressed > MAX_DOCX_BYTES * 12:
        raise InstrumentImportError("docx_expansion_limit")
    try:
        document = archive.read("word/document.xml")
    except KeyError as exc:
        raise InstrumentImportError("docx_document_xml_missing") from exc
    if b"<!DOCTYPE" in document or b"<!ENTITY" in document:
        raise InstrumentImportError("unsafe_xml")
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise InstrumentImportError("invalid_document_xml") from exc
    body = root.find(f".//{NS}body")
    if body is None:
        raise InstrumentImportError("docx_body_missing")
    tables = {}
    children = list(body)
    for index, node in enumerate(children[:-1]):
        if node.tag != f"{NS}p":
            continue
        marker = re.fullmatch(r"TABLE:([A-Z0-9_]+)", _text(node))
        if not marker or marker.group(1) not in SUPPORTED_TABLES:
            continue
        next_node = children[index + 1]
        if next_node.tag == f"{NS}tbl":
            tables[marker.group(1)] = _table(next_node)
    return validate_tables(tables, filename=filename)


def validate_tables(tables: dict, filename: str = "instrument.docx") -> dict:
    if not isinstance(tables, dict):
        return {
            "tables": {},
            "errors": [{"code": "tables_object_required"}],
            "warnings": [],
            "stats": {"filename": filename, "tables": 0, "dimensions": 0, "items": 0},
            "valid": False,
        }
    tables = _normalize_tables(tables)
    errors = []
    warnings = []
    for required in ("DIMENSIONS", "ITEMS", "ITEM_SETTINGS", "SCALE_VALUES", "MATURITY_LEVELS"):
        if not tables.get(required):
            errors.append({"code": "required_table_missing", "table": required})

    metadata = (tables.get("INSTRUMENT_METADATA") or [{}])[0]
    schema_version = str(metadata.get("schema_version") or "").strip()
    if schema_version and schema_version not in SUPPORTED_SCHEMAS:
        errors.append({"code": "unsupported_schema_version", "value": schema_version})

    dimensions = tables.get("DIMENSIONS", [])
    items = tables.get("ITEMS", [])
    settings = tables.get("ITEM_SETTINGS", [])
    scales = tables.get("SCALE_VALUES", [])
    levels = tables.get("MATURITY_LEVELS", [])
    dimension_codes = [row.get("code") for row in dimensions]
    item_codes = [row.get("code") for row in items]
    raw_setting_codes = [row.get("item_code") or row.get("code") for row in settings]
    setting_codes = set(raw_setting_codes)
    for label, values in (("dimension_code", dimension_codes), ("item_code", item_codes)):
        duplicates = sorted({value for value in values if value and values.count(value) > 1})
        if duplicates:
            errors.append({"code": "duplicate_codes", "field": label, "values": duplicates})
        if any(not value for value in values):
            errors.append({"code": "code_required", "field": label})
    duplicate_settings = sorted({value for value in raw_setting_codes if value and raw_setting_codes.count(value) > 1})
    if duplicate_settings:
        errors.append({"code": "duplicate_codes", "field": "item_settings_code", "values": duplicate_settings})

    known_dimensions = set(filter(None, dimension_codes))
    known_scales = {row.get("scale_code") for row in scales if row.get("scale_code")}
    for dimension in dimensions:
        construct = str(dimension.get("construct") or "").upper()
        if construct not in CONSTRUCT_ALIASES.values():
            errors.append({"code": "invalid_construct", "dimension": dimension.get("code"), "construct": construct})
    for index, item in enumerate(items, 1):
        item_code = item.get("code")
        dimension_code = item.get("dimension_code")
        prompt_ar = item.get("prompt_ar")
        construct = str(item.get("construct") or "").upper()
        if dimension_code not in known_dimensions:
            errors.append({"code": "unknown_dimension", "item": item_code, "dimension": dimension_code})
        if not prompt_ar:
            errors.append({"code": "arabic_prompt_required", "item": item_code or index})
        if construct not in CONSTRUCT_ALIASES.values():
            errors.append({"code": "invalid_construct", "item": item_code, "construct": construct})
        if item_code and item_code not in setting_codes:
            errors.append({"code": "item_settings_missing", "item": item_code})

    for setting in settings:
        weight = setting.get("weight", "1")
        try:
            if float(weight) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append({"code": "invalid_weight", "item": setting.get("item_code"), "value": weight})
        reverse = str(setting.get("reverse_coded", "false")).lower()
        if reverse not in {"0", "1", "false", "true", "no", "yes"}:
            errors.append({"code": "invalid_reverse_flag", "item": setting.get("item_code")})
        scale_code = setting.get("scale_code")
        if not scale_code:
            errors.append({"code": "scale_code_required", "item": setting.get("item_code")})
        elif scale_code not in known_scales:
            errors.append({"code": "unknown_scale", "item": setting.get("item_code"), "scale": scale_code})

    orphan_settings = sorted(setting_codes - set(filter(None, item_codes)))
    if orphan_settings:
        warnings.append({"code": "orphan_item_settings", "items": orphan_settings})

    scale_values: dict[str, list[float]] = {}
    for row in scales:
        scale_code = row.get("scale_code")
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            errors.append({"code": "invalid_scale_value", "scale": scale_code, "value": row.get("value")})
            continue
        scale_values.setdefault(scale_code, []).append(value)
    for scale_code, values in scale_values.items():
        if len(values) != len(set(values)):
            errors.append({"code": "duplicate_scale_values", "scale": scale_code})

    for index, level in enumerate(levels, 1):
        if level.get("provisional_threshold_applied"):
            warnings.append(
                {
                    "code": "provisional_maturity_thresholds_applied",
                    "level": level.get("code"),
                    "source_thresholds": "blank",
                }
            )
        try:
            minimum = float(level.get("min_score"))
            maximum = float(level.get("max_score"))
            if minimum >= maximum:
                raise ValueError
        except (TypeError, ValueError):
            errors.append({"code": "invalid_maturity_threshold", "row": index, "level": level.get("code")})

    expected_total = metadata.get("total_item_count")
    if str(expected_total).strip():
        try:
            if int(expected_total) != len(items):
                errors.append({"code": "total_item_count_mismatch", "expected": int(expected_total), "actual": len(items)})
        except (TypeError, ValueError):
            errors.append({"code": "invalid_total_item_count", "value": expected_total})
    core_count = sum(row.get("construct") in {"MCM", "SMCE"} for row in items)
    expected_core = metadata.get("core_item_count")
    if str(expected_core).strip():
        try:
            if int(expected_core) != core_count:
                errors.append({"code": "core_item_count_mismatch", "expected": int(expected_core), "actual": core_count})
        except (TypeError, ValueError):
            errors.append({"code": "invalid_core_item_count", "value": expected_core})

    missing_optional = sorted(SUPPORTED_TABLES - set(tables))
    for table in missing_optional:
        if table not in {error.get("table") for error in errors}:
            warnings.append({"code": "optional_table_missing", "table": table})
    stats = {
        "filename": filename,
        "tables": len(tables),
        "dimensions": len(dimensions),
        "items": len(items),
        "mcm_items": sum(row.get("construct") == "MCM" for row in items),
        "smce_items": sum(row.get("construct") == "SMCE" for row in items),
        "enabler_items": sum(row.get("construct") == "ENABLER" for row in items),
        "outcome_items": sum(row.get("construct") == "OUTCOME" for row in items),
        "core_items": core_count,
        "schema_version": schema_version or None,
        "instrument_version": metadata.get("version") or metadata.get("instrument_version"),
    }
    return {"tables": tables, "errors": errors, "warnings": warnings, "stats": stats, "valid": not errors}
