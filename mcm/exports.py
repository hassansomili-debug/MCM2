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
        f"""SELECT a.id,a.organization_id,a.version_id,a.status,a.data_origin,a.completed_at,v.version,o.sector,o.size,o.region,cp.business_model,cp.research_consent
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
    wide_headers = ["ASSESSMENT_ID", "PARTICIPANT_ID", "ORG_ID", "DATA_ORIGIN", "INSTRUMENT_VERSION", "COMPLETED_AT"]
    for code in item_codes:
        wide_headers.extend([code, code + "_MISS"])
    wide_rows = []
    for key, values in wide_map.items():
        assessment_id, participant, org, data_origin, version, completed_at = key
        wide_rows.append([assessment_id, participant, org, data_origin, version, completed_at] + [values.get(header) for header in wide_headers[6:]])
    score_headers = ["ASSESSMENT_ID", "ORG_ID", "TOTAL", "MATURITY_LEVEL", "INSTRUMENT_VERSION", "DATA_ORIGIN", "COMPLETED_AT"]
    mcm_rows, smce_rows = [], []
    profiles = []
    for row in assessments:
        totals = {score["construct"]: score for score in db.execute("SELECT s.*,m.code AS level_code FROM assessment_scores s LEFT JOIN maturity_levels m ON m.id=s.maturity_level_id WHERE s.assessment_id=?", (row["id"],))}
        base = [row["id"], f"ORG{int(row['organization_id']):06d}"]
        if "MCM" in totals:
            mcm_rows.append(base + [totals["MCM"]["total_score"], totals["MCM"]["level_code"], row["version"], row["data_origin"], row["completed_at"]])
        if "SMCE" in totals:
            smce_rows.append(base + [totals["SMCE"]["total_score"], None, row["version"], row["data_origin"], row["completed_at"]])
        profiles.append([f"ORG{int(row['organization_id']):06d}", row["sector"], row["size"], row["region"], row["business_model"], row["data_origin"]])
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
        value_label_rows.extend([[version_id, value, ar, en] for value, ar, en in [(1, "لا ينطبق إطلاقًا", "Not at all"), (2, "ينطبق بدرجة ضعيفة", "Slightly"), (3, "ينطبق جزئيًا", "Partly"), (4, "ينطبق بدرجة كبيرة", "Mostly"), (5, "ينطبق بالكامل", "Fully")]])
    generated = datetime.now(timezone.utc).isoformat()
    return OrderedDict([
        ("01_RESPONSES_WIDE", (wide_headers, wide_rows)),
        ("02_RESPONSES_LONG", (long_headers, long_rows)),
        ("03_MCM_SCORES", (score_headers, mcm_rows)),
        ("04_SMCE_SCORES", (score_headers, smce_rows)),
        ("05_COMPANY_PROFILE", (["ORG_ID", "SECTOR", "SIZE", "REGION", "BUSINESS_MODEL", "DATA_ORIGIN"], profiles)),
        ("06_CODEBOOK", (["VARIABLE_NAME", "LABEL_AR", "LABEL_EN", "CONSTRUCT", "DIMENSION", "RESPONSE_TYPE", "VALUES", "MISSING_VALUES", "REVERSE_CODED", "SOURCE", "INSTRUMENT_VERSION"], codebook_rows)),
        ("07_VARIABLE_LABELS", (["VARIABLE_NAME", "VARIABLE_LABEL_AR", "VARIABLE_LABEL_EN"], [[row[0], row[1], row[2]] for row in codebook_rows])),
        ("08_VALUE_LABELS", (["VERSION_ID", "VALUE", "LABEL_AR", "LABEL_EN"], value_label_rows)),
        ("09_INSTRUMENT", (["VERSION", "ITEM_CODE", "CONSTRUCT", "DIMENSION", "PROMPT_AR", "PROMPT_EN", "REQUIRED", "REVERSE_CODED", "WEIGHT", "RESPONSE_TYPE", "MIN", "MAX", "STATUS", "SOURCE"], instrument_rows)),
        ("10_METADATA", (["KEY", "VALUE"], [["generated_at", generated], ["data_origin_filter", str(origin or "REAL").upper()], ["pii_included", False], ["case_count", len(assessments)], ["scoring_method", "MCM_DETERMINISTIC_1.0"], ["notice", "Research Beta - provisional instrument"]])),
    ])


def research_workbook(db, origin: str = "REAL") -> bytes:
    return xlsx_bytes(build_research_sheets(db, origin))


def spss_package(db, origin: str = "REAL") -> bytes:
    sheets = build_research_sheets(db, origin)
    wide_headers, wide_rows = sheets["01_RESPONSES_WIDE"]
    code_headers, code_rows = sheets["06_CODEBOOK"]
    label_headers, label_rows = sheets["07_VARIABLE_LABELS"]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dataset.csv", csv_bytes(wide_headers, wide_rows))
        archive.writestr("codebook.xlsx", xlsx_bytes(OrderedDict([("CODEBOOK", (code_headers, code_rows))])))
        archive.writestr("labels.xlsx", xlsx_bytes(OrderedDict([("VARIABLE_LABELS", (label_headers, label_rows))])))
        variable_names = [re.sub(r"[^A-Za-z0-9_]", "_", header.upper())[:64] for header in wide_headers]
        syntax = (
            "* NUDJ MCM SPSS import package.\n"
            "GET DATA /TYPE=TXT /FILE='dataset.csv' /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=',' /QUALIFIER='\"' /ARRANGEMENT=DELIMITED /FIRSTCASE=2\n"
            f" /VARIABLES={' '.join(name + ' A255' for name in variable_names)}.\nEXECUTE.\n"
            "* Missing-reason variables use suffix _MISS and preserve explicit missing states.\n"
        )
        archive.writestr("import.sps", syntax.encode("utf-8"))
        archive.writestr("README.txt", "NUDJ MCM Research Beta\nOpen import.sps in SPSS. The package excludes direct identifiers by default.\nValues are provisional and tied to the recorded instrument version.\n".encode("utf-8"))
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


def _simple_pdf(pages: list[list[tuple[str, int]]]) -> bytes:
    objects: list[bytes] = []

    def add(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    page_ids = []
    content_ids = []
    for page in pages:
        commands = ["BT", "/F1 10 Tf", "48 790 Td"]
        first = True
        for text, size in page:
            if not first:
                commands.append("0 -16 Td")
            commands.append(f"/{'F2' if size >= 14 else 'F1'} {size} Tf")
            commands.append(f"({_pdf_escape(text)}) Tj")
            first = False
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        content_ids.append(add(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"))
        page_ids.append(None)
    pages_id = len(objects) + len(pages) + 1
    for index, content_id in enumerate(content_ids):
        page_ids[index] = add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R /F2 {bold_id} 0 R >> >> /Contents {content_id} 0 R >>".encode())
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


def assessment_pdf(db, assessment_id: int, detailed: bool = False) -> bytes:
    result = score_payload(db, assessment_id)
    diagnostic = diagnostic_payload(db, assessment_id)
    priorities = priority_payload(db, assessment_id)
    roadmap = [dict(row) for row in db.execute("SELECT * FROM roadmap_items WHERE assessment_id=? ORDER BY sort_order", (assessment_id,))]
    mcm = result["scores"]["MCM"]
    smce = result["scores"]["SMCE"]
    level = (mcm.get("maturity_level") or {}).get("label_en") or "Provisional / not configured"
    sections: list[tuple[str, list[str]]] = [
        ("Executive Summary", [f"Organisation: {result['organization_name']}", f"Assessment: {assessment_id}", f"Instrument: {result['instrument_version']} ({result['instrument_status']})", "Research Beta - Provisional. Not a validated psychometric claim."]),
        ("Overall MCM", [f"MCM total: {mcm['total'] if mcm['total'] is not None else 'Unavailable'} / 100", f"Maturity level: {level}"]),
        ("Seven MCM Dimensions", [f"{row['code']} - {row['name_en']}: {row['score']}" for row in mcm["dimensions"]]),
        ("Strengths", [f"{row['code']} at {row['score']}" for row in sorted(mcm["dimensions"], key=lambda item: item["score"], reverse=True)[:3]] or ["No scored dimensions."]),
        ("Critical Gaps", [f"{row['dimension_code']}: gap {row['gap']}, priority {row['priority_score']}" for row in priorities["priorities"][:5]] or ["No materialised priorities."]),
        ("Deep Diagnosis", [f"{row['code']} - {row['severity']} (confidence {row['confidence']})" for row in diagnostic["diagnoses"]] or ["No configured diagnostic rule fired."]),
        ("SMCE", [f"SMCE total: {smce['total'] if smce['total'] is not None else 'Unavailable'} / 100"] + [f"{row['code']} - {row['name_en']}: {row['score']}" for row in smce["dimensions"]]),
        ("Benchmark", ["Benchmark unavailable unless the privacy minimum, consent, origin, version, and unit-of-analysis checks pass."]),
        ("Priority Recommendations", [f"{row['rank']}. {row['problem']} - {row['action']}" for row in priorities["priorities"][:7]] or ["No recommendations generated."]),
        ("30 / 90 / 180 Roadmap", [f"{row['horizon']} | {row['title']} | {row['owner'] or 'Unassigned'} | {row['status']}" for row in roadmap] or ["No roadmap items generated."]),
        ("Methodological Note", ["MCM and SMCE are calculated independently using deterministic server-side rules.", "Context and organisational enablers are not included in the MCM denominator.", "Missing responses are not converted to zero. Scores remain tied to instrument and scoring versions."]),
    ]
    if not detailed:
        executive_titles = {"Executive Summary", "Overall MCM", "Seven MCM Dimensions", "Strengths", "Critical Gaps", "SMCE", "Priority Recommendations", "30 / 90 / 180 Roadmap", "Methodological Note"}
        sections = [(title, lines) for title, lines in sections if title in executive_titles]
    pages = []
    current = [(f"NUDJ MCM - {'Detailed' if detailed else 'Executive'} Maturity Report", 18)]
    for title, lines in sections:
        block = [(title, 14)]
        for line in lines:
            block.extend((wrapped, 10) for wrapped in _wrap(line))
        if len(current) + len(block) > 40:
            pages.append(current)
            current = [("NUDJ MCM - Continued", 16)]
        current.extend(block)
    pages.append(current)
    return _simple_pdf(pages)


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
