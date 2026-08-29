"""Optional, privacy-conscious AI enhancement for MCM improvement plans.

The scientific score, maturity classification, and deterministic priorities must
be calculated elsewhere.  This module only turns an already aggregated result
into a more readable 30/90/180-day plan.  It deliberately has no dependency on
the rest of the application so it can be integrated behind an API route later.

Supported providers are ``off``, ``groq``, ``gemini``, and ``ollama``.  With the
default provider (``off``), :func:`generate_improvement_plan` never opens a
network connection and returns :func:`deterministic_improvement_plan` directly.
Cloud API keys are read from environment variables or accepted as explicit
keyword-only arguments; they are never added to prompts, errors, or returned
objects.

Suggested environment variables::

    MCM_AI_PROVIDER=off|groq|gemini|ollama
    MCM_AI_MODEL=<optional provider model override>
    MCM_AI_BASE_URL=<optional endpoint override>
    MCM_AI_API_KEY=<optional generic key override>
    GROQ_API_KEY=<Groq key>
    GEMINI_API_KEY=<Gemini key>
    OLLAMA_API_KEY=<optional authenticated Ollama gateway key>

Only server-controlled configuration should be passed as ``base_url``.  Never
accept a base URL or API key from a participant request.
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from .instrument_v02 import MATURITY_LEVELS as INSTRUMENT_MATURITY_LEVELS


SCHEMA_VERSION = "MCM_IMPROVEMENT_PLAN_1.0"
SUPPORTED_PROVIDERS = frozenset({"off", "groq", "gemini", "ollama"})
MAX_RESPONSE_BYTES = 512 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0

_SAFETY_NOTICE = (
    "هذه توصيات إرشادية مولدة أو مصاغة آليًا استنادًا إلى نتائج مجمعة، "
    "ولا تغير الدرجة العلمية أو مرحلة النضج، وتحتاج اعتمادًا بشريًا قبل التنفيذ."
)

# Derived from the instrument so a stage rename never has to be repeated here.
_MATURITY_LEVELS = {
    level["code"]: (level["level_order"], level["label_ar"])
    for level in INSTRUMENT_MATURITY_LEVELS
}

_SMCE_DIMENSIONS = {
    "SMCE01": "كفاءة الاستجابة والحل",
    "SMCE02": "جودة المعنى والتفاعل",
    "SMCE03": "كفاءة الانتقال إلى الفعل",
    "SMCE04": "انخفاض الاحتكاك الاتصالي",
    "SMCE05": "كفاءة الموارد وتحقيق الأهداف",
}
_ENABLER_DIMENSIONS = {
    "EN01": "دعم القيادة",
    "EN02": "الكفاءات البشرية",
    "EN03": "البنية التحتية التقنية",
    "EN04": "جاهزية البيانات",
}

_PLAYBOOK = {
    "MCM01": {
        "name_ar": "الحوكمة والتوجيه الاستراتيجي للاتصال",
        "owner_ar": "الإدارة العليا ومدير التسويق",
        "kpi_ar": "نسبة المبادرات الاتصالية المرتبطة بهدف ومالك وقرار موثق",
        "days_30": "اعتماد ميثاق مختصر يحدد أهداف الاتصال وصلاحيات القرار والمالكين.",
        "days_90": "تطبيق بوابة قرار موحدة على الحملات الجديدة ومراجعة الالتزام شهريًا.",
        "days_180": "إدماج حوكمة الاتصال في التخطيط والميزانية والمراجعة الربعية.",
    },
    "MCM02": {
        "name_ar": "ذكاء أصحاب المصلحة والسياق",
        "owner_ar": "فريق الاستراتيجية والتسويق",
        "kpi_ar": "نسبة شرائح أصحاب المصلحة ذات بيانات ورؤى محدثة خلال 90 يومًا",
        "days_30": "تحديد الشرائح ذات الأولوية وتوثيق احتياجاتها ومصادر المعرفة المتاحة.",
        "days_90": "تشغيل سجل شهري للرؤى يربط كل شريحة برسائل وقرارات قابلة للقياس.",
        "days_180": "دمج تحديث رؤى أصحاب المصلحة في دورة التخطيط وتطوير العروض.",
    },
    "MCM03": {
        "name_ar": "حوكمة المعلومات والنزاهة الاتصالية",
        "owner_ar": "التسويق والمنتج والامتثال",
        "kpi_ar": "نسبة المواد الاتصالية المرتبطة بمصدر معتمد وحديث",
        "days_30": "تعيين مالك وإنشاء مصدر حقيقة موحد للرسائل والحقائق والادعاءات.",
        "days_90": "تطبيق دورة اعتماد وتحديث مع سجل تغييرات على القنوات ذات الأولوية.",
        "days_180": "ربط المستودع بالأنظمة والفرق ومراجعة نزاهة المعلومات دوريًا.",
    },
    "MCM04": {
        "name_ar": "التنسيق التنظيمي ورحلة العميل",
        "owner_ar": "تجربة العميل والتسويق والعمليات",
        "kpi_ar": "نسبة نقاط الرحلة الحرجة ذات مالك وتسليم موثق دون فقد السياق",
        "days_30": "رسم نقاط الرحلة الحرجة وتحديد مالك الاتصال وآلية التصعيد لكل نقطة.",
        "days_90": "تجربة آلية تسليم موحدة بين التسويق والمبيعات والخدمة على رحلة واحدة.",
        "days_180": "تعميم معايير التنسيق وربطها بقياس الاحتكاك ورضا العميل.",
    },
    "MCM05": {
        "name_ar": "مواءمة الوعد والتجربة والتوقعات",
        "owner_ar": "التسويق والعمليات وتجربة العميل",
        "kpi_ar": "عدد فجوات الوعد والتجربة المغلقة ونسبة الوعود التي اجتازت المراجعة",
        "days_30": "حصر الوعود التسويقية الأعلى أثرًا ومقارنتها بالتجربة التشغيلية الفعلية.",
        "days_90": "إطلاق مراجعة مشتركة للوعود قبل النشر وإغلاق الفجوات ذات الأولوية.",
        "days_180": "ربط بيانات الشكاوى والتوقعات بتطوير الرسائل والخدمة بصورة دورية.",
    },
    "MCM06": {
        "name_ar": "الأدلة والتعلم والاتصال التكيفي",
        "owner_ar": "التحليلات والتسويق",
        "kpi_ar": "نسبة المبادرات التي لها فرضية ومؤشر وانتهت بقرار تحسين موثق",
        "days_30": "تعريف بطاقة قياس موحدة تشمل الفرضية والمؤشر وخط الأساس وقرار المراجعة.",
        "days_90": "تشغيل دورة تعلم شهرية على المبادرات الأعلى إنفاقًا وتوثيق القرارات.",
        "days_180": "بناء مكتبة تعلم وإدماج نتائج التجارب في التخطيط وتخصيص الموارد.",
    },
    "MCM07": {
        "name_ar": "الاستدامة وقابلية التوسع الاتصالي",
        "owner_ar": "العمليات والموارد البشرية والتسويق",
        "kpi_ar": "نسبة العمليات الاتصالية الحرجة الموثقة ولها بديل مدرب",
        "days_30": "تحديد العمليات الحرجة المعتمدة على الأفراد وتوثيق الحد الأدنى لتشغيلها.",
        "days_90": "إنشاء أدلة عمل وقوالب وتدريب بدلاء على العمليات ذات المخاطر الأعلى.",
        "days_180": "تطبيق مراجعة دورية للمعرفة والقدرات تضمن الاستمرارية وقابلية التوسع.",
    },
}

_SECTORS = frozenset(
    {
        "التجزئة والتجارة",
        "الخدمات المهنية",
        "التقنية والاتصالات",
        "الصناعة",
        "السياحة والضيافة",
        "الصحة",
        "التعليم",
        "النقل والخدمات اللوجستية",
        "قطاع آخر",
    }
)
_FIRM_SIZES = frozenset({"MICRO", "SMALL", "MEDIUM"})
_REGIONS = frozenset(
    {
        "الرياض",
        "مكة المكرمة",
        "المنطقة الشرقية",
        "المدينة المنورة",
        "القصيم",
        "عسير",
        "تبوك",
        "حائل",
        "الحدود الشمالية",
        "جازان",
        "نجران",
        "الباحة",
        "الجوف",
    }
)
_RESPONDENT_ROLES = frozenset(
    {
        "مالك / مؤسس",
        "إدارة عليا",
        "مدير تسويق أو اتصال",
        "أخصائي تسويق أو اتصال",
        "خدمة عملاء / تجربة عميل",
        "دور آخر",
    }
)

_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "dimension_code": {"type": "string", "enum": sorted(_PLAYBOOK)},
        "title_ar": {"type": "string", "maxLength": 120},
        "action_ar": {"type": "string", "maxLength": 500},
        "owner_ar": {"type": "string", "maxLength": 120},
        "kpi_ar": {"type": "string", "maxLength": 240},
        "target_ar": {"type": "string", "maxLength": 240},
    },
    "required": ["dimension_code", "title_ar", "action_ar", "owner_ar", "kpi_ar", "target_ar"],
    "additionalProperties": False,
}

# Schema sent to providers.  Generation metadata is attached locally so the
# provider cannot claim that it calculated the scientific result.
AI_PLAN_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
        "summary_ar": {"type": "string", "maxLength": 700},
        "relationship_reading_ar": {"type": "string", "maxLength": 500},
        "priorities": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "dimension_code": {"type": "string", "enum": sorted(_PLAYBOOK)},
                    "name_ar": {"type": "string", "maxLength": 140},
                    "score": {"type": "number", "minimum": 0, "maximum": 100},
                    "rationale_ar": {"type": "string", "maxLength": 400},
                },
                "required": ["dimension_code", "name_ar", "score", "rationale_ar"],
                "additionalProperties": False,
            },
        },
        "roadmap": {
            "type": "object",
            "properties": {
                "days_30": {"type": "array", "minItems": 1, "maxItems": 3, "items": _ACTION_SCHEMA},
                "days_90": {"type": "array", "minItems": 1, "maxItems": 3, "items": _ACTION_SCHEMA},
                "days_180": {"type": "array", "minItems": 1, "maxItems": 3, "items": _ACTION_SCHEMA},
            },
            "required": ["days_30", "days_90", "days_180"],
            "additionalProperties": False,
        },
        "assumptions_ar": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 300},
        },
        "safeguards": {
            "type": "object",
            "properties": {
                "human_review_required": {"type": "boolean"},
                "score_unchanged": {"type": "boolean"},
                "notice_ar": {"type": "string", "maxLength": 500},
            },
            "required": ["human_review_required", "score_unchanged", "notice_ar"],
            "additionalProperties": False,
        },
    },
    "required": [
        "schema_version",
        "summary_ar",
        "relationship_reading_ar",
        "priorities",
        "roadmap",
        "assumptions_ar",
        "safeguards",
    ],
    "additionalProperties": False,
}

IMPROVEMENT_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        **AI_PLAN_CONTENT_SCHEMA["properties"],
        "generation": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "enum": sorted(SUPPORTED_PROVIDERS)},
                "mode": {"type": "string", "enum": ["deterministic", "ai_enhanced"]},
                "status": {"type": "string", "enum": ["ready", "fallback"]},
                "reason_code": {"type": ["string", "null"], "maxLength": 80},
            },
            "required": ["provider", "mode", "status", "reason_code"],
            "additionalProperties": False,
        },
    },
    "required": [*AI_PLAN_CONTENT_SCHEMA["required"], "generation"],
    "additionalProperties": False,
}

_PROVIDER_DEFAULTS = {
    "groq": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "openai/gpt-oss-20b",
        "key_env": "GROQ_API_KEY",
        "host": "api.groq.com",
    },
    "gemini": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-3.5-flash-lite",
        "key_env": "GEMINI_API_KEY",
        "host": "generativelanguage.googleapis.com",
    },
    "ollama": {
        "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
        "model": "qwen3:8b",
        "key_env": "OLLAMA_API_KEY",
        "host": None,
    },
}

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
_SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+\-/=]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:gsk_|sk-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}"),
)


class AIPlanError(RuntimeError):
    """Internal provider error carrying only a non-sensitive machine code."""

    def __init__(self, code: str):
        self.code = _safe_reason_code(code)
        super().__init__(self.code)


def _safe_reason_code(value: Any) -> str:
    code = re.sub(r"[^a-z0-9_\-]", "_", str(value or "provider_error").lower())
    return code[:80] or "provider_error"


def _clean_text(value: Any, maximum: int) -> str:
    """Collapse whitespace and neutralize markup/control characters."""

    text = _CONTROL_CHARACTERS.sub("", str(value or ""))
    text = _WHITESPACE.sub(" ", text).strip().replace("<", "‹").replace(">", "›")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:maximum]


def _score(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return round(max(0.0, min(100.0, number)), 2)


def _rating(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 1 <= number <= 5:
        return None
    return round(number, 2)


def _integer(value: Any, minimum: int, maximum: int) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, number))


def _category(value: Any, allowed: frozenset[str], fallback: str) -> str:
    candidate = _clean_text(value, 80)
    return candidate if candidate in allowed else fallback


def _age_band(value: Any) -> str:
    years = _integer(value, 0, 200)
    if years is None:
        return "غير محدد"
    if years <= 2:
        return "0-2"
    if years <= 5:
        return "3-5"
    if years <= 10:
        return "6-10"
    return "11+"


def _platform_band(value: Any) -> str:
    count = _integer(value, 0, 50)
    if count is None:
        return "غير محدد"
    if count <= 1:
        return "0-1"
    if count <= 3:
        return "2-3"
    if count <= 5:
        return "4-5"
    return "6+"


def _employee_band(value: Any) -> str:
    count = _integer(value, 1, 250_000)
    if count is None:
        return "غير محدد"
    if count <= 5:
        return "1-5"
    if count <= 49:
        return "6-49"
    if count <= 249:
        return "50-249"
    return "250+"


def _team_band(value: Any) -> str:
    count = _integer(value, 0, 250_000)
    if count is None:
        return "غير محدد"
    if count <= 1:
        return "0-1"
    if count <= 5:
        return "2-5"
    return "6+"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _dimension_scores(value: Any, allowed: Mapping[str, str]) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    collected: dict[str, float] = {}
    for row in rows:
        item = _mapping(row)
        code = str(item.get("code") or item.get("dimension_code") or "").upper()
        score = _score(item.get("score"))
        if code in allowed and score is not None:
            collected[code] = score
    return [
        {"code": code, "name_ar": allowed[code], "score": collected[code]}
        for code in sorted(collected)
    ]


def sanitize_assessment_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a de-identified, aggregate-only representation of an MCM result.

    Unknown keys are discarded.  In particular, organization/participant names,
    email addresses, IDs, timestamps, free-text answers, consent values, and raw
    item responses are never retained.  Exact age and platform count are reduced
    to bands.  Dimension names and maturity labels come from local allowlists,
    never from participant-controlled text.

    The function accepts the current :func:`mcm.scoring.score_payload` shape and
    is intentionally tolerant of missing fields so a deterministic fallback can
    still be produced during partial integration.
    """

    source = _mapping(payload)
    scores = _mapping(source.get("scores"))
    mcm = _mapping(scores.get("MCM"))
    smce = _mapping(scores.get("SMCE"))
    enabler_score_source = _mapping(scores.get("ENABLER"))
    mcm_dimensions = _dimension_scores(mcm.get("dimensions"), {code: row["name_ar"] for code, row in _PLAYBOOK.items()})
    smce_dimensions = _dimension_scores(smce.get("dimensions"), _SMCE_DIMENSIONS)
    enabler_dimensions = _dimension_scores(enabler_score_source.get("dimensions"), _ENABLER_DIMENSIONS)

    mcm_total = _score(mcm.get("total"))
    smce_total = _score(smce.get("total"))
    level_source = _mapping(mcm.get("maturity_level"))
    level_code = str(level_source.get("code") or "").upper()
    if level_code not in _MATURITY_LEVELS:
        level_code = ""
    level_order, level_label = _MATURITY_LEVELS.get(level_code, (None, "غير محدد"))

    relationship: dict[str, Any] | None = None
    if mcm_total is not None and smce_total is not None:
        gap = round(smce_total - mcm_total, 2)
        if abs(gap) <= 10:
            alignment = "ALIGNED"
        elif gap < 0:
            alignment = "MATURITY_NOT_FULLY_CONVERTED"
        else:
            alignment = "EFFICIENCY_AHEAD_OF_MATURITY"
        relationship = {
            "model": "MCM_TO_SMCE_PROPOSED_POSITIVE_EFFECT",
            "status": "PROVISIONAL_ASSOCIATION_NOT_CAUSAL",
            "efficiency_minus_maturity": gap,
            "alignment_code": alignment,
        }

    context_source = _mapping(source.get("context"))
    enablers = {row["code"]: row["score"] for row in enabler_dimensions}
    context = {
        "sector_category": _category(context_source.get("sector"), _SECTORS, "غير محدد / آخر"),
        "firm_size": _category(context_source.get("firm_size"), _FIRM_SIZES, "UNSPECIFIED"),
        "firm_age_band": _age_band(context_source.get("firm_age_years")),
        "region_category": _category(context_source.get("region"), _REGIONS, "غير محدد"),
        "social_platform_count_band": _platform_band(context_source.get("social_platform_count")),
        "employee_count_band": _employee_band(context_source.get("employee_count")),
        "social_team_size_band": _team_band(context_source.get("social_team_size")),
        "business_model_category": _clean_text(context_source.get("business_model"), 40) or "غير محدد",
        "regulated_sector": bool(context_source.get("regulated")) if context_source.get("regulated") in {0, 1, False, True} else None,
        "respondent_role_category": _category(
            context_source.get("respondent_role"), _RESPONDENT_ROLES, "غير محدد / آخر"
        ),
        "enablers": enablers,
    }

    return {
        "instrument": {
            "code": "MCM",
            "result_status": "PROVISIONAL_DIAGNOSTIC",
        },
        "scores": {
            "MCM": {
                "total": mcm_total,
                "maturity_level": {
                    "code": level_code or None,
                    "label_ar": level_label,
                    "order": level_order,
                },
                "dimensions": mcm_dimensions,
            },
            "SMCE": {"total": smce_total, "dimensions": smce_dimensions},
            "ENABLER": {"dimensions": enabler_dimensions},
        },
        "context": context,
        "relationship": relationship,
    }


