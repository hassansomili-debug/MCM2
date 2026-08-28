from __future__ import annotations

import os
import secrets
from pathlib import Path


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

PLATFORM_ADMIN_EMAIL = os.environ.get("MCM_ADMIN_EMAIL", "admin@nudj.local").lower()
PLATFORM_ADMIN_PASSWORD = os.environ.get("MCM_ADMIN_PASSWORD") or (secrets.token_urlsafe(32) if os.environ.get("VERCEL") else "Nudj-Admin-2026!")
DEMO_EMAIL = os.environ.get("MCM_DEMO_EMAIL", "sara@example.com").lower()
DEMO_PASSWORD = os.environ.get("MCM_DEMO_PASSWORD", "ChangeMe-2026")
SEED_DEMO = os.environ.get("MCM_SEED_DEMO", "1" if ENVIRONMENT != "production" else "0") == "1"
EXPOSE_DEV_RESET_TOKEN = os.environ.get("MCM_EXPOSE_DEV_RESET_TOKEN", "1" if ENVIRONMENT != "production" and not os.environ.get("VERCEL") else "0") == "1"
BOOTSTRAP_ORG_NAME = os.environ.get("MCM_BOOTSTRAP_ORG_NAME", "إدارة منصة نضج" if ENVIRONMENT == "production" else "أفق الرقمية")
EPHEMERAL_STORAGE = bool(os.environ.get("VERCEL")) and str(DB_PATH).startswith("/tmp/")
ALLOW_REGISTRATION = os.environ.get("MCM_ALLOW_REGISTRATION", "0" if EPHEMERAL_STORAGE else "1") == "1"
PUBLIC_DEMO = os.environ.get("MCM_PUBLIC_DEMO", "1" if SEED_DEMO else "0") == "1"

if ENVIRONMENT == "production":
    if PLATFORM_ADMIN_PASSWORD == "Nudj-Admin-2026!" or len(PLATFORM_ADMIN_PASSWORD) < 16:
        raise RuntimeError("MCM_ADMIN_PASSWORD must be a non-default secret of at least 16 characters in production")
    if str(DB_PATH).startswith("/tmp/"):
        raise RuntimeError("MCM_DB_PATH must point to persistent storage in production")
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

MCM_DIMENSIONS = [
    ("MCM01", "الحوكمة والتوجيه الاستراتيجي", "Strategic governance and direction"),
    ("MCM02", "ذكاء أصحاب المصلحة والسياق", "Stakeholder and context intelligence"),
    ("MCM03", "حوكمة المعلومات والنزاهة", "Information governance and integrity"),
    ("MCM04", "التنسيق ورحلة العميل", "Coordination and customer journey"),
    ("MCM05", "مواءمة الوعد والتجربة", "Promise and experience alignment"),
    ("MCM06", "الأدلة والتعلم التكيفي", "Evidence and adaptive learning"),
    ("MCM07", "المأسسة وقابلية التوسع", "Institutionalisation and scalability"),
]

SMCE_DIMENSIONS = [
    ("SMCE01", "الاستجابة والحل", "Responsiveness and resolution"),
    ("SMCE02", "جودة التفاعل", "Interaction quality"),
    ("SMCE03", "كفاءة الفعل", "Action efficiency"),
    ("SMCE04", "انخفاض الاحتكاك الاتصالي", "Low communication friction"),
    ("SMCE05", "كفاءة الموارد وتحقيق الأهداف", "Resource and goal efficiency"),
]

ENABLER_DIMENSIONS = [
    ("ENA01", "دعم القيادة", "Leadership support"),
    ("ENA02", "الموارد والقدرات", "Resources and capabilities"),
    ("ENA03", "البنية التقنية", "Technology foundation"),
    ("ENA04", "الثقافة التعاونية", "Collaborative culture"),
]

OUTCOME_DIMENSIONS = [
    ("OUT01", "رضا أصحاب المصلحة", "Stakeholder satisfaction"),
    ("OUT02", "الثقة والسمعة", "Trust and reputation"),
    ("OUT03", "كفاءة الإنفاق", "Spend efficiency"),
    ("OUT04", "أثر الأعمال", "Business impact"),
]

MATURITY_LEVELS = [
    ("FOUNDATIONAL", "تأسيسي", "Foundational", 0.0, 20.0, 1),
    ("EMERGING", "ناشئ", "Emerging", 20.0, 40.0, 2),
    ("STRUCTURED", "منظّم", "Structured", 40.0, 60.0, 3),
    ("INTEGRATED", "متكامل", "Integrated", 60.0, 80.0, 4),
    ("OPTIMIZED", "متقدم", "Optimized", 80.0, 100.01, 5),
]

