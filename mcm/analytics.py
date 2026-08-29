"""Descriptive analytics over completed assessments.

Every figure is computed on the server from stored scores. Nothing here changes
a score, a classification or an instrument; it only describes what was already
measured.

Two rules run through the whole module:

- MCM and SMCE stay separate constructs. They are described side by side and
  their association is reported, but they are never combined into one index and
  no ranking blends them.
- An association is reported as an association. Correlation coefficients carry
  their sample size and an explicit statement that they do not establish cause.

Small groups are suppressed rather than shown, so a cell can never identify one
organisation.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from .database import get_config

# The unit of analysis. Counting several assessments from one organisation
# would let a single active establishment dominate every distribution.
LATEST_PER_ORGANIZATION = "LATEST_PER_ORGANIZATION"
ALL_COMPLETED = "ALL_COMPLETED"

CONTEXT_VARIABLES = {
    "sector": "القطاع",
    "firm_size": "حجم المنشأة",
    "business_model": "نموذج الأعمال",
    "region": "المنطقة",
    "regulated": "قطاع منظم رقابيًا",
    "respondent_role": "دور المجيب",
}
NUMERIC_VARIABLES = {
    "employee_count": "عدد الموظفين",
    "firm_age_years": "عمر المنشأة",
    "social_platform_count": "عدد المنصات",
    "social_team_size": "حجم فريق التواصل",
    "leadership_support": "دعم القيادة",
    "human_competencies": "الكفاءات البشرية",
    "technology_infrastructure": "البنية التقنية",
    "data_readiness": "جاهزية البيانات",
}


def _percentile(values: list[float], fraction: float) -> float | None:
    """Linear-interpolated percentile; returns None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def describe(values: list[float]) -> dict:
    """Standard descriptive summary for one numeric variable."""
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"n": 0}
    mean = sum(clean) / len(clean)
    # Sample standard deviation; undefined for a single observation.
    variance = sum((value - mean) ** 2 for value in clean) / (len(clean) - 1) if len(clean) > 1 else None
    return {
        "n": len(clean),
        "mean": round(mean, 2),
        "median": _percentile(clean, 0.5),
        "sd": round(math.sqrt(variance), 2) if variance is not None else None,
        "min": round(min(clean), 2),
        "max": round(max(clean), 2),
        "p25": _percentile(clean, 0.25),
        "p75": _percentile(clean, 0.75),
    }


def _rank(values: list[float]) -> list[float]:
    """Average ranks, so ties do not manufacture an ordering."""
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        stop = position
        while stop + 1 < len(ordered) and values[ordered[stop + 1]] == values[ordered[position]]:
            stop += 1
        shared = (position + stop) / 2 + 1
        for index in range(position, stop + 1):
            ranks[ordered[index]] = shared
        position = stop + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    dx = [value - mean_x for value in xs]
    dy = [value - mean_y for value in ys]
    denominator = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denominator == 0:
        # A constant variable has no linear relationship to describe.
        return None
    return round(sum(a * b for a, b in zip(dx, dy)) / denominator, 3)


def correlate(xs: list[float], ys: list[float], minimum: int) -> dict:
    """Pearson and Spearman with the caveats that must travel with them."""
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    # The causal caveat travels with the result in every state. A reader who
    # sees only the withheld message must still not infer a causal claim from
    # the section it sits in.
    causality = "ارتباط وصفي، ولا يثبت علاقة سببية."
    if n < minimum:
        return {
            "available": False,
            "n": n,
            "minimum": minimum,
            "reason": "SAMPLE_BELOW_MINIMUM",
            "notice_ar": f"يلزم {minimum} حالة على الأقل قبل عرض معامل ارتباط.",
            "causality_notice_ar": causality,
        }
    xs_clean = [pair[0] for pair in pairs]
    ys_clean = [pair[1] for pair in pairs]
    pearson = _pearson(xs_clean, ys_clean)
    spearman = _pearson(_rank(xs_clean), _rank(ys_clean))
    result = {
        "available": pearson is not None,
        "n": n,
        "minimum": minimum,
        "pearson_r": pearson,
        "spearman_rho": spearman,
        "notice_ar": causality,
        "causality_notice_ar": causality,
    }
    if pearson is not None:
        # Fisher z interval. Reported so a coefficient is never read as exact.
        z = 0.5 * math.log((1 + pearson) / (1 - pearson)) if abs(pearson) < 1 else None
        if z is not None and n > 3:
            margin = 1.959964 / math.sqrt(n - 3)
            result["ci95"] = [
                round(math.tanh(z - margin), 3),
                round(math.tanh(z + margin), 3),
            ]
    return result