def _ranked_dimensions(sanitized: Mapping[str, Any]) -> list[dict[str, Any]]:
    scores = _mapping(_mapping(sanitized.get("scores")).get("MCM"))
    rows = scores.get("dimensions") if isinstance(scores.get("dimensions"), list) else []
    ranked = [dict(row) for row in rows if _mapping(row).get("code") in _PLAYBOOK]
    if not ranked:
        ranked = [
            {"code": code, "name_ar": details["name_ar"], "score": 0.0}
            for code, details in list(_PLAYBOOK.items())[:3]
        ]
    ranked.sort(key=lambda row: (float(row.get("score") or 0), str(row.get("code"))))
    return ranked[:3]


def _relationship_reading(sanitized: Mapping[str, Any]) -> str:
    relationship = _mapping(sanitized.get("relationship"))
    alignment = relationship.get("alignment_code")
    if alignment == "ALIGNED":
        return "تظهر درجتا النضج والكفاءة الاتصالية تقاربًا تشخيصيًا، مع بقاء العلاقة المقترحة غير سببية وقيد التحقق العلمي."
    if alignment == "MATURITY_NOT_FULLY_CONVERTED":
        return "تتأخر الكفاءة الاتصالية عن النضج المؤسسي؛ تركز الخطة على تحويل القدرات القائمة إلى أداء يومي قابل للقياس، دون ادعاء سببية."
    if alignment == "EFFICIENCY_AHEAD_OF_MATURITY":
        return "تتقدم الكفاءة الاتصالية على مستوى الاستدامة؛ تركز الخطة على تثبيت الممارسات وتقليل اعتمادها على الأفراد، دون ادعاء سببية."
    return "لا تتوفر بيانات كافية لقراءة العلاقة بين النضج والكفاءة؛ تبقى الخطة موجهة إلى فجوات أبعاد النضج المتاحة."


