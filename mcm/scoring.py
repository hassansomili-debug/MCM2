from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta

from .database import get_config, now


SCORING_METHOD = "MCM_DETERMINISTIC_1.0"


class ScoringError(ValueError):
    def __init__(self, code: str, details=None):
        super().__init__(code)
        self.code = code
        self.details = details


def assessment_review(db, assessment_id: int, participant_id: int | None = None) -> dict:
    assessment = db.execute("SELECT * FROM assessments WHERE id=?", (assessment_id,)).fetchone()
    if not assessment:
        raise ScoringError("assessment_not_found")
    items = db.execute(
        "SELECT id,code,construct,dimension_code,required FROM items WHERE version_id=? ORDER BY sort_order,id",
        (assessment["version_id"],),
    ).fetchall()
    response_query = "SELECT item_id FROM responses WHERE assessment_id=? AND missing_type IS NULL AND (numeric_value IS NOT NULL OR text_value IS NOT NULL)"
    response_params: list[int] = [assessment_id]
    if participant_id is not None:
        response_query += " AND participant_id=?"
        response_params.append(participant_id)
    answered = {
        row["item_id"]
        for row in db.execute(response_query, tuple(response_params))
    }
    missing = [
        {"item_id": row["id"], "code": row["code"], "construct": row["construct"], "dimension_code": row["dimension_code"]}
        for row in items
        if row["required"] and row["id"] not in answered
    ]
    required_count = sum(bool(row["required"]) for row in items)
    answered_required = required_count - len(missing)
    return {
        "assessment_id": assessment_id,
        "participant_id": participant_id,
        "status": assessment["status"],
        "item_count": len(items),
        "required_count": required_count,
        "answered_required": answered_required,
        "missing_required": missing,
        "complete": not missing and required_count > 0,
        "progress": round(answered_required / required_count * 100, 1) if required_count else 0,
    }


def _normalize(value: float, minimum: float, maximum: float, reverse: bool) -> float:
    if maximum <= minimum:
        raise ScoringError("invalid_scale")
    normalized = (value - minimum) / (maximum - minimum) * 100
    normalized = max(0.0, min(100.0, normalized))
    return 100.0 - normalized if reverse else normalized


def _level(db, version_id: int, score: float):
    return db.execute(
        """SELECT id,code,label_ar,label_en,level_order,min_score,max_score
           FROM maturity_levels WHERE version_id=? AND ?>=min_score AND ?<max_score
           ORDER BY level_order LIMIT 1""",
        (version_id, score, score),
    ).fetchone()