def _fetch_population(db, mode: str, data_origin: str, filters: dict) -> list[dict]:
    """Completed assessments with both construct totals, one row each."""
    clauses = ["a.status='COMPLETED'"]
    params: list = []
    if data_origin != "ALL":
        clauses.append("a.data_origin=?")
        params.append(data_origin)
    for column, value in (filters or {}).items():
        if value in (None, ""):
            continue
        clauses.append(f"ctx.{column}=?")
        params.append(value)
    rows = [
        dict(row)
        for row in db.execute(
            f"""SELECT a.id AS assessment_id,a.organization_id,a.version_id,a.completed_at,
                       o.name AS organization_name,
                       ctx.sector,ctx.firm_size,ctx.business_model,ctx.region,ctx.regulated,
                       ctx.respondent_role,ctx.employee_count,ctx.firm_age_years,
                       ctx.social_platform_count,ctx.social_team_size,
                       ctx.leadership_support,ctx.human_competencies,
                       ctx.technology_infrastructure,ctx.data_readiness,
                       mcm.total_score AS mcm_total,smce.total_score AS smce_total,
                       lvl.code AS maturity_code,lvl.label_ar AS maturity_label,lvl.level_order
                FROM assessments a
                JOIN organizations o ON o.id=a.organization_id
                LEFT JOIN assessment_context ctx ON ctx.assessment_id=a.id
                JOIN assessment_scores mcm ON mcm.assessment_id=a.id AND mcm.construct='MCM'
                JOIN assessment_scores smce ON smce.assessment_id=a.id AND smce.construct='SMCE'
                LEFT JOIN maturity_levels lvl ON lvl.id=mcm.maturity_level_id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.completed_at DESC,a.id DESC""",
            tuple(params),
        )
    ]
    if mode == ALL_COMPLETED:
        return rows
    latest: dict[int, dict] = {}
    for row in rows:
        latest.setdefault(row["organization_id"], row)
    return list(latest.values())


def _dimension_matrix(db, assessment_ids: list[int]) -> dict[int, dict[str, float]]:
    if not assessment_ids:
        return {}
    placeholders = ",".join("?" for _ in assessment_ids)
    matrix: dict[int, dict[str, float]] = defaultdict(dict)
    for row in db.execute(
        f"SELECT assessment_id,dimension_code,score FROM dimension_scores WHERE assessment_id IN ({placeholders})",
        tuple(assessment_ids),
    ):
        matrix[row["assessment_id"]][row["dimension_code"]] = float(row["score"])
    return matrix