ITEM_PROMPTS = {
    "MCM01": [
        "ترتبط أهداف الاتصال مباشرة بالأهداف الاستراتيجية للمؤسسة.",
        "توجد جهة واضحة تملك قرارات الاتصال التسويقي وتتابعها.",
        "تُترجم الاستراتيجية إلى أولويات ومؤشرات اتصال قابلة للقياس.",
        "تُراجع قرارات الاتصال دوريًا على مستوى القيادة.",
    ],
    "MCM02": [
        "تُحدّث المؤسسة فهمها لاحتياجات أصحاب المصلحة بانتظام.",
        "تُستخدم بيانات السوق والسياق في التخطيط للاتصال.",
        "تُميّز الرسائل بحسب شرائح أصحاب المصلحة واحتياجاتهم.",
        "تُرصد التغيرات الخارجية وتنعكس على القرارات الاتصالية.",
    ],
    "MCM03": [
        "توجد مصادر معلومات معتمدة وموحدة للرسائل والحقائق.",
        "تُراجع دقة المحتوى قبل نشره عبر القنوات.",
        "توجد ملكية واضحة لتحديث المعلومات الاتصالية.",
        "يمكن تتبع النسخ والاعتمادات والتغييرات على المحتوى.",
    ],
    "MCM04": [
        "تعمل الفرق المختلفة وفق رحلة عميل واتصال مشتركة.",
        "تنتقل معلومات العميل بسلاسة بين نقاط التماس.",
        "توجد آلية لمعالجة التعارض بين القنوات والفرق.",
        "تُصمم الرسائل والخدمات كتجربة مترابطة لا كأنشطة منفصلة.",
    ],
    "MCM05": [
        "يتوافق الوعد التسويقي مع التجربة الفعلية التي يتلقاها العميل.",
        "تُستخدم ملاحظات العملاء لتصحيح الفجوة بين الوعد والتجربة.",
        "تتسق اللغة والنبرة مع مستوى الخدمة الفعلي.",
        "تُختبر الرسائل مقابل قدرة المؤسسة على الوفاء بها.",
    ],
    "MCM06": [
        "تُقاس النتائج الاتصالية بمؤشرات تتجاوز حجم النشاط.",
        "تُستخدم الأدلة لتعديل الحملات والرسائل أثناء التنفيذ.",
        "توجد دورات تعلم موثقة بعد المبادرات الاتصالية.",
        "ترتبط التحليلات بقرارات ومالكين ومواعيد متابعة.",
    ],
    "MCM07": [
        "تعتمد جودة الاتصال على عمليات مؤسسية لا على أفراد بعينهم.",
        "توجد أدلة عمل وقوالب ومعايير قابلة للتكرار.",
        "يمكن توسيع النشاط الاتصالي دون تراجع الاتساق والجودة.",
        "تُبنى القدرات عبر التدريب ونقل المعرفة والتعاقب.",
    ],
    "SMCE01": [
        "تستجيب فرق التواصل الاجتماعي ضمن أزمنة خدمة محددة.",
        "تُنقل الحالات المعقدة إلى الجهة المناسبة دون فقد السياق.",
        "تُغلق الاستفسارات والشكاوى بحل واضح ومتابعة مناسبة.",
    ],
    "SMCE02": [
        "تعكس التفاعلات الرقمية فهمًا حقيقيًا لسياق العميل.",
        "تحافظ الردود على نبرة إنسانية ومتسقة مع العلامة.",
        "تتكيّف جودة الحوار مع اختلاف القناة والجمهور.",
    ],
    "SMCE03": [
        "توجد صلاحيات وأدوات تمكّن الفريق من اتخاذ الإجراء بسرعة.",
        "تقل التحويلات غير الضرورية بين الفرق عند خدمة العميل.",
        "تُستخدم الأتمتة دون الإضرار بدقة الاستجابة أو إنسانيتها.",
    ],
    "SMCE04": [
        "يصل العميل إلى المعلومة أو الجهة المطلوبة بأقل عدد ممكن من الخطوات.",
        "تنخفض الحاجة إلى تكرار المعلومات عند الانتقال بين القنوات والفرق.",
        "تُرصد نقاط الاحتكاك الاتصالي وتُعالج بصورة منتظمة.",
    ],
    "SMCE05": [
        "تُستخدم الموارد الاتصالية بما يتناسب مع الأولويات والأثر المتوقع.",
        "يمكن ربط أنشطة التواصل الاجتماعي بأهداف محددة وقابلة للقياس.",
        "تُعاد موازنة الوقت والميزانية استنادًا إلى النتائج الفعلية.",
    ],
    "ENA01": ["توفر القيادة رعاية واضحة لتطوير الاتصال المؤسسي."],
    "ENA02": ["تتوفر موارد ومهارات كافية لتنفيذ خطط الاتصال."],
    "ENA03": ["تدعم الأنظمة التقنية جمع البيانات وتبادلها بأمان."],
    "ENA04": ["تشجع الثقافة الداخلية التعاون وتبادل المعرفة بين الفرق."],
    "OUT01": ["كيف تقيّم رضا أصحاب المصلحة عن الاتصال؟"],
    "OUT02": ["كيف تقيّم أثر الاتصال على الثقة والسمعة؟"],
    "OUT03": ["كيف تقيّم كفاءة استخدام ميزانية الاتصال؟"],
    "OUT04": ["كيف تقيّم مساهمة الاتصال في نتائج الأعمال؟"],
}

