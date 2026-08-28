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
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class InstrumentImportError(ValueError):
    def __init__(self, code: str, details=None):
        super().__init__(code)
        self.code = code
        self.details = details


def _text(node) -> str:
    return " ".join(filter(None, (part.text for part in node.iter(f"{NS}t")))).strip()


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
    errors = []
    warnings = []
    for required in ("DIMENSIONS", "ITEMS", "ITEM_SETTINGS", "SCALE_VALUES", "MATURITY_LEVELS"):
        if not tables.get(required):
            errors.append({"code": "required_table_missing", "table": required})
    dimensions = tables.get("DIMENSIONS", [])
    items = tables.get("ITEMS", [])
    settings = tables.get("ITEM_SETTINGS", [])
    dimension_codes = [row.get("dimension_code") or row.get("code") for row in dimensions]
    item_codes = [row.get("item_code") or row.get("code") for row in items]
    setting_codes = {row.get("item_code") or row.get("code") for row in settings}
    for label, values in (("dimension_code", dimension_codes), ("item_code", item_codes)):
        duplicates = sorted({value for value in values if value and values.count(value) > 1})
        if duplicates:
            errors.append({"code": "duplicate_codes", "field": label, "values": duplicates})
        if any(not value for value in values):
            errors.append({"code": "code_required", "field": label})
    known_dimensions = set(filter(None, dimension_codes))
    for index, item in enumerate(items, 1):
        item_code = item.get("item_code") or item.get("code")
        dimension_code = item.get("dimension_code") or item.get("dimension")
        prompt_ar = item.get("prompt_ar") or item.get("wording_ar") or item.get("prompt")
        construct = str(item.get("construct") or item.get("measure") or "").upper()
        if dimension_code not in known_dimensions:
            errors.append({"code": "unknown_dimension", "item": item_code, "dimension": dimension_code})
        if not prompt_ar:
            errors.append({"code": "arabic_prompt_required", "item": item_code or index})
        if construct not in {"MCM", "SMCE", "ENABLER", "OUTCOME"}:
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
    missing_optional = sorted(SUPPORTED_TABLES - set(tables))
    for table in missing_optional:
        if table not in {error.get("table") for error in errors}:
            warnings.append({"code": "optional_table_missing", "table": table})
    stats = {
        "filename": filename,
        "tables": len(tables),
        "dimensions": len(dimensions),
        "items": len(items),
        "mcm_items": sum(str(row.get("construct") or row.get("measure") or "").upper() == "MCM" for row in items),
        "smce_items": sum(str(row.get("construct") or row.get("measure") or "").upper() == "SMCE" for row in items),
    }
    return {"tables": tables, "errors": errors, "warnings": warnings, "stats": stats, "valid": not errors}
