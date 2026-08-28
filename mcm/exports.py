from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from .database import assessment_research_eligible
from .scoring import diagnostic_payload, priority_payload, score_payload


def _safe_text(value) -> str:
    # Keep actual numeric values numeric-looking for statistical imports. Only
    # user-provided strings need spreadsheet-formula injection protection.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_safe_text(value) for value in row])
    return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_xml(headers: list[str], rows: list[list]) -> str:
    def cell(value, row_number, column_number, style=0):
        ref = f"{_column_name(column_number)}{row_number}"
        if value is None or value == "":
            return f'<c r="{ref}" s="{style}"/>'
        if isinstance(value, bool):
            return f'<c r="{ref}" s="{style}" t="b"><v>{1 if value else 0}</v></c>'
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
        return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(_safe_text(value))}</t></is></c>'

    all_rows = [headers] + rows
    rendered = []
    for row_number, values in enumerate(all_rows, 1):
        style = 1 if row_number == 1 else 0
        cells = "".join(cell(value, row_number, column_number, style) for column_number, value in enumerate(values, 1))
        rendered.append(f'<row r="{row_number}">{cells}</row>')
    width_defs = "".join(f'<col min="{index}" max="{index}" width="{min(48, max(12, len(str(header)) + 4))}" customWidth="1"/>' for index, header in enumerate(headers, 1))
    max_ref = f"{_column_name(max(1, len(headers)))}{max(1, len(all_rows))}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{max_ref}"/><sheetViews><sheetView workbookViewId="0" rightToLeft="1"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{width_defs}</cols><sheetData>{"".join(rendered)}</sheetData><autoFilter ref="A1:{_column_name(max(1, len(headers)))}1"/>'
        '</worksheet>'
    )