def _assumptions(sanitized: Mapping[str, Any]) -> list[str]:
    enablers = _mapping(_mapping(sanitized.get("context")).get("enablers"))
    labels = _ENABLER_DIMENSIONS
    assumptions = [
        f"يتطلب التنفيذ معالجة محدودية {labels[key]} بالتوازي مع إجراءات الخطة."
        for key, value in enablers.items()
        if isinstance(value, (int, float)) and value < 50
    ]
    if not assumptions:
        assumptions.append("تعتمد الخطة على الدرجات المجمعة والسياق المصنف المتاح وقت إنشاء التقرير.")
    assumptions.append("الأهداف التشغيلية المقترحة تحتاج ضبط خط أساس واعتماد المالك قبل التنفيذ.")
    return assumptions[:5]


def _fallback_action(code: str, phase: str) -> dict[str, Any]:
    details = _PLAYBOOK[code]
    phase_targets = {
        "days_30": "اعتماد المخرج الأساسي وتوثيق خط البداية خلال 30 يومًا.",
        "days_90": "تشغيل الإجراء تجريبيًا ومراجعة المؤشر مقارنة بخط الأساس خلال 90 يومًا.",
        "days_180": "تثبيت الممارسة وقياس أثرها واعتماد دورة التحسين خلال 180 يومًا.",
    }
    return {
        "dimension_code": code,
        "title_ar": details["name_ar"],
        "action_ar": details[phase],
        "owner_ar": details["owner_ar"],
        "kpi_ar": details["kpi_ar"],
        "target_ar": phase_targets[phase],
    }