def calculate_scores(db, assessment_id: int) -> dict:
    assessment = db.execute("SELECT * FROM assessments WHERE id=?", (assessment_id,)).fetchone()
    if not assessment:
        raise ScoringError("assessment_not_found")
    review = assessment_review(db, assessment_id)
    if not review["complete"]:
        raise ScoringError("required_answers_missing", review)
    rows = db.execute(
        """SELECT i.id,i.construct,i.dimension_code,i.reverse_coded,i.weight,i.min_value,i.max_value,
                  r.participant_id,r.numeric_value,r.missing_type
           FROM items i LEFT JOIN responses r ON r.item_id=i.id AND r.assessment_id=?
           WHERE i.version_id=? AND i.construct IN ('MCM','SMCE')
           ORDER BY i.sort_order,i.id""",
        (assessment_id, assessment["version_id"]),
    ).fetchall()
    response_snapshot = [
        dict(row)
        for row in db.execute(
            "SELECT participant_id,item_id,numeric_value,text_value,missing_type,updated_at FROM responses WHERE assessment_id=? ORDER BY participant_id,item_id",
            (assessment_id,),
        )
    ]
    input_hash = hashlib.sha256(json.dumps(response_snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    configuration = {
        "priority_weights": get_config(db, "PRIORITY_WEIGHTS", {}),
        "gap_threshold": get_config(db, "GAP_THRESHOLD", None),
        "normalization": "(x-min)/(max-min)*100",
        "multi_respondent": "mean_by_item",
        "instrument_status": db.execute("SELECT status FROM instrument_versions WHERE id=?", (assessment["version_id"],)).fetchone()[0],
    }
    run_number = db.execute("SELECT COALESCE(MAX(run_number),0)+1 FROM score_runs WHERE assessment_id=?", (assessment_id,)).fetchone()[0]
    db.execute("UPDATE score_runs SET is_current=0 WHERE assessment_id=?", (assessment_id,))
    score_run_id = db.execute(
        """INSERT INTO score_runs(assessment_id,run_number,instrument_version_id,scoring_version,configuration_json,input_hash,is_current,created_at)
           VALUES (?,?,?,?,?,?,1,?)""",
        (assessment_id, run_number, assessment["version_id"], SCORING_METHOD, json.dumps(configuration, ensure_ascii=False, sort_keys=True), input_hash, now()),
    ).lastrowid
    per_item = defaultdict(list)
    item_meta = {}
    for row in rows:
        item_meta[row["id"]] = row
        if row["numeric_value"] is None or row["missing_type"]:
            continue
        per_item[row["id"]].append(float(row["numeric_value"]))
    dimension_values = defaultdict(list)
    for item_id, values in per_item.items():
        meta = item_meta[item_id]
        mean_value = sum(values) / len(values)
        normalized = _normalize(
            mean_value,
            float(meta["min_value"] if meta["min_value"] is not None else 1),
            float(meta["max_value"] if meta["max_value"] is not None else 5),
            bool(meta["reverse_coded"]),
        )
        effective = (float(meta["min_value"] or 1) + float(meta["max_value"] or 5) - mean_value) if meta["reverse_coded"] else mean_value
        db.execute(
            """INSERT INTO response_item_scores(score_run_id,item_id,raw_value,effective_value,normalized_score,reverse_coded,item_weight)
               VALUES (?,?,?,?,?,?,?)""",
            (score_run_id, item_id, mean_value, effective, normalized, int(bool(meta["reverse_coded"])), float(meta["weight"] or 1)),
        )
        dimension_values[(meta["construct"], meta["dimension_code"])].append((normalized, float(meta["weight"] or 1)))
    calculated_at = now()
    db.execute("DELETE FROM dimension_scores WHERE assessment_id=?", (assessment_id,))
    db.execute("DELETE FROM assessment_scores WHERE assessment_id=?", (assessment_id,))
    db.execute("DELETE FROM scores WHERE assessment_id=?", (assessment_id,))
    construct_dimensions = defaultdict(list)
    for (construct, dimension_code), values in dimension_values.items():
        weighted_sum = sum(value * weight for value, weight in values)
        weight_sum = sum(weight for _, weight in values)
        score = round(weighted_sum / weight_sum, 2)
        answered_count = len(values)
        eligible_count = db.execute(
            "SELECT COUNT(*) FROM items WHERE version_id=? AND dimension_code=? AND construct=?",
            (assessment["version_id"], dimension_code, construct),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO dimension_scores VALUES (?,?,?,?,?,?,?,?)",
            (assessment_id, dimension_code, construct, score, answered_count, eligible_count, SCORING_METHOD, calculated_at),
        )
        db.execute(
            "INSERT INTO score_run_dimensions VALUES (?,?,?,?,?,?)",
            (score_run_id, dimension_code, construct, score, answered_count, eligible_count),
        )
        db.execute("INSERT OR REPLACE INTO scores VALUES (?,?,?,?)", (assessment_id, construct, dimension_code, score))
        dim_weight = db.execute("SELECT weight FROM dimensions WHERE version_id=? AND code=? LIMIT 1", (assessment["version_id"], dimension_code)).fetchone()
        construct_dimensions[construct].append((score, float(dim_weight["weight"] if dim_weight else 1)))
    totals = {}
    for construct in ("MCM", "SMCE"):
        values = construct_dimensions.get(construct, [])
        if not values:
            continue
        total = round(sum(score * weight for score, weight in values) / sum(weight for _, weight in values), 2)
        level = _level(db, assessment["version_id"], total) if construct == "MCM" else None
        answered_count = sum(len(v) for (c, _), v in dimension_values.items() if c == construct)
        db.execute(
            "INSERT INTO assessment_scores VALUES (?,?,?,?,?,?,?)",
            (assessment_id, construct, total, level["id"] if level else None, answered_count, SCORING_METHOD, calculated_at),
        )
        db.execute(
            "INSERT INTO score_run_totals VALUES (?,?,?,?)",
            (score_run_id, construct, total, level["id"] if level else None),
        )
        totals[construct] = total
    _materialize_diagnostics(db, assessment_id, assessment["version_id"])
    _materialize_priorities(db, assessment_id, assessment["version_id"])
    _materialize_quality_flags(db, assessment_id, review)
    output_hash = hashlib.sha256(json.dumps(totals, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    db.execute("UPDATE score_runs SET output_hash=? WHERE id=?", (output_hash, score_run_id))
    return score_payload(db, assessment_id)


def _dimension_map(db, assessment_id: int) -> dict[str, float]:
    return {row["dimension_code"]: float(row["score"]) for row in db.execute("SELECT dimension_code,score FROM dimension_scores WHERE assessment_id=?", (assessment_id,))}


def _materialize_diagnostics(db, assessment_id: int, version_id: int) -> None:
    scores = _dimension_map(db, assessment_id)
    db.execute("DELETE FROM diagnostic_results WHERE assessment_id=?", (assessment_id,))
    rules = db.execute("SELECT * FROM diagnostic_rules WHERE version_id=? AND active=1", (version_id,)).fetchall()
    for rule in rules:
        codes = rule["dimensions"].split(":")
        values = [scores.get(code) for code in codes]
        if any(value is None for value in values):
            continue
        operator = rule["operator"]
        threshold = float(rule["threshold"])
        matched = (
            (operator == "lt" and values[0] < threshold)
            or (operator == "gap_gt" and values[0] - values[1] > threshold)
            or (operator == "average_lt" and sum(values) / len(values) < threshold)
        )
        if matched:
            evidence = {code: round(scores[code], 2) for code in codes}
            db.execute(
                "INSERT INTO diagnostic_results(assessment_id,rule_id,evidence_json,created_at) VALUES (?,?,?,?)",
                (assessment_id, rule["id"], json.dumps(evidence, ensure_ascii=False), now()),
            )


def _materialize_priorities(db, assessment_id: int, version_id: int) -> None:
    db.execute("DELETE FROM assessment_recommendations WHERE assessment_id=?", (assessment_id,))
    db.execute("DELETE FROM roadmap_items WHERE assessment_id=?", (assessment_id,))
    weights = get_config(db, "PRIORITY_WEIGHTS", {"gap": .45, "impact": .25, "dependency": .15, "effort": .10, "confidence": .05})
    dimensions = db.execute(
        "SELECT dimension_code,score FROM dimension_scores WHERE assessment_id=? AND construct='MCM' ORDER BY score",
        (assessment_id,),
    ).fetchall()
    ranked = []
    for row in dimensions:
        recommendation = db.execute(
            "SELECT * FROM recommendations WHERE version_id=? AND dimension_code=? AND active=1",
            (version_id, row["dimension_code"]),
        ).fetchone()
        if not recommendation:
            continue
        gap = max(0.0, 80.0 - float(row["score"]))
        impact = {"HIGH": 100, "MEDIUM": 65, "LOW": 35}.get(recommendation["expected_impact"], 65)
        effort_bonus = {"LOW": 100, "MEDIUM": 65, "HIGH": 35}.get(recommendation["effort"], 65)
        dependency = 100 if row["dimension_code"] in ("MCM01", "MCM03", "MCM07") else 60
        confidence = 85
        priority = round(
            gap * float(weights.get("gap", .45))
            + impact * float(weights.get("impact", .25))
            + dependency * float(weights.get("dependency", .15))
            + effort_bonus * float(weights.get("effort", .10))
            + confidence * float(weights.get("confidence", .05)),
            2,
        )
        ranked.append((priority, gap, recommendation))
    ranked.sort(key=lambda item: item[0], reverse=True)
    today = date.today()
    for rank, (priority, gap, recommendation) in enumerate(ranked, 1):
        db.execute(
            "INSERT INTO assessment_recommendations VALUES (?,?,?,?,?,?)",
            (assessment_id, recommendation["id"], priority, round(gap, 2), rank, "ترتيب حتمي مبني على الفجوة والأثر والاعتمادية والجهد والثقة."),
        )
        if rank <= 2:
            horizon, target = "0-30", today + timedelta(days=30)
        elif rank <= 5:
            horizon, target = "31-90", today + timedelta(days=90)
        else:
            horizon, target = "3-6", today + timedelta(days=180)
        db.execute(
            """INSERT INTO roadmap_items(assessment_id,recommendation_id,horizon,title,description,owner,status,target_date,impact,effort,kpi,sort_order)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (assessment_id, recommendation["id"], horizon, recommendation["problem"], recommendation["action"], recommendation["suggested_owner"], "NOT_STARTED", target.isoformat(), recommendation["expected_impact"], recommendation["effort"], recommendation["kpi"], rank),
        )


def _materialize_quality_flags(db, assessment_id: int, review: dict) -> None:
    db.execute("DELETE FROM data_quality_flags WHERE assessment_id=?", (assessment_id,))
    if review["missing_required"]:
        db.execute(
            "INSERT INTO data_quality_flags(assessment_id,flag_type,severity,details,created_at) VALUES (?,?,?,?,?)",
            (assessment_id, "MISSING_REQUIRED", "HIGH", f"{len(review['missing_required'])} required responses are missing", now()),
        )
    values = [row[0] for row in db.execute("SELECT numeric_value FROM responses WHERE assessment_id=? AND numeric_value IS NOT NULL", (assessment_id,))]
    if len(values) >= 10 and len(set(values)) == 1:
        db.execute(
            "INSERT INTO data_quality_flags(assessment_id,flag_type,severity,details,created_at) VALUES (?,?,?,?,?)",
            (assessment_id, "STRAIGHT_LINING", "MEDIUM", "All numeric responses have the same value", now()),
        )
    assessment = db.execute("SELECT created_at,submitted_at FROM assessments WHERE id=?", (assessment_id,)).fetchone()
    if assessment and assessment["submitted_at"] and assessment["submitted_at"] - assessment["created_at"] < 180:
        db.execute(
            "INSERT INTO data_quality_flags(assessment_id,flag_type,severity,details,created_at) VALUES (?,?,?,?,?)",
            (assessment_id, "SUSPICIOUS_DURATION", "MEDIUM", "Completion time was under three minutes", now()),
        )


def score_payload(db, assessment_id: int) -> dict:
    assessment = db.execute(
        """SELECT a.*,v.version AS instrument_version,v.status AS instrument_status,o.name AS organization_name
           FROM assessments a JOIN instrument_versions v ON v.id=a.version_id JOIN organizations o ON o.id=a.organization_id
           WHERE a.id=?""",
        (assessment_id,),
    ).fetchone()
    if not assessment:
        raise ScoringError("assessment_not_found")
    dimension_rows = db.execute(
        """SELECT ds.*,COALESCE(d.name,ds.dimension_code) AS name,COALESCE(d.name_en,ds.dimension_code) AS name_en
           FROM dimension_scores ds
           LEFT JOIN assessments a ON a.id=ds.assessment_id
           LEFT JOIN dimensions d ON d.version_id=a.version_id AND d.code=ds.dimension_code
           WHERE ds.assessment_id=? GROUP BY ds.dimension_code ORDER BY ds.construct,ds.dimension_code""",
        (assessment_id,),
    ).fetchall()
    totals = {row["construct"]: row for row in db.execute(
        """SELECT s.*,m.code AS level_code,m.label_ar,m.label_en,m.level_order
           FROM assessment_scores s LEFT JOIN maturity_levels m ON m.id=s.maturity_level_id WHERE s.assessment_id=?""",
        (assessment_id,),
    )}
    grouped = {"MCM": [], "SMCE": []}
    for row in dimension_rows:
        if row["construct"] in grouped:
            grouped[row["construct"]].append({
                "code": row["dimension_code"], "name": row["name"], "name_en": row["name_en"],
                "score": row["score"], "answered_count": row["answered_count"], "eligible_count": row["eligible_count"],
            })
    mcm = totals.get("MCM")
    smce = totals.get("SMCE")
    return {
        "assessment_id": assessment_id,
        "organization_name": assessment["organization_name"],
        "instrument_version_id": assessment["version_id"],
        "instrument_version": assessment["instrument_version"],
        "instrument_status": assessment["instrument_status"],
        "assessment_status": assessment["status"],
        "completed_at": assessment["completed_at"],
        "data_origin": assessment["data_origin"],
        "scores": {
            "MCM": {
                "total": mcm["total_score"] if mcm else None,
                "maturity_level": ({"code": mcm["level_code"], "label_ar": mcm["label_ar"], "label_en": mcm["label_en"], "order": mcm["level_order"]} if mcm and mcm["level_code"] else None),
                "dimensions": grouped["MCM"],
            },
            "SMCE": {"total": smce["total_score"] if smce else None, "dimensions": grouped["SMCE"]},
        },
        "classification_notice": "Research Beta - the instrument is undergoing empirical validation.",
    }


def diagnostic_payload(db, assessment_id: int) -> dict:
    rows = db.execute(
        """SELECT r.code,r.name_ar,r.dimensions,r.severity,r.confidence,d.evidence_json
           FROM diagnostic_results d JOIN diagnostic_rules r ON r.id=d.rule_id
           WHERE d.assessment_id=? ORDER BY CASE r.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,r.code""",
        (assessment_id,),
    ).fetchall()
    return {
        "assessment_id": assessment_id,
        "diagnoses": [
            {
                "code": row["code"], "name": row["name_ar"], "severity": row["severity"],
                "confidence": row["confidence"], "affected_dimensions": row["dimensions"].split(":"),
                "evidence": json.loads(row["evidence_json"]),
                "interpretation": "تشير النتيجة إلى فجوة قدرة قابلة للمعالجة بخطوات محددة.",
                "business_implication": "قد تؤثر الفجوة على الاتساق والسرعة وجودة تجربة أصحاب المصلحة.",
            }
            for row in rows
        ],
    }


def gap_payload(db, assessment_id: int) -> dict:
    scores = _dimension_map(db, assessment_id)
    threshold = float(get_config(db, "GAP_THRESHOLD", 15))
    patterns = [
        ("STRATEGY_INFORMATION", "فجوة الاستراتيجية وحوكمة المعلومات", "MCM01", "MCM03"),
        ("INFORMATION_JOURNEY", "فجوة المعلومات ورحلة العميل", "MCM03", "MCM04"),
        ("JOURNEY_EXPERIENCE", "فجوة الرحلة والتجربة", "MCM04", "MCM05"),
        ("EVIDENCE_ADAPTATION", "فجوة الأدلة والتعلم", "MCM05", "MCM06"),
        ("KNOWLEDGE_SCALABILITY", "فجوة المعرفة وقابلية التوسع", "MCM06", "MCM07"),
    ]
    gaps = []
    for code, name, source, target in patterns:
        if source not in scores or target not in scores:
            continue
        value = round(scores[source] - scores[target], 2)
        if abs(value) >= threshold:
            gaps.append({"code": code, "name": name, "source": source, "target": target, "gap": value, "threshold": threshold})
    totals = {row["construct"]: row["total_score"] for row in db.execute("SELECT construct,total_score FROM assessment_scores WHERE assessment_id=?", (assessment_id,))}
    if "MCM" in totals and "SMCE" in totals:
        value = round(float(totals["MCM"]) - float(totals["SMCE"]), 2)
        if abs(value) >= threshold:
            gaps.append({"code": "MCM_SMCE", "name": "فجوة النضج وكفاءة التواصل الاجتماعي", "source": "MCM", "target": "SMCE", "gap": value, "threshold": threshold})
    return {"assessment_id": assessment_id, "threshold": threshold, "gaps": gaps}


def priority_payload(db, assessment_id: int) -> dict:
    rows = db.execute(
        """SELECT ar.rank,ar.priority_score,ar.gap,ar.rationale,r.dimension_code,r.problem,r.action,r.suggested_owner,r.expected_impact,r.effort,r.kpi,ds.score AS current_score
           FROM assessment_recommendations ar JOIN recommendations r ON r.id=ar.recommendation_id
           LEFT JOIN dimension_scores ds ON ds.assessment_id=ar.assessment_id AND ds.dimension_code=r.dimension_code
           WHERE ar.assessment_id=? ORDER BY ar.rank""",
        (assessment_id,),
    ).fetchall()
    return {"assessment_id": assessment_id, "priorities": [dict(row) for row in rows]}
