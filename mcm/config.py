from __future__ import annotations

import os
import secrets
from pathlib import Path

from .instrument_v02 import (
    DIMENSIONS as INSTRUMENT_DIMENSIONS,
    ITEMS as INSTRUMENT_ITEMS,
    MATURITY_LEVELS as INSTRUMENT_MATURITY_LEVELS,
    METADATA as INSTRUMENT_METADATA,
    PROFILE_FIELDS as INSTRUMENT_PROFILE_FIELDS,
    SCALE_DEFINITIONS,
)


ROOT = Path(__file__).resolve().parent.parent


def _load_local_env() -> None:
    """Load a small KEY=VALUE .env file without overriding real environment values."""
    env_file = ROOT / ".env"
    if not env_file.is_file() or os.environ.get("VERCEL"):
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value)


_load_local_env()

ENVIRONMENT = os.environ.get("MCM_ENV", "development").strip().lower()
DATABASE_URL = (
    os.environ.get("MCM_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or ""
).strip()
DATABASE_MIGRATION_URL = (
    os.environ.get("MCM_DATABASE_MIGRATION_URL")
    or os.environ.get("POSTGRES_URL_NON_POOLING")
    or DATABASE_URL
).strip()
if DATABASE_URL and not DATABASE_URL.startswith(("postgresql://", "postgres://")):
    raise RuntimeError("MCM_DATABASE_URL must be a PostgreSQL connection URL")
if DATABASE_MIGRATION_URL and not DATABASE_MIGRATION_URL.startswith(("postgresql://", "postgres://")):
    raise RuntimeError("MCM_DATABASE_MIGRATION_URL must be a PostgreSQL connection URL")
DB_BACKEND = "postgresql" if DATABASE_URL else "sqlite"
DB_PATH = Path(
    os.environ.get(
        "MCM_DB_PATH",
        "/tmp/mcm.sqlite3" if os.environ.get("VERCEL") else str(ROOT / "mcm.sqlite3"),
    )
)
HOST = os.environ.get("MCM_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
SESSION_TTL = int(os.environ.get("MCM_SESSION_TTL", str(8 * 60 * 60)))
INVITATION_TTL = int(os.environ.get("MCM_INVITATION_TTL", str(7 * 86_400)))
RESET_TTL = int(os.environ.get("MCM_RESET_TTL", "1800"))
ALLOWED_ORIGIN = os.environ.get("MCM_ALLOWED_ORIGIN", "same-origin")
MAX_DOCX_BYTES = int(os.environ.get("MCM_MAX_DOCX_BYTES", str(8 * 1024 * 1024)))
AI_PROVIDER = os.environ.get("MCM_AI_PROVIDER", "off").strip().lower()
if AI_PROVIDER not in {"off", "groq", "gemini", "ollama"}:
    AI_PROVIDER = "off"
AI_MODEL = os.environ.get("MCM_AI_MODEL", "").strip() or None
AI_BASE_URL = os.environ.get("MCM_AI_BASE_URL", "").strip() or None
AI_TIMEOUT = max(3.0, min(30.0, float(os.environ.get("MCM_AI_TIMEOUT", "15"))))
AI_CLOUD_KEY_CONFIGURED = bool(
    os.environ.get("MCM_AI_API_KEY")
    or (AI_PROVIDER == "groq" and os.environ.get("GROQ_API_KEY"))
    or (AI_PROVIDER == "gemini" and os.environ.get("GEMINI_API_KEY"))
)
AI_AVAILABLE = AI_PROVIDER == "ollama" or (AI_PROVIDER in {"groq", "gemini"} and AI_CLOUD_KEY_CONFIGURED)

PLATFORM_ADMIN_EMAIL = os.environ.get("MCM_ADMIN_EMAIL", "hmsomili@gmail.com").lower()
PLATFORM_ADMIN_NAME = os.environ.get("MCM_ADMIN_NAME", "مدير المنصة")
PLATFORM_ADMIN_PASSWORD_CONFIGURED = bool(os.environ.get("MCM_ADMIN_PASSWORD"))
PLATFORM_ADMIN_PASSWORD = os.environ.get("MCM_ADMIN_PASSWORD") or secrets.token_urlsafe(32)
EXPOSE_DEV_RESET_TOKEN = os.environ.get("MCM_EXPOSE_DEV_RESET_TOKEN", "1" if ENVIRONMENT != "production" and not os.environ.get("VERCEL") else "0") == "1"
BOOTSTRAP_ORG_NAME = os.environ.get("MCM_BOOTSTRAP_ORG_NAME", "إدارة مقياس النضج الاتصالي التسويقي")
EPHEMERAL_STORAGE = not DATABASE_URL and bool(os.environ.get("VERCEL")) and str(DB_PATH).startswith("/tmp/")
STORAGE_MODE = "supabase-postgresql" if DATABASE_URL else ("ephemeral-demo" if EPHEMERAL_STORAGE else "sqlite-local")
ALLOW_REGISTRATION = os.environ.get("MCM_ALLOW_REGISTRATION", "0") == "1"

if ENVIRONMENT == "production":
    if len(PLATFORM_ADMIN_PASSWORD) < 10:
        raise RuntimeError("MCM_ADMIN_PASSWORD must be a private secret of at least 10 characters in production")
    if not DATABASE_URL and str(DB_PATH).startswith("/tmp/"):
        raise RuntimeError("MCM_DATABASE_URL must point to durable PostgreSQL storage in production")
    if EXPOSE_DEV_RESET_TOKEN:
        raise RuntimeError("MCM_EXPOSE_DEV_RESET_TOKEN must be disabled in production")

ROLE_ALIASES = {
    "admin": "COMPANY_ADMIN",
    "assessor": "CONSULTANT",
    "respondent": "COMPANY_RESPONDENT",
    "company_respondent": "COMPANY_RESPONDENT",
    "company_admin": "COMPANY_ADMIN",
    "consultant": "CONSULTANT",
    "researcher": "RESEARCHER",
    "super_admin": "SUPER_ADMIN",
}
ROLES = tuple(sorted(set(ROLE_ALIASES.values())))

# Platform roles act across every organisation: they reach the consultation
# workspace, the research console or platform administration. Only the platform
# manager may grant them. Company roles are scoped to one organisation and a
# company administrator may grant those within their own organisation.
#
# Participants are deliberately not in either set. A direct participant answers
# the instrument through a scoped session and never holds an account, so taking
# the assessment can never become a route to an account of any kind.
PLATFORM_ROLES = ("SUPER_ADMIN", "CONSULTANT", "RESEARCHER")
COMPANY_ROLES = ("COMPANY_ADMIN", "COMPANY_RESPONDENT")
# The single role self-registration may ever produce, when it is enabled at all.
SELF_REGISTRATION_ROLE = "COMPANY_ADMIN"

def _dimension_tuples(construct: str):
    return [
        (row["code"], row["name_ar"], row["name_en"])
        for row in INSTRUMENT_DIMENSIONS
        if row["construct"] == construct
    ]


MCM_DIMENSIONS = _dimension_tuples("MCM")
SMCE_DIMENSIONS = _dimension_tuples("SMCE")
ENABLER_DIMENSIONS = _dimension_tuples("ENABLER")
OUTCOME_DIMENSIONS = _dimension_tuples("OUTCOME")
MATURITY_LEVELS = [
    (
        row["code"], row["label_ar"], row["label_en"], row["min_score"],
        row["max_score"], row["level_order"],
    )
    for row in INSTRUMENT_MATURITY_LEVELS
]

# Compatibility views used by older maintenance utilities. The database seed
# uses INSTRUMENT_ITEMS directly so item wording, English labels, scale type,
# source references and ordering remain exactly tied to scientific v0.2.
ITEM_PROMPTS = {
    code: [row["prompt_ar"] for row in INSTRUMENT_ITEMS if row["dimension_code"] == code]
    for code, _, _ in MCM_DIMENSIONS + SMCE_DIMENSIONS + ENABLER_DIMENSIONS + OUTCOME_DIMENSIONS
}

RECOMMENDATIONS = {
    "MCM01": ("حوكمة القرار الاتصالي", "اعتماد ميثاق حوكمة يربط الأهداف والقرارات والمالكين.", "المدير التنفيذي", "نسبة المبادرات المرتبطة بهدف استراتيجي"),
    "MCM02": ("نظام ذكاء أصحاب المصلحة", "إنشاء سجل شرائح ورؤى يُحدّث شهريًا ويغذي التخطيط.", "الاستراتيجية", "نسبة الشرائح المحدثة خلال 90 يومًا"),
    "MCM03": ("مصدر حقيقة موحّد", "إنشاء مستودع حقائق ورسائل مع مالك وتاريخ مراجعة واعتماد.", "التسويق + المنتج", "نسبة المواد المرتبطة بمصدر معتمد"),
    "MCM04": ("حوكمة رحلة العميل", "توحيد خريطة الرحلة وآلية تسليم الحالات بين الفرق.", "تجربة العميل", "نسبة الحالات المحوّلة دون فقد السياق"),
    "MCM05": ("اختبار الوعد مقابل التجربة", "مراجعة الوعود التسويقية مع التشغيل والخدمة قبل الإطلاق.", "التسويق + العمليات", "عدد فجوات الوعد المغلقة"),
    "MCM06": ("دورة قياس وتعلم", "ربط كل مبادرة بفرضية ومؤشر وقرار مراجعة موثق.", "التحليلات", "نسبة المبادرات التي أنتجت قرار تحسين"),
    "MCM07": ("استدامة المعرفة", "توثيق العمليات الحرجة وبناء تدريب وتسليم يقللان الاعتماد على الأفراد.", "العمليات", "نسبة العمليات ذات بديل موثق"),
}

DIAGNOSTIC_RULES = [
    ("INFORMATION_INTEGRITY_RISK", "مخاطر نزاهة المعلومات", "MCM03", "lt", 50, "HIGH", 0.90),
    ("STRATEGY_EXECUTION_GAP", "فجوة الاستراتيجية والتنفيذ", "MCM01:MCM04", "gap_gt", 15, "HIGH", 0.86),
    ("PROMISE_EXPERIENCE_GAP", "فجوة الوعد والتجربة", "MCM01:MCM05", "gap_gt", 15, "HIGH", 0.86),
    ("DATA_WITHOUT_LEARNING", "بيانات دون تعلم", "MCM06", "lt", 50, "MEDIUM", 0.82),
    ("KEY_PERSON_DEPENDENCY", "الاعتماد على أفراد محوريين", "MCM07", "lt", 50, "HIGH", 0.88),
    ("JOURNEY_FRAGMENTATION", "تجزؤ رحلة العميل", "MCM04", "lt", 50, "HIGH", 0.88),
    ("COMMUNICATION_FRICTION", "خفض معوقات الاستجابة", "SMCE01:SMCE03", "average_lt", 55, "MEDIUM", 0.80),
    ("STAKEHOLDER_MISALIGNMENT", "عدم مواءمة أصحاب المصلحة", "MCM02", "lt", 50, "MEDIUM", 0.84),
    ("REACTIVE_COMMUNICATION", "اتصال تفاعلي قصير الأجل", "MCM01:MCM06", "average_lt", 45, "HIGH", 0.83),
    ("SCALABILITY_RISK", "مخاطر قابلية التوسع", "MCM07:SMCE04", "average_lt", 50, "HIGH", 0.87),
]


def normalize_role(value: str | None) -> str:
    role = str(value or "").strip()
    return ROLE_ALIASES.get(role.lower(), role.upper())