def deterministic_improvement_plan(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a deterministic, audit-friendly 30/90/180-day plan.

    This callable is the mandatory fallback for all providers and performs no
    network I/O.  Given the same aggregate payload it returns the same plan.  It
    prioritizes the three lowest available MCM dimension scores and uses the
    local, versioned playbook above; it never changes scores or classification.
    """

    sanitized = sanitize_assessment_payload(payload)
    ranked = _ranked_dimensions(sanitized)
    level = _mapping(_mapping(_mapping(sanitized.get("scores")).get("MCM")).get("maturity_level"))
    names = "، ".join(_PLAYBOOK[row["code"]]["name_ar"] for row in ranked)
    level_label = level.get("label_ar") or "غير محدد"
    summary = (
        f"المنشأة مصنفة تشخيصيًا عند مستوى «{level_label}». تركز دورة التحسين الأولى على: {names}. "
        "يبدأ التنفيذ بتأسيس الضوابط، ثم تجربة الممارسات، ثم مأسستها وقياس أثرها."
    )
    priorities = []
    for row in ranked:
        code = row["code"]
        current = _score(row.get("score"), 0.0) or 0.0
        level_order = int(level.get("order") or 1)
        target = float(level_order * 20 if level_order < 5 else 100)
        gap = round(max(0.0, target - current), 1)
        priorities.append(
            {
                "dimension_code": code,
                "name_ar": _PLAYBOOK[code]["name_ar"],
                "score": current,
                "rationale_ar": (
                    f"الدرجة الحالية {current:.1f} من 100، والفجوة التشخيصية إلى عتبة المرحلة التالية {target:.0f} تبلغ {gap:.1f} نقطة."
                ),
            }
        )
    roadmap = {
        phase: [_fallback_action(row["code"], phase) for row in ranked]
        for phase in ("days_30", "days_90", "days_180")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_ar": summary,
        "relationship_reading_ar": _relationship_reading(sanitized),
        "priorities": priorities,
        "roadmap": roadmap,
        "assumptions_ar": _assumptions(sanitized),
        "safeguards": {
            "human_review_required": True,
            "score_unchanged": True,
            "notice_ar": _SAFETY_NOTICE,
        },
        "generation": {
            "provider": "off",
            "mode": "deterministic",
            "status": "ready",
            "reason_code": None,
        },
    }


def _required_text(value: Any, maximum: int, error_code: str) -> str:
    text = _clean_text(value, maximum)
    if not text:
        raise AIPlanError(error_code)
    return text


def _validate_provider_content(raw: Any, sanitized: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize untrusted model JSON using only stdlib code."""

    content = _mapping(raw)
    if content.get("schema_version") != SCHEMA_VERSION:
        raise AIPlanError("invalid_schema_version")

    available = {
        row["code"]: float(row.get("score") or 0)
        for row in _ranked_dimensions(sanitized)
    }
    # A provider may select another measured MCM dimension, but it may not
    # invent codes or alter their scientific scores.
    all_measured = {
        row["code"]: float(row.get("score") or 0)
        for row in _mapping(_mapping(sanitized.get("scores")).get("MCM")).get("dimensions", [])
        if _mapping(row).get("code") in _PLAYBOOK
    }
    if all_measured:
        available = all_measured

    raw_priorities = content.get("priorities")
    if not isinstance(raw_priorities, list) or not 1 <= len(raw_priorities) <= 3:
        raise AIPlanError("invalid_priorities")
    priorities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_priority in raw_priorities:
        priority = _mapping(raw_priority)
        code = str(priority.get("dimension_code") or "").upper()
        if code not in available or code in seen:
            raise AIPlanError("invalid_priority_dimension")
        seen.add(code)
        priorities.append(
            {
                "dimension_code": code,
                "name_ar": _PLAYBOOK[code]["name_ar"],
                "score": round(available[code], 2),
                "rationale_ar": _required_text(priority.get("rationale_ar"), 400, "invalid_priority_rationale"),
            }
        )

    raw_roadmap = _mapping(content.get("roadmap"))
    roadmap: dict[str, list[dict[str, Any]]] = {}
    for phase in ("days_30", "days_90", "days_180"):
        raw_actions = raw_roadmap.get(phase)
        if not isinstance(raw_actions, list) or not 1 <= len(raw_actions) <= 3:
            raise AIPlanError("invalid_roadmap")
        actions: list[dict[str, Any]] = []
        for raw_action in raw_actions:
            action = _mapping(raw_action)
            code = str(action.get("dimension_code") or "").upper()
            if code not in available:
                raise AIPlanError("invalid_action_dimension")
            actions.append(
                {
                    "dimension_code": code,
                    "title_ar": _required_text(action.get("title_ar"), 120, "invalid_action_title"),
                    "action_ar": _required_text(action.get("action_ar"), 500, "invalid_action_text"),
                    "owner_ar": _required_text(action.get("owner_ar"), 120, "invalid_action_owner"),
                    "kpi_ar": _required_text(action.get("kpi_ar"), 240, "invalid_action_kpi"),
                    "target_ar": _required_text(action.get("target_ar"), 240, "invalid_action_target"),
                }
            )
        roadmap[phase] = actions

    raw_assumptions = content.get("assumptions_ar")
    if not isinstance(raw_assumptions, list) or len(raw_assumptions) > 5:
        raise AIPlanError("invalid_assumptions")
    assumptions = [
        _required_text(item, 300, "invalid_assumption")
        for item in raw_assumptions
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "summary_ar": _required_text(content.get("summary_ar"), 700, "invalid_summary"),
        "relationship_reading_ar": _required_text(
            content.get("relationship_reading_ar"), 500, "invalid_relationship_reading"
        ),
        "priorities": priorities,
        "roadmap": roadmap,
        "assumptions_ar": assumptions,
        # These values are server-owned regardless of what the model returned.
        "safeguards": {
            "human_review_required": True,
            "score_unchanged": True,
            "notice_ar": _SAFETY_NOTICE,
        },
    }


def _endpoint(provider: str, base_url: str | None) -> str:
    defaults = _PROVIDER_DEFAULTS[provider]
    candidate = (base_url or os.environ.get("MCM_AI_BASE_URL") or defaults["endpoint"]).strip()
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AIPlanError("invalid_provider_endpoint")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AIPlanError("invalid_provider_endpoint")
    if provider in {"groq", "gemini"}:
        if parsed.scheme != "https" or parsed.hostname != defaults["host"] or parsed.port not in {None, 443}:
            raise AIPlanError("untrusted_cloud_endpoint")
    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _provider_model(provider: str, model: str | None) -> str:
    value = model or os.environ.get("MCM_AI_MODEL") or _PROVIDER_DEFAULTS[provider]["model"]
    cleaned = _clean_text(value, 120)
    if not cleaned or not re.fullmatch(r"[A-Za-z0-9._:/\-]+", cleaned):
        raise AIPlanError("invalid_model")
    return cleaned


def _provider_key(provider: str, api_key: str | None) -> str | None:
    key_env = _PROVIDER_DEFAULTS[provider]["key_env"]
    key = api_key if api_key is not None else os.environ.get("MCM_AI_API_KEY") or os.environ.get(key_env)
    if provider in {"groq", "gemini"} and not key:
        raise AIPlanError("missing_api_key")
    return key


def _timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    if not math.isfinite(timeout):
        timeout = DEFAULT_TIMEOUT_SECONDS
    return max(2.0, min(30.0, timeout))


def _prompt(sanitized: Mapping[str, Any]) -> tuple[str, str]:
    system = (
        "أنت مستشار تطوير مؤسسي متخصص في النضج الاتصالي التسويقي للمنشآت الصغيرة والمتوسطة. "
        "خصص خطة عملية باللغة العربية دون تغيير أي درجة أو مرحلة، ودون استنتاج علاقة سببية بين MCM وSMCE. "
        "لا تطلب أو تستنتج هوية المنشأة أو المشارك. أعِد JSON فقط مطابقًا للمخطط المحدد، واجعل الإجراءات قابلة للقياس "
        "ومناسبة لموارد منشأة صغيرة أو متوسطة، مع اشتراط المراجعة البشرية."
    )
    user = json.dumps(
        {
            "task": "إنشاء خطة تحسين مخصصة من النتائج المجمعة المجهولة أدناه.",
            "aggregate_result": sanitized,
            "required_output_schema": AI_PLAN_CONTENT_SCHEMA,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return system, user


def _request_payload(provider: str, model: str, sanitized: Mapping[str, Any]) -> bytes:
    system, user = _prompt(sanitized)
    response_format: dict[str, Any]
    if provider == "groq":
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "mcm_improvement_plan",
                "strict": True,
                "schema": AI_PLAN_CONTENT_SCHEMA,
            },
        }
    elif provider == "gemini":
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "mcm_improvement_plan",
                "schema": AI_PLAN_CONTENT_SCHEMA,
            },
        }
    else:
        # Ollama's OpenAI-compatible endpoint broadly supports JSON object mode;
        # the full schema remains in the prompt and is enforced locally.
        response_format = {"type": "json_object"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 2500,
        "response_format": response_format,
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _http_error_code(status: int) -> str:
    if status in {401, 403}:
        return "provider_auth_failed"
    if status == 429:
        return "provider_rate_limited"
    if status in {408, 504}:
        return "provider_timeout"
    if status >= 500:
        return "provider_unavailable"
    if status >= 400:
        return "provider_rejected_request"
    return "provider_http_error"


def _extract_json_content(response_data: bytes) -> Any:
    try:
        envelope = json.loads(response_data.decode("utf-8"))
        content = envelope["choices"][0]["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise AIPlanError("invalid_provider_response") from exc
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, Mapping)
        )
    if isinstance(content, Mapping):
        return dict(content)
    if not isinstance(content, str):
        raise AIPlanError("invalid_provider_content")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIPlanError("invalid_provider_json") from exc