RECOMMENDATIONS = {
    "MCM01": ("حوكمة القرار الاتصالي", "اعتماد ميثاق حوكمة يربط الأهداف والقرارات والمالكين.", "المدير التنفيذي", "نسبة المبادرات المرتبطة بهدف استراتيجي"),
    "MCM02": ("نظام ذكاء أصحاب المصلحة", "إنشاء سجل شرائح ورؤى يُحدّث شهريًا ويغذي التخطيط.", "الاستراتيجية", "نسبة الشرائح المحدثة خلال 90 يومًا"),
    "MCM03": ("مصدر حقيقة موحّد", "إنشاء مستودع حقائق ورسائل مع مالك وتاريخ مراجعة واعتماد.", "التسويق + المنتج", "نسبة المواد المرتبطة بمصدر معتمد"),
    "MCM04": ("حوكمة رحلة العميل", "توحيد خريطة الرحلة وآلية تسليم الحالات بين الفرق.", "تجربة العميل", "نسبة الحالات المحوّلة دون فقد السياق"),
    "MCM05": ("اختبار الوعد مقابل التجربة", "مراجعة الوعود التسويقية مع التشغيل والخدمة قبل الإطلاق.", "التسويق + العمليات", "عدد فجوات الوعد المغلقة"),
    "MCM06": ("دورة قياس وتعلم", "ربط كل مبادرة بفرضية ومؤشر وقرار مراجعة موثق.", "التحليلات", "نسبة المبادرات التي أنتجت قرار تحسين"),
    "MCM07": ("مأسسة المعرفة", "توثيق العمليات الحرجة وبناء تدريب وتسليم يقللان الاعتماد على الأفراد.", "العمليات", "نسبة العمليات ذات بديل موثق"),
}

DIAGNOSTIC_RULES = [
    ("INFORMATION_INTEGRITY_RISK", "مخاطر نزاهة المعلومات", "MCM03", "lt", 50, "HIGH", 0.90),
    ("STRATEGY_EXECUTION_GAP", "فجوة الاستراتيجية والتنفيذ", "MCM01:MCM04", "gap_gt", 15, "HIGH", 0.86),
    ("PROMISE_EXPERIENCE_GAP", "فجوة الوعد والتجربة", "MCM01:MCM05", "gap_gt", 15, "HIGH", 0.86),
    ("DATA_WITHOUT_LEARNING", "بيانات دون تعلم", "MCM06", "lt", 50, "MEDIUM", 0.82),
    ("KEY_PERSON_DEPENDENCY", "الاعتماد على أفراد محوريين", "MCM07", "lt", 50, "HIGH", 0.88),
    ("JOURNEY_FRAGMENTATION", "تجزؤ رحلة العميل", "MCM04", "lt", 50, "HIGH", 0.88),
    ("COMMUNICATION_FRICTION", "احتكاك في الاستجابة", "SMCE01:SMCE03", "average_lt", 55, "MEDIUM", 0.80),
    ("STAKEHOLDER_MISALIGNMENT", "عدم مواءمة أصحاب المصلحة", "MCM02", "lt", 50, "MEDIUM", 0.84),
    ("REACTIVE_COMMUNICATION", "اتصال تفاعلي قصير الأجل", "MCM01:MCM06", "average_lt", 45, "HIGH", 0.83),
    ("SCALABILITY_RISK", "مخاطر قابلية التوسع", "MCM07:SMCE04", "average_lt", 50, "HIGH", 0.87),
]


def normalize_role(value: str | None) -> str:
    role = str(value or "").strip()
    return ROLE_ALIASES.get(role.lower(), role.upper())