def xlsx_bytes(sheets: OrderedDict[str, tuple[list[str], list[list]]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{overrides}</Types>",
        )
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        workbook_sheets = "".join(f'<sheet name="{escape(name[:31])}" sheetId="{index}" r:id="rId{index}"/>' for index, name in enumerate(sheets, 1))
        archive.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>{workbook_sheets}</sheets></workbook>')
        relationships = "".join(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>' for index in range(1, len(sheets) + 1))
        relationships += f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        archive.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relationships}</Relationships>')
        archive.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0B1F33"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs></styleSheet>')
        for index, (_, (headers, rows)) in enumerate(sheets.items(), 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(headers, rows))
    return output.getvalue()


def _origin_filter(origin: str) -> tuple[str, tuple]:
    normalized = str(origin or "REAL").upper()
    if normalized in {"REAL", "SYNTHETIC", "DEMO", "TEST"}:
        return "a.data_origin=?", (normalized,)
    if normalized == "DEMO_TEST":
        return "a.data_origin IN ('DEMO','TEST')", ()
    if normalized == "ALL":
        return "1=1", ()
    return "a.data_origin='REAL'", ()


def build_research_sheets(db, origin: str = "REAL") -> OrderedDict:
    where, params = _origin_filter(origin)
    assessments = db.execute(
        f"""SELECT a.id,a.organization_id,a.version_id,a.status,a.data_origin,a.completed_at,v.version,
                   o.sector,o.size,o.region,cp.business_model,cp.research_consent
            FROM assessments a JOIN instrument_versions v ON v.id=a.version_id JOIN organizations o ON o.id=a.organization_id
            LEFT JOIN company_profiles cp ON cp.organization_id=o.id
            WHERE a.status='COMPLETED' AND {where} ORDER BY a.id""",
        params,
    ).fetchall()
    assessments = [
        row for row in assessments
        if row["data_origin"] != "REAL" or assessment_research_eligible(db, row["id"])
    ]
    assessment_ids = [row["id"] for row in assessments]
    long_headers = ["PARTICIPANT_ID", "ORG_ID", "ASSESSMENT_ID", "DATA_ORIGIN", "INSTRUMENT_VERSION", "ITEM_CODE", "CONSTRUCT", "DIMENSION", "RESPONSE", "MISSING_TYPE", "COMPLETED_AT"]
    long_rows = []
    wide_map = {}
    item_codes = []
    if assessment_ids:
        placeholders = ",".join("?" for _ in assessment_ids)
        response_rows = db.execute(
            f"""SELECT r.assessment_id,r.participant_id,r.numeric_value,r.text_value,r.missing_type,i.code,i.construct,i.dimension_code,a.organization_id,a.data_origin,a.completed_at,v.version
                FROM responses r JOIN items i ON i.id=r.item_id JOIN assessments a ON a.id=r.assessment_id JOIN instrument_versions v ON v.id=a.version_id
                WHERE r.assessment_id IN ({placeholders}) ORDER BY r.assessment_id,r.participant_id,i.sort_order,i.id""",
            tuple(assessment_ids),
        ).fetchall()
        for row in response_rows:
            participant = f"P{int(row['participant_id'] or 0):06d}"
            org = f"ORG{int(row['organization_id']):06d}"
            value = row["numeric_value"] if row["numeric_value"] is not None else row["text_value"]
            long_rows.append([participant, org, row["assessment_id"], row["data_origin"], row["version"], row["code"], row["construct"], row["dimension_code"], value, row["missing_type"], row["completed_at"]])
            key = (row["assessment_id"], participant, org, row["data_origin"], row["version"], row["completed_at"])
            wide_map.setdefault(key, {})[row["code"]] = value
            wide_map[key][row["code"] + "_MISS"] = row["missing_type"]
            if row["code"] not in item_codes:
                item_codes.append(row["code"])
    wide_base_headers = [
        "ASSESSMENT_ID", "PARTICIPANT_ID", "ORG_ID", "DATA_ORIGIN", "INSTRUMENT_VERSION", "COMPLETED_AT",
        "SECTOR", "FIRM_SIZE", "FIRM_SIZE_CODE", "FIRM_AGE_YEARS", "REGION", "SOCIAL_PLATFORM_COUNT",
        "RESPONDENT_ROLE", "LEADERSHIP_SUPPORT", "HUMAN_COMPETENCIES", "TECHNOLOGY_INFRASTRUCTURE",
        "DATA_READINESS", "MCM_TOTAL", "SMCE_TOTAL", "EFFICIENCY_MINUS_MATURITY", "MATURITY_LEVEL",
        "MATURITY_LEVEL_ORDER",
    ]
    wide_headers = list(wide_base_headers)
    for code in item_codes:
        wide_headers.extend([code, code + "_MISS"])
    contexts = {
        row["assessment_id"]: dict(row)
        for row in db.execute(
            f"SELECT * FROM assessment_context WHERE assessment_id IN ({','.join('?' for _ in assessment_ids)})",
            tuple(assessment_ids),
        ).fetchall()
    } if assessment_ids else {}
    score_summaries = {}
    dimension_summaries = {}
    for assessment in assessments:
        totals = {score["construct"]: dict(score) for score in db.execute(
            """SELECT s.*,m.code AS level_code,m.label_ar,m.label_en,m.level_order
               FROM assessment_scores s LEFT JOIN maturity_levels m ON m.id=s.maturity_level_id
               WHERE s.assessment_id=?""",
            (assessment["id"],),
        )}
        mcm_total = totals.get("MCM", {}).get("total_score")
        smce_total = totals.get("SMCE", {}).get("total_score")
        score_summaries[assessment["id"]] = {
            "mcm": mcm_total,
            "smce": smce_total,
            "gap": round(float(smce_total) - float(mcm_total), 2) if mcm_total is not None and smce_total is not None else None,
            "level": totals.get("MCM", {}).get("level_code"),
            "level_order": totals.get("MCM", {}).get("level_order"),
        }
        dimension_summaries[assessment["id"]] = {
            row["dimension_code"]: row["score"]
            for row in db.execute("SELECT dimension_code,score FROM dimension_scores WHERE assessment_id=?", (assessment["id"],))
        }
    wide_rows = []
    for key, values in wide_map.items():
        assessment_id, participant, org, data_origin, version, completed_at = key
        assessment_row = next(row for row in assessments if row["id"] == assessment_id)
        context = contexts.get(assessment_id, {})
        summary = score_summaries.get(assessment_id, {})
        size = context.get("firm_size") or assessment_row["size"]
        base = [
            assessment_id, participant, org, data_origin, version, completed_at,
            context.get("sector") or assessment_row["sector"], size, {"MICRO": 1, "SMALL": 2, "MEDIUM": 3}.get(size),
            context.get("firm_age_years"), context.get("region") or assessment_row["region"], context.get("social_platform_count"),
            context.get("respondent_role"), context.get("leadership_support"), context.get("human_competencies"),
            context.get("technology_infrastructure"), context.get("data_readiness"), summary.get("mcm"), summary.get("smce"),
            summary.get("gap"), summary.get("level"), summary.get("level_order"),
        ]
        wide_rows.append(base + [values.get(header) for header in wide_headers[len(wide_base_headers):]])
    mcm_score_headers = ["ASSESSMENT_ID", "ORG_ID", "MCM_TOTAL", "MATURITY_LEVEL", "MATURITY_LEVEL_ORDER"] + [f"MCM{i:02d}" for i in range(1, 8)] + ["SMCE_TOTAL", "EFFICIENCY_MINUS_MATURITY", "INSTRUMENT_VERSION", "DATA_ORIGIN", "COMPLETED_AT"]
    smce_score_headers = ["ASSESSMENT_ID", "ORG_ID", "SMCE_TOTAL"] + [f"SMCE{i:02d}" for i in range(1, 6)] + ["MCM_TOTAL", "EFFICIENCY_MINUS_MATURITY", "INSTRUMENT_VERSION", "DATA_ORIGIN", "COMPLETED_AT"]
    mcm_rows, smce_rows = [], []
    profiles = []
    for row in assessments:
        base = [row["id"], f"ORG{int(row['organization_id']):06d}"]
        summary = score_summaries.get(row["id"], {})
        dimensions = dimension_summaries.get(row["id"], {})
        mcm_rows.append(base + [summary.get("mcm"), summary.get("level"), summary.get("level_order")] + [dimensions.get(f"MCM{i:02d}") for i in range(1, 8)] + [summary.get("smce"), summary.get("gap"), row["version"], row["data_origin"], row["completed_at"]])
        smce_rows.append(base + [summary.get("smce")] + [dimensions.get(f"SMCE{i:02d}") for i in range(1, 6)] + [summary.get("mcm"), summary.get("gap"), row["version"], row["data_origin"], row["completed_at"]])
        context = contexts.get(row["id"], {})
        size = context.get("firm_size") or row["size"]
        profiles.append([
            row["id"], f"ORG{int(row['organization_id']):06d}", context.get("sector") or row["sector"], size,
            {"MICRO": 1, "SMALL": 2, "MEDIUM": 3}.get(size), context.get("firm_age_years"),
            context.get("region") or row["region"], context.get("social_platform_count"), context.get("respondent_role"),
            context.get("leadership_support"), context.get("human_competencies"), context.get("technology_infrastructure"),
            context.get("data_readiness"), row["business_model"], row["data_origin"],
        ])
    versions = sorted({row["version_id"] for row in assessments})
    if not versions:
        latest = db.execute("SELECT id FROM instrument_versions ORDER BY id DESC LIMIT 1").fetchone()
        versions = [latest["id"]] if latest else []
    instrument_rows = []
    codebook_rows = []
    value_label_rows = []
    for version_id in versions:
        for row in db.execute("SELECT i.*,v.version FROM items i JOIN instrument_versions v ON v.id=i.version_id WHERE i.version_id=? ORDER BY i.sort_order,i.id", (version_id,)):
            instrument_rows.append([row["version"], row["code"], row["construct"], row["dimension_code"], row["prompt_ar"], row["prompt_en"], row["required"], row["reverse_coded"], row["weight"], row["response_type"], row["min_value"], row["max_value"], row["lifecycle_status"], row["source"]])
            codebook_rows.append([row["code"], row["prompt_ar"], row["prompt_en"], row["construct"], row["dimension_code"], row["response_type"], f"{row['min_value']}-{row['max_value']}", "NOT_ANSWERED|NOT_APPLICABLE|SKIPPED|TECHNICAL_MISSING", row["reverse_coded"], row["source"], row["version"]])
        value_label_rows.extend([["LIKERT_1_5", value, ar, en] for value, ar, en in [(1, "لا أوافق بشدة", "Strongly disagree"), (2, "لا أوافق", "Disagree"), (3, "محايد", "Neutral"), (4, "أوافق", "Agree"), (5, "أوافق بشدة", "Strongly agree")]])
    value_label_rows.extend([
        ["FIRM_SIZE_CODE", 1, "متناهية الصغر", "Micro"], ["FIRM_SIZE_CODE", 2, "صغيرة", "Small"], ["FIRM_SIZE_CODE", 3, "متوسطة", "Medium"],
        ["MATURITY_LEVEL_ORDER", 1, "تفاعلي", "Reactive"], ["MATURITY_LEVEL_ORDER", 2, "مستجيب", "Responsive"],
        ["MATURITY_LEVEL_ORDER", 3, "مُدار ومتكامل", "Managed & Integrated"], ["MATURITY_LEVEL_ORDER", 4, "استباقي ومتكيّف", "Proactive & Adaptive"],
        ["MATURITY_LEVEL_ORDER", 5, "مؤسسي وذكي", "Institutionalised & Intelligent"],
    ])
    metadata_labels = {
        "ASSESSMENT_ID": ("معرف التقييم", "Assessment identifier"), "PARTICIPANT_ID": ("معرف المشارك المجهول", "Anonymous participant identifier"),
        "ORG_ID": ("معرف المنشأة المجهول", "Anonymous organisation identifier"), "DATA_ORIGIN": ("مصدر البيانات", "Data origin"),
        "INSTRUMENT_VERSION": ("إصدار الأداة", "Instrument version"), "COMPLETED_AT": ("وقت الإكمال", "Completion timestamp"),
        "SECTOR": ("قطاع المنشأة", "Firm sector"), "FIRM_SIZE": ("حجم المنشأة", "Firm size"), "FIRM_SIZE_CODE": ("رمز حجم المنشأة", "Firm size code"),
        "FIRM_AGE_YEARS": ("عمر المنشأة بالسنوات", "Firm age in years"), "REGION": ("المنطقة", "Region"),
        "SOCIAL_PLATFORM_COUNT": ("عدد منصات التواصل المستخدمة", "Number of social media platforms"), "RESPONDENT_ROLE": ("دور المجيب", "Respondent role"),
        "LEADERSHIP_SUPPORT": ("دعم القيادة", "Leadership support"), "HUMAN_COMPETENCIES": ("الكفاءات البشرية", "Human competencies"),
        "TECHNOLOGY_INFRASTRUCTURE": ("البنية التحتية التقنية", "Technology infrastructure"), "DATA_READINESS": ("جاهزية البيانات", "Data readiness"),
        "MCM_TOTAL": ("الدرجة الكلية للنضج الاتصالي التسويقي", "Marketing communication maturity total"),
        "SMCE_TOTAL": ("الدرجة الكلية للكفاءة الاتصالية", "Social media communication efficiency total"),
        "EFFICIENCY_MINUS_MATURITY": ("فارق الكفاءة ناقص النضج", "Efficiency minus maturity gap"),
        "MATURITY_LEVEL": ("تصنيف مرحلة النضج", "Maturity stage classification"), "MATURITY_LEVEL_ORDER": ("ترتيب مرحلة النضج", "Maturity stage order"),
    }
    existing_variables = {row[0] for row in codebook_rows}
    for variable, (label_ar, label_en) in metadata_labels.items():
        if variable not in existing_variables:
            codebook_rows.insert(0, [variable, label_ar, label_en, "CONTEXT" if variable not in {"MCM_TOTAL", "SMCE_TOTAL", "EFFICIENCY_MINUS_MATURITY", "MATURITY_LEVEL", "MATURITY_LEVEL_ORDER"} else "SCORE", "", "NUMERIC_OR_STRING", "", "SYSTEM_MISSING", 0, "System-derived or participant demographics", "all"])
    generated = datetime.now(timezone.utc).isoformat()
    return OrderedDict([
        ("01_RESPONSES_WIDE", (wide_headers, wide_rows)),
        ("02_RESPONSES_LONG", (long_headers, long_rows)),
        ("03_MCM_SCORES", (mcm_score_headers, mcm_rows)),
        ("04_SMCE_SCORES", (smce_score_headers, smce_rows)),
        ("05_COMPANY_PROFILE", (["ASSESSMENT_ID", "ORG_ID", "SECTOR", "FIRM_SIZE", "FIRM_SIZE_CODE", "FIRM_AGE_YEARS", "REGION", "SOCIAL_PLATFORM_COUNT", "RESPONDENT_ROLE", "LEADERSHIP_SUPPORT", "HUMAN_COMPETENCIES", "TECHNOLOGY_INFRASTRUCTURE", "DATA_READINESS", "BUSINESS_MODEL", "DATA_ORIGIN"], profiles)),
        ("06_CODEBOOK", (["VARIABLE_NAME", "LABEL_AR", "LABEL_EN", "CONSTRUCT", "DIMENSION", "RESPONSE_TYPE", "VALUES", "MISSING_VALUES", "REVERSE_CODED", "SOURCE", "INSTRUMENT_VERSION"], codebook_rows)),
        ("07_VARIABLE_LABELS", (["VARIABLE_NAME", "VARIABLE_LABEL_AR", "VARIABLE_LABEL_EN"], [[row[0], row[1], row[2]] for row in codebook_rows])),
        ("08_VALUE_LABELS", (["VARIABLE_GROUP", "VALUE", "LABEL_AR", "LABEL_EN"], value_label_rows)),
        ("09_INSTRUMENT", (["VERSION", "ITEM_CODE", "CONSTRUCT", "DIMENSION", "PROMPT_AR", "PROMPT_EN", "REQUIRED", "REVERSE_CODED", "WEIGHT", "RESPONSE_TYPE", "MIN", "MAX", "STATUS", "SOURCE"], instrument_rows)),
        ("10_METADATA", (["KEY", "VALUE"], [["generated_at", generated], ["data_origin_filter", str(origin or "REAL").upper()], ["pii_included", False], ["case_count", len(assessments)], ["scoring_method", "MCM_DETERMINISTIC_1.0"], ["relationship_model", "MCM -> SMCE proposed positive effect"], ["notice", "Provisional diagnostic instrument; quantitative validation required"]])),
    ])


def research_workbook(db, origin: str = "REAL") -> bytes:
    return xlsx_bytes(build_research_sheets(db, origin))


def spss_package(db, origin: str = "REAL") -> bytes:
    sheets = build_research_sheets(db, origin)
    wide_headers, wide_rows = sheets["01_RESPONSES_WIDE"]
    code_headers, code_rows = sheets["06_CODEBOOK"]
    label_headers, label_rows = sheets["07_VARIABLE_LABELS"]
    value_headers, value_rows = sheets["08_VALUE_LABELS"]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dataset.csv", csv_bytes(wide_headers, wide_rows))
        archive.writestr("dataset.xlsx", xlsx_bytes(OrderedDict([("SPSS_DATA", (wide_headers, wide_rows))])))
        archive.writestr("codebook.xlsx", xlsx_bytes(OrderedDict([("CODEBOOK", (code_headers, code_rows))])))
        archive.writestr("labels.xlsx", xlsx_bytes(OrderedDict([("VARIABLE_LABELS", (label_headers, label_rows))])))
        archive.writestr("value_labels.xlsx", xlsx_bytes(OrderedDict([("VALUE_LABELS", (value_headers, value_rows))])))
        variable_names = [re.sub(r"[^A-Za-z0-9_]", "_", header.upper())[:64] for header in wide_headers]
        numeric_exact = {
            "ASSESSMENT_ID", "COMPLETED_AT", "FIRM_SIZE_CODE", "FIRM_AGE_YEARS", "SOCIAL_PLATFORM_COUNT",
            "LEADERSHIP_SUPPORT", "HUMAN_COMPETENCIES", "TECHNOLOGY_INFRASTRUCTURE", "DATA_READINESS",
            "MCM_TOTAL", "SMCE_TOTAL", "EFFICIENCY_MINUS_MATURITY", "MATURITY_LEVEL_ORDER",
        }
        numeric_variables = [
            name for header, name in zip(wide_headers, variable_names)
            if header in numeric_exact or bool(re.fullmatch(r"(?:MCM|SMCE|ENA|OUT)\d{2}_\d{2}", header))
        ]
        definitions = []
        for header, name in zip(wide_headers, variable_names):
            definitions.append(f"{name} F12.2" if name in numeric_variables else f"{name} A255")
        label_lookup = {str(row[0]): str(row[2] or row[1] or row[0]) for row in label_rows}
        label_lines = []
        for header, name in zip(wide_headers, variable_names):
            label = label_lookup.get(header, header).replace("'", "''")[:240]
            label_lines.append(f" {name} '{label}'")
        likert_variables = [name for name in numeric_variables if re.fullmatch(r"(?:MCM|SMCE|ENA|OUT)\d{2}_\d{2}", name)]
        likert_variables.extend([name for name in ("LEADERSHIP_SUPPORT", "HUMAN_COMPETENCIES", "TECHNOLOGY_INFRASTRUCTURE", "DATA_READINESS") if name in variable_names])
        value_label_syntax = ""
        if likert_variables:
            value_label_syntax += f"VALUE LABELS {' '.join(likert_variables)} 1 'Strongly disagree' 2 'Disagree' 3 'Neutral' 4 'Agree' 5 'Strongly agree'.\n"
        if "FIRM_SIZE_CODE" in variable_names:
            value_label_syntax += "VALUE LABELS FIRM_SIZE_CODE 1 'Micro' 2 'Small' 3 'Medium'.\n"
        if "MATURITY_LEVEL_ORDER" in variable_names:
            value_label_syntax += "VALUE LABELS MATURITY_LEVEL_ORDER 1 'Reactive' 2 'Responsive' 3 'Managed and Integrated' 4 'Proactive and Adaptive' 5 'Institutionalised and Intelligent'.\n"
        labels_block = "\n".join(label_lines)
        syntax = (
            "* Marketing Communication Maturity Scale - SPSS import package.\n"
            "GET DATA /TYPE=TXT /FILE='dataset.csv' /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=',' /QUALIFIER='\"' /ARRANGEMENT=DELIMITED /FIRSTCASE=2\n"
            f" /VARIABLES={' '.join(definitions)}.\n"
            f"VARIABLE LABELS\n{labels_block}.\n"
            f"{value_label_syntax}"
            f"VARIABLE LEVEL ({' '.join(numeric_variables)}) (SCALE).\n"
            "EXECUTE.\n"
            "* Missing-reason variables use suffix _MISS and preserve explicit missing states.\n"
        )
        archive.writestr("import.sps", syntax.encode("utf-8"))
        archive.writestr("README.txt", "Marketing Communication Maturity Scale - SPSS package\nOpen import.sps in SPSS, or import dataset.xlsx directly. Variables use ASCII-compatible names, numeric Likert values, explicit value labels, a codebook, and no direct identifiers.\nMCM and SMCE are separate constructs; their proposed relationship is provisional and not a causal result.\n".encode("utf-8"))
    return output.getvalue()


def _pdf_escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 86) -> list[str]:
    words = str(text).split()
    lines, current = [], []
    for word in words:
        if sum(len(part) + 1 for part in current) + len(word) > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def _pdf_document(streams: list[str]) -> bytes:
    objects: list[bytes] = []

    def add(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    content_ids = []
    for commands in streams:
        stream = commands.encode("latin-1", "replace")
        content_ids.append(add(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"))
    page_ids = []
    pages_id = len(objects) + len(streams) + 1
    for content_id in content_ids:
        page_ids.append(add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R /F2 {bold_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()))
    actual_pages_id = add(f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(str(page_id) + ' 0 R' for page_id in page_ids)}] >>".encode())
    if actual_pages_id != pages_id:
        raise RuntimeError("pdf_object_order_error")
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode())
        output.write(obj)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(f"trailer << /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return output.getvalue()


def _pdf_text(x: float, y: float, text: str, size: float = 10, bold: bool = False, color=(0.07, 0.15, 0.28)) -> str:
    font = "F2" if bold else "F1"
    clean = str(text).encode("latin-1", "replace").decode("latin-1")
    return f"BT {color[0]} {color[1]} {color[2]} rg /{font} {size} Tf {x} {y} Td ({_pdf_escape(clean)}) Tj ET"


def _pdf_rect(x: float, y: float, width: float, height: float, color) -> str:
    return f"{color[0]} {color[1]} {color[2]} rg {x} {y} {width} {height} re f"


def _pdf_bar(x: float, y: float, width: float, score: float, color) -> list[str]:
    bounded = max(0.0, min(100.0, float(score or 0)))
    return [_pdf_rect(x, y, width, 8, (0.89, 0.92, 0.94)), _pdf_rect(x, y, width * bounded / 100, 8, color)]


def _report_header(title: str, subtitle: str) -> list[str]:
    return [
        _pdf_rect(0, 0, 595, 842, (0.97, 0.98, 0.99)),
        _pdf_rect(0, 730, 595, 112, (0.035, 0.14, 0.29)),
        _pdf_rect(0, 724, 595, 6, (0.0, 0.55, 0.53)),
        _pdf_text(42, 792, title, 20, True, (1, 1, 1)),
        _pdf_text(42, 765, subtitle, 10, False, (0.78, 0.9, 0.96)),
        _pdf_text(500, 792, "MCM", 18, True, (0.28, 0.9, 0.84)),
    ]


def assessment_pdf(db, assessment_id: int, detailed: bool = False) -> bytes:
    result = score_payload(db, assessment_id)
    diagnostic = diagnostic_payload(db, assessment_id)
    priorities = priority_payload(db, assessment_id)
    roadmap = [dict(row) for row in db.execute("SELECT * FROM roadmap_items WHERE assessment_id=? ORDER BY sort_order", (assessment_id,))]
    mcm = result["scores"]["MCM"]
    smce = result["scores"]["SMCE"]
    mcm_total = float(mcm.get("total") or 0)
    smce_total = float(smce.get("total") or 0)
    relationship = result.get("relationship") or {}
    level = (mcm.get("maturity_level") or {}).get("label_en") or "Not classified"
    level_order = int((mcm.get("maturity_level") or {}).get("order") or 0)

    page_one = _report_header("Marketing Communication Maturity Scale", f"Executive diagnostic report | Assessment {assessment_id} | Instrument {result['instrument_version']}")
    cards = [
        (42, "MCM maturity", f"{mcm_total:.1f}", (0.035, 0.14, 0.29)),
        (224, "SMCE efficiency", f"{smce_total:.1f}", (0.0, 0.47, 0.47)),
        (406, "Efficiency - maturity", f"{float(relationship.get('efficiency_minus_maturity') or 0):+.1f}", (0.16, 0.39, 0.62)),
    ]
    for x, label, value, color in cards:
        page_one.extend([_pdf_rect(x, 603, 147, 88, (1, 1, 1)), _pdf_rect(x, 603, 7, 88, color), _pdf_text(x + 17, 659, label, 9, False, (0.28, 0.35, 0.42)), _pdf_text(x + 17, 623, value, 24, True, color)])
    page_one.extend([_pdf_text(42, 568, "Five-stage maturity progression", 13, True), _pdf_text(42, 548, f"Current classification: {level}", 10, False, (0.0, 0.47, 0.47))])
    stage_names = [("Reactive", ""), ("Responsive", ""), ("Managed &", "Integrated"), ("Proactive &", "Adaptive"), ("Institutionalised &", "Intelligent")]
    for index, (first, second) in enumerate(stage_names, 1):
        x = 42 + (index - 1) * 103
        active = index == level_order
        fill = (0.0, 0.47, 0.47) if active else (0.9, 0.93, 0.95)
        text_color = (1, 1, 1) if active else (0.12, 0.22, 0.34)
        page_one.extend([_pdf_rect(x, 478, 92, 55, fill), _pdf_text(x + 8, 507, first, 7.3, True, text_color)])
        if second:
            page_one.append(_pdf_text(x + 8, 492, second, 7.3, True, text_color))
        page_one.append(_pdf_text(x + 76, 515, str(index), 8, True, text_color))
    page_one.extend([
        _pdf_rect(42, 360, 511, 86, (0.91, 0.97, 0.97)),
        _pdf_text(57, 417, "Proposed MCM -> SMCE relationship", 12, True, (0.0, 0.4, 0.4)),
        _pdf_text(57, 394, str(relationship.get("alignment_code") or "NOT_AVAILABLE").replace("_", " ").title(), 10, True),
        _pdf_text(57, 374, "MCM is a higher-order capability; SMCE is a downstream communication outcome.", 8.5),
        _pdf_text(42, 321, "Interpretation boundary", 12, True),
        _pdf_text(42, 299, "Provisional diagnostic classification. The proposed association is not a causal or validated claim.", 9, False, (0.55, 0.25, 0.12)),
        _pdf_text(42, 278, "Context and enabling conditions are retained separately from the MCM score denominator.", 9),
        _pdf_text(42, 54, "Generated without direct participant identifiers", 8, False, (0.4, 0.45, 0.5)),
    ])

    page_two = _report_header("Capability and efficiency profile", "Seven MCM dimensions and five SMCE outcomes | 0-100 normalized scores")
    navy, teal = (0.035, 0.14, 0.29), (0.0, 0.47, 0.47)
    page_two.extend([_pdf_text(42, 690, "Marketing Communication Maturity (MCM)", 13, True, navy), _pdf_text(315, 690, "Social Media Communication Efficiency (SMCE)", 11, True, teal)])
    for index, row in enumerate(mcm["dimensions"]):
        y = 645 - index * 70
        page_two.extend([_pdf_text(42, y + 22, f"{row['code']}  {row['name_en']}", 8.2, True), _pdf_text(264, y + 22, f"{float(row['score']):.1f}", 8.5, True, navy)])
        page_two.extend(_pdf_bar(42, y, 245, row["score"], navy))
    for index, row in enumerate(smce["dimensions"]):
        y = 645 - index * 86
        page_two.extend([_pdf_text(315, y + 22, f"{row['code']}  {row['name_en']}", 7.7, True), _pdf_text(528, y + 22, f"{float(row['score']):.1f}", 8.5, True, teal)])
        page_two.extend(_pdf_bar(315, y, 238, row["score"], teal))
    page_two.extend([_pdf_text(42, 118, "Reading the chart", 11, True), _pdf_text(42, 96, "Longer bars indicate stronger observed capability or efficiency. MCM and SMCE remain separately scored.", 8.5), _pdf_text(42, 54, "Deterministic server-side calculation | Missing answers are never converted to zero", 8, False, (0.4, 0.45, 0.5))])

    page_three = _report_header("Priority action plan", "Evidence-linked recommendations and staged implementation roadmap")
    page_three.append(_pdf_text(42, 690, "Top development priorities", 13, True))
    priority_rows = priorities["priorities"][:5]
    if not priority_rows:
        page_three.append(_pdf_text(42, 660, "No materialised priorities were generated.", 10))
    for index, row in enumerate(priority_rows):
        y = 625 - index * 78
        page_three.extend([_pdf_rect(42, y, 511, 58, (1, 1, 1)), _pdf_rect(42, y, 8, 58, teal if index < 2 else navy), _pdf_text(62, y + 35, f"Priority {row['rank']} | {row['dimension_code']} | current {float(row.get('current_score') or 0):.1f}", 10, True), _pdf_text(62, y + 16, f"Gap to target: {float(row.get('gap') or 0):.1f} | owner and KPI available in the platform roadmap", 8.5)])
    page_three.append(_pdf_text(42, 202, "Implementation horizons", 12, True))
    horizon_counts = {key: sum(1 for item in roadmap if item.get("horizon") == key) for key in ("0-30", "31-90", "3-6")}
    for index, (horizon, label) in enumerate((("0-30", "First 30 days"), ("31-90", "Days 31-90"), ("3-6", "Months 3-6"))):
        x = 42 + index * 171
        page_three.extend([_pdf_rect(x, 112, 154, 66, (0.91, 0.95, 0.97)), _pdf_text(x + 13, 151, label, 9, True), _pdf_text(x + 13, 126, f"{horizon_counts[horizon]} roadmap actions", 9, False, teal)])
    page_three.extend([_pdf_text(42, 78, f"Diagnostic rules triggered: {len(diagnostic['diagnoses'])} | Detailed report: {'yes' if detailed else 'no'}", 8.5), _pdf_text(42, 54, "Use these priorities as a management conversation, then validate progress through reassessment.", 8, False, (0.4, 0.45, 0.5))])
    return _pdf_document(["\n".join(page_one), "\n".join(page_two), "\n".join(page_three)])


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