def _call_provider(
    provider: str,
    sanitized: Mapping[str, Any],
    *,
    api_key: str | None,
    model: str | None,
    base_url: str | None,
    timeout: float,
) -> dict[str, Any]:
    endpoint = _endpoint(provider, base_url)
    selected_model = _provider_model(provider, model)
    selected_key = _provider_key(provider, api_key)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "mcm-improvement-plans/1.0",
    }
    if selected_key:
        headers["Authorization"] = f"Bearer {selected_key}"
    request = urllib.request.Request(
        endpoint,
        data=_request_payload(provider, selected_model, sanitized),
        headers=headers,
        method="POST",
    )
    response = None
    try:
        response = urllib.request.urlopen(request, timeout=_timeout(timeout))
        response_data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(response_data) > MAX_RESPONSE_BYTES:
            raise AIPlanError("provider_response_too_large")
    except urllib.error.HTTPError as exc:
        raise AIPlanError(_http_error_code(int(exc.code))) from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        reason = "provider_timeout" if isinstance(exc, (socket.timeout, TimeoutError)) else "provider_network_error"
        raise AIPlanError(reason) from exc
    except OSError as exc:
        raise AIPlanError("provider_network_error") from exc
    finally:
        if response is not None:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    return _validate_provider_content(_extract_json_content(response_data), sanitized)