def analytics_payload(db, *, mode: str = LATEST_PER_ORGANIZATION, data_origin: str = "REAL",
                      filters: dict | None = None, include_names: bool = False) -> dict:
    """The full analysis payload for the platform analysis centre."""
    minimum_group = int(get_config(db, "MIN_ANALYTICS_COHORT_SIZE", 10) or 10)
    minimum_relationship = int(get_config(db, "MIN_RELATIONSHIP_SAMPLE", 30) or 30)
    population = _fetch_population(db, mode, data_origin, filters or {})
    mcm = [float(row["mcm_total"]) for row in population]
    smce = [float(row["smce_total"]) for row in population]
    matrix = _dimension_matrix(db, [row["assessment_id"] for row in population])

    versions = sorted({row["version_id"] for row in population})
    dimension_codes = sorted({code for scores in matrix.values() for code in scores})

    # Grouped descriptives. A group below the minimum is reported as suppressed
    # rather than omitted silently, so the reader knows it exists.
    groups = {}
    for variable, label in CONTEXT_VARIABLES.items():
        buckets: dict[str, list[dict]] = defaultdict(list)
        for row in population:
            buckets[str(row.get(variable) or "غير محدد")].append(row)
        entries = []
        for value, members in sorted(buckets.items(), key=lambda item: -len(item[1])):
            entry = {"value": value, "n": len(members)}
            if len(members) < minimum_group:
                entry["suppressed"] = True
            else:
                entry["mcm"] = describe([float(item["mcm_total"]) for item in members])
                entry["smce"] = describe([float(item["smce_total"]) for item in members])
            entries.append(entry)
        groups[variable] = {"label_ar": label, "groups": entries}

    # Associations between the context variables and each construct, reported
    # separately so neither construct is treated as the other's outcome.
    associations = []
    for variable, label in NUMERIC_VARIABLES.items():
        xs, mcm_pairs, smce_pairs = [], [], []
        for row in population:
            value = row.get(variable)
            if value is None:
                continue
            xs.append(float(value))
            mcm_pairs.append(float(row["mcm_total"]))
            smce_pairs.append(float(row["smce_total"]))
        associations.append({
            "variable": variable,
            "label_ar": label,
            "descriptives": describe(xs),
            "with_mcm": correlate(xs, mcm_pairs, minimum_relationship),
            "with_smce": correlate(xs, smce_pairs, minimum_relationship),
        })

    stage_counts = Counter(row["maturity_label"] or "غير مصنف" for row in population)
    quadrant_x = _percentile(mcm, 0.5)
    quadrant_y = _percentile(smce, 0.5)
    quadrants = {"HIGH_HIGH": 0, "HIGH_LOW": 0, "LOW_HIGH": 0, "LOW_LOW": 0}
    if quadrant_x is not None and quadrant_y is not None:
        for row in population:
            high_mcm = float(row["mcm_total"]) >= quadrant_x
            high_smce = float(row["smce_total"]) >= quadrant_y
            key = f"{'HIGH' if high_mcm else 'LOW'}_{'HIGH' if high_smce else 'LOW'}"
            quadrants[key] += 1

    scatter = [
        {
            "assessment_id": row["assessment_id"],
            "organization_id": row["organization_id"],
            # Names are for the platform manager only; every other reader gets
            # the reference alone.
            "organization_name": row["organization_name"] if include_names else None,
            "mcm_total": float(row["mcm_total"]),
            "smce_total": float(row["smce_total"]),
            "maturity_label": row["maturity_label"],
            "sector": row["sector"],
            "firm_size": row["firm_size"],
            "completed_at": row["completed_at"],
        }
        for row in population
    ]

    dimension_summary = [
        {
            "code": code,
            "label_ar": code,
            **describe([scores[code] for scores in matrix.values() if code in scores]),
        }
        for code in dimension_codes
    ]

    return {
        "unit_of_analysis": mode,
        "data_origin": data_origin,
        "filters": {key: value for key, value in (filters or {}).items() if value},
        "n": len(population),
        "instrument_versions": versions,
        "version_warning_ar": (
            "تشمل العينة أكثر من إصدار للأداة؛ فسّر المقارنة بحذر."
            if len(versions) > 1 else None
        ),
        "minimum_group_size": minimum_group,
        "minimum_relationship_sample": minimum_relationship,
        "summary": {
            "mcm": describe(mcm),
            "smce": describe(smce),
            "stage_distribution": [
                {"label_ar": label, "n": count} for label, count in stage_counts.most_common()
            ],
        },
        "relationship": {
            **correlate(mcm, smce, minimum_relationship),
            "interpretation_ar": (
                "يعرض النموذج النضج والكفاءة بوصفهما بناءين منفصلين. "
                "الارتباط بينهما وصفي، ولا يُقرأ بوصفه أثرًا سببيًا."
            ),
        },
        "quadrants": {
            "boundary_method": "COHORT_MEDIAN",
            "mcm_boundary": quadrant_x,
            "smce_boundary": quadrant_y,
            "counts": quadrants,
            "labels_ar": {
                "HIGH_HIGH": "نضج مرتفع وكفاءة مرتفعة",
                "HIGH_LOW": "نضج مرتفع وكفاءة منخفضة",
                "LOW_HIGH": "نضج منخفض وكفاءة مرتفعة",
                "LOW_LOW": "نضج منخفض وكفاءة منخفضة",
            },
        },
        "dimensions": dimension_summary,
        "groups": groups,
        "associations": associations,
        "scatter": scatter,
        "notice_ar": (
            "إحصاءات وصفية على الحالات المكتملة فقط. لا تُدمج درجتا MCM وSMCE في مؤشر واحد، "
            "وتُحجب المجموعات الأصغر من الحد الأدنى للعينة."
        ),
    }