def _redact_exact_secret(value: Any, secret: str | None) -> Any:
    """Defense in depth: recursively remove an explicitly supplied secret."""

    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, list):
        return [_redact_exact_secret(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: _redact_exact_secret(item, secret) for key, item in value.items()}
    return value


def generate_improvement_plan(
    payload: Mapping[str, Any] | None,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Generate an optional AI-enhanced plan with a deterministic fallback.

    ``provider`` defaults to ``MCM_AI_PROVIDER`` and ultimately to ``off``.
    When it is ``off``, this function returns before endpoint/key resolution and
    therefore performs no network I/O.  Provider failures never expose response
    bodies, URLs, credentials, or exception messages; the caller receives only a
    stable ``reason_code`` and a complete deterministic plan.

    The returned dictionary always follows :data:`IMPROVEMENT_PLAN_SCHEMA`.
    """

    selected = str(provider if provider is not None else os.environ.get("MCM_AI_PROVIDER", "off")).strip().lower()
    sanitized = sanitize_assessment_payload(payload)
    fallback = deterministic_improvement_plan(sanitized)

    if selected == "off":
        return fallback
    if selected not in SUPPORTED_PROVIDERS:
        fallback["generation"] = {
            "provider": "off",
            "mode": "deterministic",
            "status": "fallback",
            "reason_code": "unsupported_provider",
        }
        return fallback

    try:
        enhanced = _call_provider(
            selected,
            sanitized,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
        )
        enhanced["generation"] = {
            "provider": selected,
            "mode": "ai_enhanced",
            "status": "ready",
            "reason_code": None,
        }
        return _redact_exact_secret(enhanced, api_key)
    except AIPlanError as exc:
        fallback["generation"] = {
            "provider": selected,
            "mode": "deterministic",
            "status": "fallback",
            "reason_code": exc.code,
        }
        return _redact_exact_secret(fallback, api_key)


__all__ = [
    "AIPlanError",
    "AI_PLAN_CONTENT_SCHEMA",
    "IMPROVEMENT_PLAN_SCHEMA",
    "SCHEMA_VERSION",
    "SUPPORTED_PROVIDERS",
    "deterministic_improvement_plan",
    "generate_improvement_plan",
    "sanitize_assessment_payload",
]
