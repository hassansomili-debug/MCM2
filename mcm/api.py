from __future__ import annotations

import json
import math
import os
import re
import secrets
import statistics
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config
from .ai_plans import generate_improvement_plan
from .database import INTEGRITY_ERRORS, PRODUCT_STATUSES, SCIENTIFIC_STATUSES, assessment_research_eligible, audit, connect, get_config, init_db, now, password_hash, select_for_update, token_hash, verify_password
from .exports import assessment_pdf, build_research_sheets, csv_bytes, fingerprint, research_workbook, spss_package
from .instruments import InstrumentImportError, parse_docx_base64, validate_tables
from .scoring import (
    ScoringError,
    assessment_review,
    calculate_scores,
    diagnostic_payload,
    gap_payload,
    priority_payload,
    score_payload,
)


PUBLIC_FILES = {"index.html", "app.js", "styles.css", "import.css", "platform.css", "og.png", "og-mcm-v2.png", "favicon.svg"}
ALLOWED_MISSING = {"NOT_APPLICABLE", "DONT_KNOW"}
ROADMAP_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "COMPLETED", "DEFERRED"}
PRIVILEGED_ASSESSMENT_ROLES = {"COMPANY_ADMIN", "CONSULTANT", "SUPER_ADMIN"}
RESEARCH_ROLES = {"RESEARCHER", "SUPER_ADMIN"}
_RATE_LIMITS: dict[str, deque] = defaultdict(deque)

# The approved public description of the model. It states the evidentiary basis
# without claiming completed empirical validation, and without the pilot wording
# the participant-facing interface no longer uses. Internal lifecycle status
# stays on instrument_versions and is not shown to participants.
PUBLIC_MODEL = {
    "label_ar": "نموذج تطبيقي قائم على الأدلة العلمية",
    "label_en": "Evidence-Informed Applied Model",
    "supporting_ar": (
        "بُني النموذج بالاستناد إلى الدراسات العلمية في الاتصال التسويقي المتكامل، "
        "وحوكمة المعلومات، ورحلة العميل، وإدارة الوعود، والتعلم التنظيمي، وكفاءة الاتصال."
    ),
    "result_disclaimer_ar": (
        "النتيجة تشخيصية وتطويرية، ولا تمثل شهادة اعتماد أو حكمًا نهائيًا على أداء المنشأة."
    ),
    # Only EMPIRICALLY_VALIDATED may ever change this sentence, and only after
    # an authorised researcher records that status with a written rationale.
    "validation_claim_ar": None,
    "methodology_ar": [
        (
            "نضج MCM نموذج تطبيقي لقياس وتطوير النضج الاتصالي التسويقي في المنشآت. "
            "بُني النموذج بالاستناد إلى الأدبيات العلمية ذات الصلة والممارسات التنظيمية الحديثة، "
            "ويقيس النضج عبر سبعة أبعاد مترابطة، مع قياس كفاءة الاتصال SMCE بوصفها نتيجة "
            "مستقلة عن درجة النضج."
        ),
        (
            "تستخدم نتائج النموذج لأغراض التشخيص، وتحديد الفجوات، وبناء خطط التحسين، "
            "والمقارنة المعيارية. وتخضع الأوزان وحدود المستويات ومكتبة التوصيات للمراجعة "
            "والتحسين المستمر مع تراكم البيانات والأدلة التطبيقية."
        ),
    ],
}


def public_model(scientific_status: str = "EVIDENCE_INFORMED") -> dict:
    """The public model description for a given scientific status.

    A validation sentence is emitted only when the active version has actually
    been recorded as EMPIRICALLY_VALIDATED by an authorised researcher. Every
    weaker status yields no claim at all, so the interface cannot drift into
    asserting validation the evidence does not support.
    """
    model = dict(PUBLIC_MODEL)
    model["scientific_status"] = scientific_status
    if scientific_status == "EMPIRICALLY_VALIDATED":
        model["validation_claim_ar"] = "اكتمل التحقق الكمي التجريبي لهذا الإصدار."
    return model


class APIError(Exception):
    def __init__(self, code: str, status: int = 400, details=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.details = details


def _row(row):
    return dict(row) if row is not None else None


def _slug_email(value) -> str:
    return str(value or "").strip().lower()


def _valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value))


def _password_ok(value: str) -> bool:
    return len(value) >= 10 and bool(re.search(r"[a-z]", value)) and bool(re.search(r"[A-Z]", value)) and bool(re.search(r"\d", value))


def _role(value: str | None) -> str:
    role = config.normalize_role(value)
    if role not in config.ROLES:
        raise APIError("invalid_role", 422)
    return role


def _json_dumps(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def data_version(tables: dict) -> str | None:
    metadata = tables.get("INSTRUMENT_METADATA") or []
    if not metadata:
        return None
    first = metadata[0]
    if "key" in first and "value" in first:
        flattened = {str(row.get("key") or "").strip(): row.get("value") for row in metadata}
        return flattened.get("instrument_version") or flattened.get("version")
    return first.get("instrument_version") or first.get("version")


class API(BaseHTTPRequestHandler):
    server_version = "NudjMCM/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("MCM_ACCESS_LOG", "0") == "1":
            super().log_message(fmt, *args)

    def parsed(self):
        parsed = urlparse(self.path)
        routed = parse_qs(parsed.query).get("route", [""])[0]
        path = f"/api{routed}" if routed else parsed.path
        return path.rstrip("/") or "/", parse_qs(parsed.query)

    def _origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return None
        if config.ALLOWED_ORIGIN != "same-origin":
            allowed = {item.strip() for item in config.ALLOWED_ORIGIN.split(",") if item.strip()}
            return origin if origin in allowed else None
        parsed = urlparse(origin)
        return origin if parsed.netloc == self.headers.get("Host") else None

    def _headers(self, content_type: str, length: int, disposition: str | None = None):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        allowed_origin = self._origin()
        if allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Requested-With")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        private_response = bool(disposition) or content_type.startswith("application/json")
        self.send_header("Cache-Control", "private, no-store" if private_response else "public, max-age=300")
        if private_response:
            self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if disposition:
            self.send_header("Content-Disposition", disposition)

    def send_json(self, value, status: int = 200):
        payload = _json_dumps(value)
        self.send_response(status)
        self._headers("application/json; charset=utf-8", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def send_bytes(self, payload: bytes, content_type: str, filename: str, status: int = 200):
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
        self.send_response(status)
        self._headers(content_type, len(payload), f'attachment; filename="{safe_name}"')
        self.end_headers()
        self.wfile.write(payload)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > config.MAX_DOCX_BYTES * 2:
            raise APIError("request_too_large", 413)
        if not length:
            return {}
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError("invalid_json", 400) from exc
        if not isinstance(value, dict):
            raise APIError("json_object_required", 422)
        return value

    def _rate_limit(self, bucket: str, limit: int, period: int):
        key = f"{self.client_address[0]}:{bucket}"
        current = time.monotonic()
        queue = _RATE_LIMITS[key]
        while queue and queue[0] < current - period:
            queue.popleft()
        if len(queue) >= limit:
            raise APIError("rate_limit_exceeded", 429)
        queue.append(current)

    def context(self, required: bool = True):
        raw_token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not raw_token:
            if required:
                raise APIError("authentication_required", 401)
            return None
        digest = token_hash(raw_token)
        db = connect()
        try:
            session = db.execute(
                "SELECT * FROM sessions WHERE token IN (?,?) AND expires_at>? ORDER BY expires_at DESC LIMIT 1",
                (digest, raw_token, now()),
            ).fetchone()
            if not session:
                if required:
                    raise APIError("session_expired", 401)
                return None
            active_org = session["active_org_id"]
            membership = None
            if active_org:
                membership = db.execute("SELECT * FROM memberships WHERE user_id=? AND organization_id=? AND status='ACTIVE'", (session["user_id"], active_org)).fetchone()
            if not membership:
                membership = db.execute("SELECT * FROM memberships WHERE user_id=? AND status='ACTIVE' ORDER BY organization_id LIMIT 1", (session["user_id"],)).fetchone()
            user = db.execute("SELECT * FROM users WHERE id=? AND is_active=1", (session["user_id"],)).fetchone()
            if not user or not membership:
                raise APIError("membership_required", 403)
            db.execute("UPDATE sessions SET active_org_id=?,last_seen_at=? WHERE token=?", (membership["organization_id"], now(), session["token"]))
            db.commit()
            result = dict(user)
            result.update({"organization_id": membership["organization_id"], "role": config.normalize_role(membership["role"]), "session_key": session["token"]})
            return result
        finally:
            db.close()

    def require_roles(self, context, roles):
        if context["role"] not in set(roles):
            raise APIError("permission_denied", 403)

    def do_OPTIONS(self):
        self.send_response(204)
        self._headers("text/plain", 0)
        self.end_headers()

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        try:
            path, _ = self.parsed()
            if path.startswith("/api"):
                self.send_response(200)
                self._headers("application/json; charset=utf-8", 0)
                self.end_headers()
            else:
                self._static(path, head=True)
        except APIError as exc:
            payload = _json_dumps({"error": exc.code})
            self.send_response(exc.status)
            self._headers("application/json; charset=utf-8", len(payload))
            self.end_headers()

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str):
        try:
            path, query = self.parsed()
            if not path.startswith("/api"):
                return self._static(path)
            data = self.body() if method in {"POST", "PATCH", "DELETE"} else {}
            return self._route(method, path, query, data)
        except APIError as exc:
            self.send_json({"error": exc.code, "details": exc.details}, exc.status)
        except InstrumentImportError as exc:
            self.send_json({"error": exc.code, "details": exc.details}, 422)
        except ScoringError as exc:
            self.send_json({"error": exc.code, "details": exc.details}, 422 if exc.code != "assessment_not_found" else 404)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            request_id = secrets.token_hex(6)
            if os.environ.get("MCM_DEBUG") == "1":
                self.send_json({"error": "internal_error", "request_id": request_id, "debug": repr(exc)}, 500)
            else:
                self.send_json({"error": "internal_error", "request_id": request_id}, 500)

    def _static(self, path: str, head: bool = False):
        filename = "index.html" if path == "/" else path.lstrip("/")
        if filename not in PUBLIC_FILES:
            raise APIError("not_found", 404)
        file_path = (config.ROOT / filename).resolve()
        if file_path.parent != config.ROOT.resolve() or not file_path.is_file():
            raise APIError("not_found", 404)
        payload = file_path.read_bytes()
        content_types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}
        self.send_response(200)
        self._headers(content_types.get(file_path.suffix, "application/octet-stream"), len(payload))
        self.end_headers()
        if not head:
            self.wfile.write(payload)

    def _route(self, method: str, path: str, query: dict, data: dict):
        if method == "GET" and path in {"/api", "/api/health"}:
            db = connect()
            try:
                migration = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                db.execute("SELECT 1").fetchone()
            finally:
                db.close()
            return self.send_json({"status": "ok", "service": "nudj-mcm", "version": "1.0", "database": "ok", "schema_version": migration, "time": now()})
        if method == "GET" and path == "/api/public-config":
            return self.send_json({
                "registration_enabled": config.ALLOW_REGISTRATION,
                "direct_participant_enabled": not config.EPHEMERAL_STORAGE,
                "platform_name": "مقياس النضج الاتصالي التسويقي",
                "storage": config.STORAGE_MODE,
                "notice": "بيئة عرض مؤقتة؛ لا تستخدم بيانات حقيقية." if config.EPHEMERAL_STORAGE else None,
                "model": PUBLIC_MODEL,
                "ai_improvement_plans": {
                    "available": config.AI_AVAILABLE,
                    "provider": config.AI_PROVIDER if config.AI_AVAILABLE else "off",
                    "deterministic_fallback": True,
                    "notice": "التحسين الذكي اختياري ولا يغيّر الدرجة أو مرحلة النضج.",
                },
            })
        if method == "GET" and path == "/api/public/maturity-levels":
            return self.send_json(self._public_maturity_levels())
        if method == "POST" and path == "/api/public/assessments":
            if config.EPHEMERAL_STORAGE:
                raise APIError("durable_storage_required", 503)
            return self._public_assessment(data)
        if path.startswith("/api/auth/"):
            return self._auth(method, path, data)
        if path.startswith("/api/invitations/") and path.endswith("/accept") and method == "POST":
            return self._accept_invitation(path.split("/")[3], data)
        if path.startswith("/api/invitations/") and method == "GET":
            return self._invitation_details(path.split("/")[3])
        if path.startswith("/api/participant/session/"):
            return self._participant(method, path, data)
        context = self.context()
        if method == "GET" and path == "/api/me":
            return self._me(context)
        if path.startswith("/api/organizations") or path == "/api/session/organization" or path.startswith("/api/company/") or path == "/api/consents":
            return self._organization(method, path, data, context)
        if path == "/api/invitations":
            return self._invitations(method, data, context)
        if path.startswith("/api/notifications") or path == "/api/settings":
            return self._preferences(method, path, data, context)
        if path.startswith("/api/instruments") or path.startswith("/api/instrument-versions") or path.startswith("/api/research/instruments") or path.startswith("/api/research/items") or path.startswith("/api/research/codebook"):
            return self._instruments(method, path, query, data, context)
        if path.startswith("/api/assessments"):
            return self._assessments(method, path, data, context)
        if path == "/api/dashboard":
            return self._dashboard(context)
        if path.startswith("/api/results/") or path.startswith("/api/diagnostics/") or path.startswith("/api/gaps/") or path.startswith("/api/priorities/") or path.startswith("/api/roadmap/") or path == "/api/history" or path.startswith("/api/benchmark/"):
            return self._results(method, path, query, data, context)
        if path.startswith("/api/reports"):
            return self._reports(method, path, query, data, context)
        if path.startswith("/api/research/"):
            return self._research(method, path, query, data, context)
        if path.startswith("/api/admin"):
            return self._admin(method, path, data, context)
        raise APIError("route_not_found", 404)

    def _public_maturity_levels(self) -> dict:
        """Serve the five stages for the public stage section and methodology page.

        Both surfaces read this one payload so a stage rename is applied in the
        instrument and the database only, never repeated in the client. Score
        bands are configuration data and are returned so the client never
        hardcodes a cutoff, but the public section does not display them.
        """
        db = connect()
        try:
            version = db.execute(
                """SELECT id,scientific_status FROM instrument_versions
                   WHERE archived_at IS NULL
                   ORDER BY COALESCE(published_at,0) DESC, id DESC LIMIT 1"""
            ).fetchone()
            scientific_status = version["scientific_status"] if version else "EVIDENCE_INFORMED"
            levels = []
            if version:
                for row in db.execute(
                    """SELECT code,label_ar,label_en,level_order,min_score,max_score,content_json
                       FROM maturity_levels WHERE version_id=? ORDER BY level_order""",
                    (version["id"],),
                ):
                    try:
                        content = json.loads(row["content_json"]) if row["content_json"] else {}
                    except (TypeError, ValueError):
                        content = {}
                    levels.append({
                        "code": row["code"],
                        "label_ar": row["label_ar"],
                        "label_en": row["label_en"],
                        "level_order": row["level_order"],
                        "min_score": row["min_score"],
                        "max_score": row["max_score"],
                        "summary_ar": content.get("summary"),
                        "description_ar": content.get("description"),
                        "characteristics_ar": content.get("characteristics") or [],
                        "risks_ar": content.get("risks") or [],
                        "focus_ar": content.get("focus") or [],
                        "transition_ar": content.get("transition") or [],
                    })
        finally:
            db.close()
        return {
            "title_ar": "مراحل النضج الاتصالي التسويقي",
            "subtitle_ar": (
                "تتطور قدرة المنشأة الاتصالية عبر خمس مراحل، تبدأ من الممارسات التي تعتمد "
                "على ردود الفعل وتنتهي بقدرة مستدامة وذكية وقابلة للتوسع."
            ),
            "model": public_model(scientific_status),
            "levels": levels,
        }

    def _public_assessment(self, data: dict):
        """Create an anonymous SME assessment and a participant session in one step."""
        self._rate_limit("public_assessment", 12, 3600)
        organization_name = str(data.get("organization_name") or "").strip()
        sector = str(data.get("sector") or "").strip()
        firm_size = str(data.get("firm_size") or "").strip().upper()
        region = str(data.get("region") or "").strip()
        respondent_role = str(data.get("respondent_role") or "").strip()
        business_model = str(data.get("business_model") or "").strip().upper()
        if not bool(data.get("service_consent")):
            raise APIError("service_consent_required", 422)
        if not 2 <= len(organization_name) <= 120:
            raise APIError("organization_name_required", 422)
        if not 2 <= len(sector) <= 100:
            raise APIError("sector_required", 422)
        if firm_size not in {"MICRO", "SMALL", "MEDIUM"}:
            raise APIError("sme_size_required", 422)
        if not 2 <= len(region) <= 100:
            raise APIError("region_required", 422)
        if not 2 <= len(respondent_role) <= 100:
            raise APIError("respondent_role_required", 422)
        if business_model not in {"B2B", "B2C", "B2B2C", "GOVERNMENT", "NONPROFIT", "OTHER"}:
            raise APIError("business_model_required", 422)
        try:
            firm_age_years = int(data.get("firm_age_years"))
            employee_count = int(data.get("employee_count"))
            social_platform_count = int(data.get("social_platform_count"))
            social_team_size = int(data.get("social_team_size"))
        except (TypeError, ValueError) as exc:
            raise APIError("invalid_demographics", 422) from exc
        if (
            not 0 <= firm_age_years <= 200
            or not 1 <= employee_count <= 250_000
            or not 0 <= social_platform_count <= 50
            or not 0 <= social_team_size <= employee_count
        ):
            raise APIError("invalid_demographics", 422)
        regulated_raw = data.get("regulated_sector")
        if isinstance(regulated_raw, bool):
            regulated_sector = int(regulated_raw)
        elif str(regulated_raw).strip().upper() in {"1", "YES", "TRUE"}:
            regulated_sector = 1
        elif str(regulated_raw).strip().upper() in {"0", "NO", "FALSE"}:
            regulated_sector = 0
        else:
            raise APIError("regulated_sector_required", 422)

        db = connect()
        try:
            version = db.execute(
                "SELECT * FROM instrument_versions WHERE status IN ('PILOT','VALIDATED','PUBLISHED','published') ORDER BY id DESC LIMIT 1"
            ).fetchone()
            admin = db.execute("SELECT id FROM users WHERE lower(email)=? AND is_active=1", (config.PLATFORM_ADMIN_EMAIL,)).fetchone()
            if not version or not admin:
                raise APIError("platform_not_ready", 503)
            timestamp = now()
            origin = "DEMO" if config.EPHEMERAL_STORAGE else "REAL"
            organization_id = db.execute(
                "INSERT INTO organizations(name,locale,sector,size,country,region,data_origin,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (organization_name, "ar", sector, firm_size, "Saudi Arabia", region, origin, timestamp),
            ).lastrowid
            db.execute(
                "INSERT INTO company_profiles(organization_id,research_consent,completion,updated_at) VALUES (?,?,?,?)",
                (organization_id, int(bool(data.get("research_consent"))), 100, timestamp),
            )
            db.execute(
                "INSERT INTO memberships(user_id,organization_id,role,status) VALUES (?,?,?,?)",
                (admin["id"], organization_id, "SUPER_ADMIN", "ACTIVE"),
            )
            assessment_id = db.execute(
                """INSERT INTO assessments(organization_id,version_id,created_by,assessment_type,status,data_origin,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (organization_id, version["id"], admin["id"], "FULL", "IN_PROGRESS", origin, timestamp, timestamp),
            ).lastrowid
            db.execute(
                """INSERT INTO assessment_context(
                     assessment_id,sector,firm_size,employee_count,firm_age_years,business_model,region,
                     social_platform_count,social_team_size,regulated,respondent_role,
                     leadership_support,human_competencies,technology_infrastructure,data_readiness,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (assessment_id, sector, firm_size, employee_count, firm_age_years, business_model, region,
                 social_platform_count, social_team_size, regulated_sector, respondent_role,
                 None, None, None, None, timestamp),
            )
            participant_id = db.execute(
                "INSERT INTO participants(organization_id,full_name,email,job_title,created_at) VALUES (?,?,?,?,?)",
                (organization_id, "مشارك مباشر", None, respondent_role, timestamp),
            ).lastrowid
            db.execute("UPDATE participants SET research_id=? WHERE id=?", (f"P{participant_id:06d}", participant_id))
            db.execute(
                "INSERT INTO assessment_participants(assessment_id,participant_id,assessment_role,status) VALUES (?,?,?,?)",
                (assessment_id, participant_id, "RESPONDENT", "ACCEPTED"),
            )
            for consent_type, accepted in (
                ("SERVICE_DIAGNOSTIC", 1),
                ("RESEARCH_USE", int(bool(data.get("research_consent")))),
            ):
                db.execute(
                    "INSERT INTO consents(participant_id,consent_type,consent_version,accepted,accepted_at) VALUES (?,?,?,?,?)",
                    (participant_id, consent_type, "1.0", accepted, timestamp),
                )
            session_raw = secrets.token_urlsafe(36)
            db.execute(
                "INSERT INTO participant_sessions(token,participant_id,name,email,assessment_id,expires_at) VALUES (?,?,?,?,?,?)",
                (token_hash(session_raw), participant_id, "مشارك مباشر", f"participant-{participant_id}@anonymous.invalid", assessment_id, timestamp + config.INVITATION_TTL),
            )
            audit(db, None, "public_assessment_created", "assessment", assessment_id, {"firm_size": firm_size, "data_origin": origin})
            db.commit()
            return self.send_json({
                "token": session_raw,
                "assessment_id": assessment_id,
                "participant_id": participant_id,
                "instrument_status": version["status"],
                "storage": config.STORAGE_MODE,
            }, 201)
        except INTEGRITY_ERRORS as exc:
            db.rollback()
            raise APIError("assessment_creation_failed", 409) from exc
        finally:
            db.close()

    def _new_session(self, db, user_id: int, organization_id: int) -> str:
        raw = secrets.token_urlsafe(36)
        digest = token_hash(raw)
        timestamp = now()
        db.execute(
            "INSERT INTO sessions(token,user_id,active_org_id,expires_at,created_at,last_seen_at) VALUES (?,?,?,?,?,?)",
            (digest, user_id, organization_id, timestamp + config.SESSION_TTL, timestamp, timestamp),
        )
        return raw

    def _auth(self, method: str, path: str, data: dict):
        db = connect()
        try:
            if method == "POST" and path == "/api/auth/register":
                if not config.ALLOW_REGISTRATION:
                    raise APIError("registration_disabled", 403)
                self._rate_limit("register", 8, 3600)
                email = _slug_email(data.get("email"))
                name = str(data.get("name") or "").strip()
                password = str(data.get("password") or "")
                organization_name = str(data.get("organization_name") or "").strip()
                if not _valid_email(email) or len(name) < 2 or len(organization_name) < 2:
                    raise APIError("valid_registration_data_required", 422)
                if not _password_ok(password):
                    raise APIError("password_policy_failed", 422, {"minimum": 10, "requires": ["uppercase", "lowercase", "number"]})
                if db.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
                    raise APIError("email_already_exists", 409)
                timestamp = now()
                db.execute("BEGIN IMMEDIATE")
                user_id = db.execute(
                    "INSERT INTO users(email,name,password_hash,preferred_language,verified,is_active,created_at) VALUES (?,?,?,?,1,1,?)",
                    (email, name, password_hash(password), data.get("locale", "ar"), timestamp),
                ).lastrowid
                org_id = db.execute(
                    "INSERT INTO organizations(name,locale,sector,size,country,region,data_origin,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (organization_name, data.get("locale", "ar"), data.get("sector"), data.get("size"), data.get("country"), data.get("region"), "REAL", timestamp),
                ).lastrowid
                db.execute("INSERT INTO memberships(user_id,organization_id,role,status) VALUES (?,?,?,?)", (user_id, org_id, "COMPANY_ADMIN", "ACTIVE"))
                db.execute("INSERT INTO company_profiles(organization_id,completion,updated_at) VALUES (?,?,?)", (org_id, 10, timestamp))
                db.execute("INSERT INTO user_settings(user_id,locale) VALUES (?,?)", (user_id, data.get("locale", "ar")))
                if bool(data.get("service_consent", True)):
                    db.execute("INSERT INTO consents(user_id,consent_type,consent_version,accepted,accepted_at) VALUES (?,?,?,?,?)", (user_id, "SERVICE_DIAGNOSTIC", "1.0", 1, timestamp))
                raw = self._new_session(db, user_id, org_id)
                audit(db, user_id, "register", "organization", org_id)
                db.commit()
                return self.send_json({"token": raw, "user": {"id": user_id, "name": name, "email": email, "role": "COMPANY_ADMIN"}, "organization_id": org_id}, 201)
            if method == "POST" and path == "/api/auth/login":
                self._rate_limit("login", 10, 900)
                email = _slug_email(data.get("email"))
                user = db.execute("SELECT * FROM users WHERE lower(email)=?", (email,)).fetchone()
                if not user or not user["is_active"] or not verify_password(str(data.get("password") or ""), user["password_hash"]):
                    raise APIError("invalid_credentials", 401)
                membership = db.execute("SELECT * FROM memberships WHERE user_id=? AND status='ACTIVE' ORDER BY organization_id LIMIT 1", (user["id"],)).fetchone()
                if not membership:
                    raise APIError("membership_required", 403)
                raw = self._new_session(db, user["id"], membership["organization_id"])
                if not str(user["password_hash"]).startswith("pbkdf2_sha256$"):
                    db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(str(data.get("password") or "")), user["id"]))
                audit(db, user["id"], "login", "session", None)
                db.commit()
                return self.send_json({"token": raw, "expires_in": config.SESSION_TTL, "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": config.normalize_role(membership["role"])}})
            if method == "POST" and path == "/api/auth/logout":
                context = self.context()
                db.execute("DELETE FROM sessions WHERE token=?", (context["session_key"],))
                audit(db, context["id"], "logout", "session", None)
                db.commit()
                return self.send_json({"logged_out": True})
            if method == "POST" and path == "/api/auth/forgot-password":
                self._rate_limit("forgot", 5, 3600)
                email = _slug_email(data.get("email"))
                user = db.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
                response = {"accepted": True, "message": "If the account exists, reset instructions are available through the configured delivery channel."}
                if user:
                    raw = secrets.token_urlsafe(32)
                    db.execute("INSERT INTO password_reset_tokens(token_hash,user_id,expires_at) VALUES (?,?,?)", (token_hash(raw), user["id"], now() + config.RESET_TTL))
                    audit(db, user["id"], "password_reset_requested", "user", user["id"])
                    if config.EXPOSE_DEV_RESET_TOKEN:
                        response["development_reset_token"] = raw
                db.commit()
                return self.send_json(response)
            if method == "POST" and path == "/api/auth/reset-password":
                self._rate_limit("reset", 8, 3600)
                password = str(data.get("password") or "")
                if not _password_ok(password):
                    raise APIError("password_policy_failed", 422)
                digest = token_hash(str(data.get("token") or ""))
                timestamp = now()
                db.execute("BEGIN IMMEDIATE")
                reset = select_for_update(
                    db,
                    "SELECT * FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                    (digest, timestamp),
                )
                if not reset:
                    raise APIError("reset_token_invalid", 401)
                claimed = db.execute(
                    "UPDATE password_reset_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                    (timestamp, digest, timestamp),
                )
                if claimed.rowcount != 1:
                    raise APIError("reset_token_invalid", 401)
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password), reset["user_id"]))
                db.execute("DELETE FROM sessions WHERE user_id=?", (reset["user_id"],))
                audit(db, reset["user_id"], "password_reset", "user", reset["user_id"])
                db.commit()
                return self.send_json({"password_reset": True})
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _me(self, context):
        db = connect()
        try:
            organizations = [dict(row) for row in db.execute(
                """SELECT o.id,o.name,o.locale,o.sector,o.size,m.role,m.status
                   FROM memberships m JOIN organizations o ON o.id=m.organization_id WHERE m.user_id=? ORDER BY o.name""",
                (context["id"],),
            )]
            settings = db.execute("SELECT * FROM user_settings WHERE user_id=?", (context["id"],)).fetchone()
            organization = db.execute("SELECT * FROM organizations WHERE id=?", (context["organization_id"],)).fetchone()
            unread = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (context["id"],)).fetchone()[0]
            return self.send_json({
                "user": {key: context.get(key) for key in ("id", "email", "name", "job_title", "phone", "preferred_language", "role")},
                "organization": _row(organization), "organizations": organizations, "settings": _row(settings), "unread_notifications": unread,
            })
        finally:
            db.close()

    def _organization(self, method: str, path: str, data: dict, context):
        db = connect()
        try:
            if path == "/api/organizations" and method == "GET":
                rows = db.execute("SELECT o.*,m.role,m.status FROM memberships m JOIN organizations o ON o.id=m.organization_id WHERE m.user_id=? ORDER BY o.name", (context["id"],)).fetchall()
                return self.send_json({"organizations": [dict(row) for row in rows], "active_organization_id": context["organization_id"]})
            if path == "/api/organizations" and method == "POST":
                name = str(data.get("name") or "").strip()
                if len(name) < 2:
                    raise APIError("organization_name_required", 422)
                timestamp = now()
                org_id = db.execute("INSERT INTO organizations(name,locale,sector,size,country,region,data_origin,created_at) VALUES (?,?,?,?,?,?,?,?)", (name, data.get("locale", "ar"), data.get("sector"), data.get("size"), data.get("country"), data.get("region"), "REAL", timestamp)).lastrowid
                db.execute("INSERT INTO memberships VALUES (?,?,?,?)", (context["id"], org_id, "COMPANY_ADMIN", "ACTIVE"))
                db.execute("INSERT INTO company_profiles(organization_id,completion,updated_at) VALUES (?,?,?)", (org_id, 10, timestamp))
                db.execute("UPDATE sessions SET active_org_id=? WHERE token=?", (org_id, context["session_key"]))
                audit(db, context["id"], "create", "organization", org_id)
                db.commit()
                return self.send_json({"id": org_id, "name": name}, 201)
            if path == "/api/session/organization" and method == "POST":
                org_id = int(data.get("organization_id") or 0)
                membership = db.execute("SELECT 1 FROM memberships WHERE user_id=? AND organization_id=? AND status='ACTIVE'", (context["id"], org_id)).fetchone()
                if not membership:
                    raise APIError("organization_membership_required", 403)
                db.execute("UPDATE sessions SET active_org_id=? WHERE token=?", (org_id, context["session_key"]))
                db.commit()
                return self.send_json({"active_organization_id": org_id})
            if path == "/api/company/profile" and method == "GET":
                organization = db.execute("SELECT * FROM organizations WHERE id=?", (context["organization_id"],)).fetchone()
                profile = db.execute("SELECT * FROM company_profiles WHERE organization_id=?", (context["organization_id"],)).fetchone()
                return self.send_json({"organization": _row(organization), "profile": _row(profile) or {"organization_id": context["organization_id"], "completion": 0}})
            if path == "/api/company/profile" and method in {"POST", "PATCH"}:
                self.require_roles(context, {"COMPANY_ADMIN", "SUPER_ADMIN"})
                allowed_org = {"name", "sector", "subsector", "size", "country", "region", "locale"}
                updates = {key: data[key] for key in allowed_org if key in data}
                if updates:
                    clauses = ",".join(f"{key}=?" for key in updates)
                    db.execute(f"UPDATE organizations SET {clauses} WHERE id=?", (*updates.values(), context["organization_id"]))
                fields = ["website", "business_model", "employee_count", "annual_revenue_band", "communication_team_size", "crm_system", "analytics_system", "research_consent"]
                values = {field: data.get(field) for field in fields}
                completion = round(sum(value not in (None, "", []) for value in values.values()) / len(values) * 100)
                db.execute(
                    """INSERT INTO company_profiles(organization_id,website,business_model,employee_count,annual_revenue_band,communication_team_size,crm_system,analytics_system,research_consent,completion,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(organization_id) DO UPDATE SET website=excluded.website,business_model=excluded.business_model,employee_count=excluded.employee_count,annual_revenue_band=excluded.annual_revenue_band,communication_team_size=excluded.communication_team_size,crm_system=excluded.crm_system,analytics_system=excluded.analytics_system,research_consent=excluded.research_consent,completion=excluded.completion,updated_at=excluded.updated_at""",
                    (context["organization_id"], *(values[field] for field in fields), completion, now()),
                )
                audit(db, context["id"], "update", "company_profile", context["organization_id"], {"completion": completion})
                db.commit()
                return self.send_json({"updated": True, "completion": completion})
            if path == "/api/company/team" and method == "GET":
                rows = db.execute("SELECT u.id,u.name,u.email,u.job_title,m.role,m.status FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.organization_id=? ORDER BY u.name", (context["organization_id"],)).fetchall()
                return self.send_json({"members": [dict(row) for row in rows]})
            if path == "/api/company/team" and method in {"POST", "PATCH"}:
                self.require_roles(context, {"COMPANY_ADMIN", "SUPER_ADMIN"})
                user_id = int(data.get("user_id") or 0)
                role = _role(data.get("role"))
                company_roles = {"COMPANY_RESPONDENT", "COMPANY_ADMIN", "CONSULTANT"}
                if context["role"] != "SUPER_ADMIN" and role not in company_roles:
                    raise APIError("permission_denied", 403)
                status = str(data.get("status") or "ACTIVE").upper()
                if status not in {"ACTIVE", "SUSPENDED"}:
                    raise APIError("invalid_membership_status", 422)
                if not db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                    raise APIError("user_not_found", 404)
                db.execute("INSERT INTO memberships(user_id,organization_id,role,status) VALUES (?,?,?,?) ON CONFLICT(user_id,organization_id) DO UPDATE SET role=excluded.role,status=excluded.status", (user_id, context["organization_id"], role, status))
                audit(db, context["id"], "update", "membership", user_id, {"role": role, "status": status})
                db.commit()
                return self.send_json({"user_id": user_id, "role": role, "status": status})
            if path == "/api/consents" and method == "GET":
                rows = db.execute("SELECT * FROM consents WHERE user_id=? ORDER BY accepted_at DESC", (context["id"],)).fetchall()
                return self.send_json({"consents": [dict(row) for row in rows]})
            if path == "/api/consents" and method in {"POST", "PATCH"}:
                consent_type = str(data.get("consent_type") or "").upper()
                if consent_type not in {"SERVICE_DIAGNOSTIC", "RESEARCH_USE"}:
                    raise APIError("invalid_consent_type", 422)
                accepted = int(bool(data.get("accepted")))
                version = str(data.get("consent_version") or "1.0")
                db.execute("BEGIN IMMEDIATE")
                select_for_update(db, "SELECT id FROM users WHERE id=?", (context["id"],))
                db.execute("DELETE FROM consents WHERE user_id=? AND participant_id IS NULL AND consent_type=? AND consent_version=?", (context["id"], consent_type, version))
                db.execute("INSERT INTO consents(user_id,consent_type,consent_version,accepted,accepted_at) VALUES (?,?,?,?,?)", (context["id"], consent_type, version, accepted, now()))
                audit(db, context["id"], "consent_update", "consent", None, {"type": consent_type, "accepted": bool(accepted)})
                db.commit()
                return self.send_json({"consent_type": consent_type, "accepted": bool(accepted), "version": version})
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _invitations(self, method: str, data: dict, context):
        db = connect()
        try:
            if method == "GET":
                self.require_roles(context, {"COMPANY_ADMIN", "CONSULTANT", "SUPER_ADMIN"})
                rows = db.execute("SELECT id,assessment_id,email,full_name,job_title,department,role,status,expires_at,accepted_at FROM invitations WHERE organization_id=? ORDER BY id DESC", (context["organization_id"],)).fetchall()
                return self.send_json({"invitations": [dict(row) for row in rows]})
            if method == "POST":
                self.require_roles(context, {"COMPANY_ADMIN", "CONSULTANT", "SUPER_ADMIN"})
                email = _slug_email(data.get("email"))
                if not _valid_email(email):
                    raise APIError("valid_email_required", 422)
                assessment_id = int(data.get("assessment_id") or 0)
                assessment = db.execute("SELECT * FROM assessments WHERE id=? AND organization_id=? AND status IN ('DRAFT','IN_PROGRESS')", (assessment_id, context["organization_id"])).fetchone()
                if not assessment:
                    raise APIError("active_assessment_required", 422)
                raw = secrets.token_urlsafe(28)
                digest = token_hash(raw)
                expires = now() + config.INVITATION_TTL
                invitation_id = db.execute(
                    """INSERT INTO invitations(organization_id,assessment_id,email,full_name,job_title,department,role,token,status,expires_at,created_by)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (context["organization_id"], assessment_id, email, str(data.get("full_name") or "").strip() or None, data.get("job_title"), data.get("department"), str(data.get("assessment_role") or "RESPONDENT").upper(), digest, "PENDING", expires, context["id"]),
                ).lastrowid
                audit(db, context["id"], "invite", "invitation", invitation_id, {"assessment_id": assessment_id})
                db.commit()
                return self.send_json({"id": invitation_id, "email": email, "status": "PENDING", "expires_at": expires, "invitation_url": f"/#participant?token={raw}"}, 201)
            raise APIError("method_not_allowed", 405)
        finally:
            db.close()

    def _find_invitation(self, db, raw: str, *, lock: bool = False):
        sql = "SELECT * FROM invitations WHERE token IN (?,?) ORDER BY id DESC LIMIT 1"
        if lock:
            return select_for_update(db, sql, (token_hash(raw), raw))
        return db.execute(sql, (token_hash(raw), raw)).fetchone()

    def _invitation_details(self, raw: str):
        db = connect()
        try:
            invitation = self._find_invitation(db, raw)
            if not invitation or invitation["expires_at"] <= now():
                raise APIError("invitation_invalid_or_expired", 404)
            organization = db.execute("SELECT name FROM organizations WHERE id=?", (invitation["organization_id"],)).fetchone()
            return self.send_json({"email": invitation["email"], "full_name": invitation["full_name"], "assessment_id": invitation["assessment_id"], "role": invitation["role"], "status": invitation["status"], "organization_name": organization["name"] if organization else None, "expires_at": invitation["expires_at"]})
        finally:
            db.close()

    def _accept_invitation(self, raw: str, data: dict):
        self._rate_limit("invitation_accept", 20, 3600)
        db = connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            invitation = self._find_invitation(db, raw, lock=True)
            if not invitation or invitation["expires_at"] <= now() or invitation["status"] != "PENDING":
                raise APIError("invitation_invalid_or_expired", 404)
            assessment = db.execute("SELECT * FROM assessments WHERE id=? AND status IN ('DRAFT','IN_PROGRESS')", (invitation["assessment_id"],)).fetchone()
            if not assessment:
                raise APIError("assessment_not_available", 409)
            accepted = bool(data.get("service_consent"))
            if not accepted:
                raise APIError("service_consent_required", 422)
            select_for_update(db, "SELECT id FROM organizations WHERE id=?", (invitation["organization_id"],))
            participant = db.execute("SELECT * FROM participants WHERE organization_id=? AND lower(email)=? ORDER BY id LIMIT 1", (invitation["organization_id"], invitation["email"].lower())).fetchone()
            if participant:
                participant_id = participant["id"]
            else:
                participant_id = db.execute(
                    "INSERT INTO participants(organization_id,full_name,email,job_title,department,created_at) VALUES (?,?,?,?,?,?)",
                    (invitation["organization_id"], invitation["full_name"] or data.get("full_name") or "مشارك", invitation["email"], invitation["job_title"], invitation["department"], now()),
                ).lastrowid
                db.execute("UPDATE participants SET research_id=? WHERE id=?", (f"P{participant_id:06d}", participant_id))
            db.execute("INSERT INTO assessment_participants(assessment_id,participant_id,assessment_role,status) VALUES (?,?,?,?) ON CONFLICT(assessment_id,participant_id) DO UPDATE SET assessment_role=excluded.assessment_role,status='ACCEPTED'", (assessment["id"], participant_id, invitation["role"], "ACCEPTED"))
            db.execute("DELETE FROM consents WHERE participant_id=? AND user_id IS NULL AND consent_type IN ('SERVICE_DIAGNOSTIC','RESEARCH_USE') AND consent_version='1.0'", (participant_id,))
            db.execute("INSERT INTO consents(participant_id,consent_type,consent_version,accepted,accepted_at) VALUES (?,?,?,?,?)", (participant_id, "SERVICE_DIAGNOSTIC", "1.0", 1, now()))
            if data.get("research_consent") is not None:
                db.execute("INSERT INTO consents(participant_id,consent_type,consent_version,accepted,accepted_at) VALUES (?,?,?,?,?)", (participant_id, "RESEARCH_USE", "1.0", int(bool(data.get("research_consent"))), now()))
            session_raw = secrets.token_urlsafe(36)
            db.execute("INSERT INTO participant_sessions(token,participant_id,name,email,assessment_id,expires_at) VALUES (?,?,?,?,?,?)", (token_hash(session_raw), participant_id, invitation["full_name"] or data.get("full_name") or "مشارك", invitation["email"], assessment["id"], invitation["expires_at"]))
            db.execute("UPDATE invitations SET status='ACCEPTED',accepted_at=? WHERE id=?", (now(), invitation["id"]))
            db.execute("UPDATE assessments SET status='IN_PROGRESS',updated_at=? WHERE id=? AND status='DRAFT'", (now(), assessment["id"]))
            audit(db, None, "accept", "invitation", invitation["id"], {"participant_id": participant_id})
            db.commit()
            return self.send_json({"token": session_raw, "assessment_id": assessment["id"], "participant_id": participant_id})
        finally:
            db.close()

    def _participant_session(self, db, raw: str):
        return db.execute("SELECT * FROM participant_sessions WHERE token IN (?,?) AND expires_at>? ORDER BY expires_at DESC LIMIT 1", (token_hash(raw), raw, now())).fetchone()

    def _participant(self, method: str, path: str, data: dict):
        parts = path.split("/")
        if len(parts) < 5:
            raise APIError("route_not_found", 404)
        raw = parts[4]
        action = parts[5] if len(parts) > 5 else None
        db = connect()
        try:
            session = self._participant_session(db, raw)
            if not session:
                raise APIError("participant_session_invalid", 401)
            assessment = db.execute("SELECT * FROM assessments WHERE id=?", (session["assessment_id"],)).fetchone()
            if not assessment:
                raise APIError("assessment_not_found", 404)
            participant_id = int(session["participant_id"] or 0)
            membership = db.execute("SELECT status FROM assessment_participants WHERE assessment_id=? AND participant_id=?", (assessment["id"], participant_id)).fetchone()
            if not membership:
                raise APIError("assessment_participation_required", 403)
            if method == "GET" and not action:
                items = [dict(row) for row in db.execute("SELECT id,code,construct,dimension_code,prompt_ar,prompt_en,required,response_type,min_value,max_value FROM items WHERE version_id=? ORDER BY sort_order,id", (assessment["version_id"],))]
                responses = {row["item_id"]: {"value": row["numeric_value"] if row["numeric_value"] is not None else row["text_value"], "missing_type": row["missing_type"]} for row in db.execute("SELECT item_id,numeric_value,text_value,missing_type FROM responses WHERE assessment_id=? AND participant_id=?", (assessment["id"], session["participant_id"] or 0))}
                review = assessment_review(db, assessment["id"], participant_id)
                assessment_context = db.execute("SELECT * FROM assessment_context WHERE assessment_id=?", (assessment["id"],)).fetchone()
                completed_result = score_payload(db, assessment["id"]) if assessment["status"] == "COMPLETED" and assessment_context else None
                return self.send_json({"participant": {"name": session["name"]}, "assessment": {"id": assessment["id"], "status": assessment["status"], "participant_status": membership["status"]}, "context": _row(assessment_context), "items": items, "responses": responses, "review": review, "result": completed_result})
            if method == "POST" and action == "answers":
                if membership["status"] == "COMPLETED":
                    raise APIError("participant_submission_locked", 409)
                result = self._save_answers(db, assessment, participant_id, data.get("answers", []))
                db.commit()
                return self.send_json(result)
            if method == "POST" and action == "submit":
                if assessment["status"] not in {"DRAFT", "IN_PROGRESS"}:
                    raise APIError("assessment_locked", 409)
                if membership["status"] == "COMPLETED":
                    raise APIError("participant_submission_locked", 409)
                result = self._complete_participant(db, assessment, participant_id, None)
                db.commit()
                return self.send_json(result)
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _preferences(self, method: str, path: str, data: dict, context):
        db = connect()
        try:
            if path == "/api/notifications" and method == "GET":
                rows = db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 100", (context["id"],)).fetchall()
                return self.send_json({"notifications": [dict(row) for row in rows]})
            if path == "/api/notifications/read" and method in {"POST", "PATCH"}:
                notification_id = data.get("notification_id")
                if notification_id:
                    db.execute("UPDATE notifications SET read_at=? WHERE id=? AND user_id=?", (now(), int(notification_id), context["id"]))
                else:
                    db.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (now(), context["id"]))
                db.commit()
                return self.send_json({"marked_read": True})
            if path == "/api/settings" and method == "GET":
                settings = db.execute("SELECT * FROM user_settings WHERE user_id=?", (context["id"],)).fetchone()
                return self.send_json({"user": {"name": context["name"], "email": context["email"], "job_title": context["job_title"], "phone": context["phone"]}, "settings": _row(settings)})
            if path == "/api/settings" and method in {"POST", "PATCH"}:
                locale = str(data.get("locale") or "ar")
                if locale not in {"ar", "en"}:
                    raise APIError("unsupported_locale", 422)
                db.execute("UPDATE users SET name=?,job_title=?,phone=?,preferred_language=? WHERE id=?", (str(data.get("name") or context["name"]).strip(), data.get("job_title"), data.get("phone"), locale, context["id"]))
                db.execute("INSERT INTO user_settings(user_id,locale,email_notifications,security_notifications) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET locale=excluded.locale,email_notifications=excluded.email_notifications,security_notifications=excluded.security_notifications", (context["id"], locale, int(bool(data.get("email_notifications", True))), int(bool(data.get("security_notifications", True)))))
                audit(db, context["id"], "update", "settings", context["id"])
                db.commit()
                return self.send_json({"updated": True, "locale": locale})
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _instruments(self, method: str, path: str, query: dict, data: dict, context):
        self.require_roles(context, RESEARCH_ROLES)
        db = connect()
        try:
            if method == "GET" and path in {"/api/instruments", "/api/research/instruments"}:
                rows = db.execute(
                    """SELECT v.id,v.instrument_id,v.version,v.status,v.product_status,v.scientific_status,
                              v.scientific_status_changed_at,v.notes,v.created_at,v.published_at,v.archived_at,
                              i.code AS instrument_code,i.name,COUNT(DISTINCT it.id) AS item_count,
                              COUNT(DISTINCT a.id) AS assessment_count
                       FROM instrument_versions v JOIN instruments i ON i.id=v.instrument_id
                       LEFT JOIN items it ON it.version_id=v.id LEFT JOIN assessments a ON a.version_id=v.id
                       GROUP BY v.id,i.id ORDER BY v.id DESC"""
                ).fetchall()
                return self.send_json({"versions": [dict(row) for row in rows]})
            if method == "GET" and re.fullmatch(r"/api/instruments/\d+", path):
                version_id = int(path.rsplit("/", 1)[-1])
                version = db.execute("SELECT v.*,i.code AS instrument_code,i.name FROM instrument_versions v JOIN instruments i ON i.id=v.instrument_id WHERE v.id=?", (version_id,)).fetchone()
                if not version:
                    raise APIError("instrument_version_not_found", 404)
                dimensions = db.execute("SELECT code,construct,name,name_en,weight,sort_order FROM dimensions WHERE version_id=? ORDER BY sort_order,code", (version_id,)).fetchall()
                levels = db.execute("SELECT code,label_ar,label_en,min_score,max_score,level_order FROM maturity_levels WHERE version_id=? ORDER BY level_order", (version_id,)).fetchall()
                return self.send_json({"version": dict(version), "dimensions": [dict(row) for row in dimensions], "maturity_levels": [dict(row) for row in levels]})
            if method == "GET" and (re.fullmatch(r"/api/instruments/\d+/items", path) or path == "/api/research/items"):
                if path == "/api/research/items":
                    requested = int((query.get("version_id") or [0])[0] or 0)
                    version_id = requested or db.execute("SELECT id FROM instrument_versions ORDER BY id DESC LIMIT 1").fetchone()[0]
                else:
                    version_id = int(path.split("/")[3])
                rows = db.execute("SELECT * FROM items WHERE version_id=? ORDER BY sort_order,id", (version_id,)).fetchall()
                return self.send_json({"version_id": version_id, "items": [dict(row) for row in rows]})
            if method == "GET" and path == "/api/research/codebook":
                version_id = int((query.get("version_id") or [0])[0] or 0) or db.execute("SELECT id FROM instrument_versions ORDER BY id DESC LIMIT 1").fetchone()[0]
                rows = db.execute("SELECT code AS variable_name,prompt_ar AS variable_label_ar,prompt_en AS variable_label_en,construct,dimension_code AS dimension,response_type,min_value,max_value,reverse_coded,source,version_id AS instrument_version FROM items WHERE version_id=? ORDER BY sort_order,id", (version_id,)).fetchall()
                return self.send_json({"version_id": version_id, "variables": [dict(row) for row in rows]})
            if method == "POST" and path == "/api/instrument-versions/preview":
                if data.get("docx_base64"):
                    result = parse_docx_base64(str(data["docx_base64"]), str(data.get("filename") or "instrument.docx"), data.get("mime_type"))
                else:
                    result = validate_tables(data.get("tables") or {}, str(data.get("filename") or "instrument.docx"))
                return self.send_json(result)
            if method == "POST" and path == "/api/instrument-versions/import":
                if data.get("docx_base64"):
                    result = parse_docx_base64(str(data["docx_base64"]), str(data.get("filename") or "instrument.docx"), data.get("mime_type"))
                else:
                    result = validate_tables(data.get("tables") or {}, str(data.get("filename") or "instrument.docx"))
                if not result["valid"]:
                    raise APIError("instrument_validation_failed", 422, result)
                version_id, version = self._create_instrument_version(db, result["tables"], context)
                audit(db, context["id"], "instrument_import", "instrument_version", version_id, {"version": version, "stats": result["stats"]})
                db.commit()
                return self.send_json({"id": version_id, "version": version, "status": "DRAFT", "validation": {"warnings": result["warnings"], "stats": result["stats"]}}, 201)
            approve = re.fullmatch(r"/api/instrument-versions/(\d+)/(approve|publish)", path)
            if method == "POST" and approve:
                version_id = int(approve.group(1))
                version = db.execute("SELECT * FROM instrument_versions WHERE id=?", (version_id,)).fetchone()
                if not version:
                    raise APIError("instrument_version_not_found", 404)
                if version["status"] not in {"DRAFT", "EXPERT_REVIEW"}:
                    raise APIError("instrument_version_not_publishable", 409)
                if db.execute("SELECT COUNT(*) FROM items WHERE version_id=?", (version_id,)).fetchone()[0] == 0:
                    raise APIError("instrument_items_required", 422)
                # Publishing is an operational decision only. It moves the
                # product status to ACTIVE and never touches scientific status.
                db.execute(
                    "UPDATE instrument_versions SET status='PILOT',product_status='ACTIVE',published_at=? WHERE id=?",
                    (now(), version_id),
                )
                audit(db, context["id"], "instrument_publication", "instrument_version", version_id, {"status": "PILOT", "product_status": "ACTIVE"})
                db.commit()
                return self.send_json({
                    "id": version_id,
                    "status": "PILOT",
                    "product_status": "ACTIVE",
                    "scientific_status": version["scientific_status"],
                    "notice": "Publication is an operational decision and asserts no empirical validation.",
                })
            scientific = re.fullmatch(r"/api/instrument-versions/(\d+)/scientific-status", path)
            if method in {"POST", "PATCH"} and scientific:
                version_id = int(scientific.group(1))
                version = db.execute("SELECT * FROM instrument_versions WHERE id=?", (version_id,)).fetchone()
                if not version:
                    raise APIError("instrument_version_not_found", 404)
                target = str(data.get("scientific_status") or "").strip().upper()
                if target not in SCIENTIFIC_STATUSES:
                    raise APIError("unsupported_scientific_status", 422)
                rationale = str(data.get("rationale") or "").strip()
                # An evidentiary claim must be justified in writing by the person
                # making it; the platform never advances it on its own.
                if not rationale:
                    raise APIError("scientific_status_rationale_required", 422)
                previous = version["scientific_status"]
                changed_at = now()
                db.execute(
                    """UPDATE instrument_versions
                       SET scientific_status=?,scientific_status_changed_at=?,scientific_status_changed_by=?
                       WHERE id=?""",
                    (target, changed_at, context["id"], version_id),
                )
                audit(db, context["id"], "instrument_scientific_status", "instrument_version", version_id, {
                    "previous_scientific_status": previous,
                    "new_scientific_status": target,
                    "rationale": rationale[:500],
                    "product_status_unchanged": version["product_status"],
                })
                db.commit()
                return self.send_json({
                    "id": version_id,
                    "scientific_status": target,
                    "previous_scientific_status": previous,
                    "changed_at": changed_at,
                })
            archive = re.fullmatch(r"/api/instrument-versions/(\d+)/archive", path)
            if method == "POST" and archive:
                version_id = int(archive.group(1))
                if not db.execute("SELECT 1 FROM instrument_versions WHERE id=?", (version_id,)).fetchone():
                    raise APIError("instrument_version_not_found", 404)
                db.execute(
                    "UPDATE instrument_versions SET status='ARCHIVED',product_status='ARCHIVED',archived_at=? WHERE id=?",
                    (now(), version_id),
                )
                audit(db, context["id"], "instrument_archive", "instrument_version", version_id, {"product_status": "ARCHIVED"})
                db.commit()
                return self.send_json({"id": version_id, "status": "ARCHIVED", "product_status": "ARCHIVED"})
            duplicate = re.fullmatch(r"/api/instrument-versions/(\d+)/duplicate", path)
            if method == "POST" and duplicate:
                source_id = int(duplicate.group(1))
                source = db.execute("SELECT * FROM instrument_versions WHERE id=?", (source_id,)).fetchone()
                if not source:
                    raise APIError("instrument_version_not_found", 404)
                latest = db.execute("SELECT version FROM instrument_versions WHERE instrument_id=? ORDER BY id DESC LIMIT 1", (source["instrument_id"],)).fetchone()[0]
                parts = [int(part) if part.isdigit() else 0 for part in str(latest).split(".")[:3]]
                while len(parts) < 3:
                    parts.append(0)
                version = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
                new_id = db.execute("INSERT INTO instrument_versions(instrument_id,version,status,notes,created_by,created_at) VALUES (?,?,?,?,?,?)", (source["instrument_id"], version, "DRAFT", f"Duplicated from {source_id}", context["id"], now())).lastrowid
                db.execute("INSERT INTO dimensions(version_id,code,construct,name,name_en,weight,sort_order) SELECT ?,code,construct,name,name_en,weight,sort_order FROM dimensions WHERE version_id=?", (new_id, source_id))
                db.execute("INSERT INTO items(version_id,code,construct,dimension_code,prompt_ar,prompt_en,source,lifecycle_status,reverse_coded,required,weight,response_type,min_value,max_value,sort_order) SELECT ?,code,construct,dimension_code,prompt_ar,prompt_en,source,lifecycle_status,reverse_coded,required,weight,response_type,min_value,max_value,sort_order FROM items WHERE version_id=?", (new_id, source_id))
                db.execute("INSERT INTO maturity_levels(version_id,code,label_ar,label_en,min_score,max_score,level_order) SELECT ?,code,label_ar,label_en,min_score,max_score,level_order FROM maturity_levels WHERE version_id=?", (new_id, source_id))
                for source_scale in db.execute("SELECT * FROM scales WHERE version_id=? ORDER BY id", (source_id,)).fetchall():
                    new_scale_id = db.execute("INSERT INTO scales(version_id,code,response_type,min_value,max_value) VALUES (?,?,?,?,?)", (new_id, source_scale["code"], source_scale["response_type"], source_scale["min_value"], source_scale["max_value"])).lastrowid
                    db.execute("INSERT INTO scale_values(scale_id,value,label_ar,label_en,missing_type) SELECT ?,value,label_ar,label_en,missing_type FROM scale_values WHERE scale_id=?", (new_scale_id, source_scale["id"]))
                db.execute("INSERT INTO diagnostic_rules(version_id,code,name_ar,dimensions,operator,threshold,severity,confidence,active) SELECT ?,code,name_ar,dimensions,operator,threshold,severity,confidence,active FROM diagnostic_rules WHERE version_id=?", (new_id, source_id))
                db.execute("INSERT INTO recommendations(version_id,dimension_code,problem,action,why_it_matters,implementation_guidance,suggested_owner,expected_impact,effort,time_horizon,kpi,evidence_source,active) SELECT ?,dimension_code,problem,action,why_it_matters,implementation_guidance,suggested_owner,expected_impact,effort,time_horizon,kpi,evidence_source,active FROM recommendations WHERE version_id=?", (new_id, source_id))
                audit(db, context["id"], "instrument_duplicate", "instrument_version", new_id, {"source_id": source_id})
                db.commit()
                return self.send_json({"id": new_id, "version": version, "status": "DRAFT"}, 201)
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _create_instrument_version(self, db, tables: dict, context) -> tuple[int, str]:
        instrument = db.execute("SELECT id FROM instruments WHERE code='MCM_CORE' ORDER BY id LIMIT 1").fetchone()
        if not instrument:
            instrument_id = db.execute("INSERT INTO instruments(code,name,status,created_at) VALUES ('MCM_CORE','MCM / SMCE Scientific Instrument','ACTIVE',?)", (now(),)).lastrowid
        else:
            instrument_id = instrument["id"]
        metadata_rows = tables.get("INSTRUMENT_METADATA") or [{}]
        metadata = metadata_rows[0]
        if "key" in metadata and "value" in metadata:
            metadata = {str(row.get("key") or "").strip(): row.get("value") for row in metadata_rows}
        requested_version = str(metadata.get("version") or data_version(tables) or "").strip()
        if requested_version and re.fullmatch(r"\d+\.\d+\.\d+", requested_version) and not db.execute("SELECT 1 FROM instrument_versions WHERE instrument_id=? AND version=?", (instrument_id, requested_version)).fetchone():
            version = requested_version
        else:
            latest = db.execute("SELECT version FROM instrument_versions WHERE instrument_id=? ORDER BY id DESC LIMIT 1", (instrument_id,)).fetchone()
            parts = [int(part) if part.isdigit() else 0 for part in str(latest["version"] if latest else "0.0.0").split(".")[:3]]
            while len(parts) < 3:
                parts.append(0)
            version = f"{parts[0]}.{parts[1] + 1}.0"
        import_metadata = dict(metadata)
        import_metadata["source_instrument_version"] = requested_version or None
        import_metadata["platform_version"] = version
        version_id = db.execute(
            "INSERT INTO instrument_versions(instrument_id,version,status,notes,metadata_json,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
            (instrument_id, version, "DRAFT", f"Imported from scientific instrument v{requested_version or 'unknown'}; expert review and quantitative validation remain required.", json.dumps(import_metadata, ensure_ascii=False, sort_keys=True), context["id"], now()),
        ).lastrowid
        settings = {row.get("item_code") or row.get("code"): row for row in tables.get("ITEM_SETTINGS", [])}
        for dimension_sort, row in enumerate(tables.get("DIMENSIONS", []), 1):
            code = row.get("dimension_code") or row.get("code")
            construct = str(row.get("construct") or row.get("construct_type") or row.get("measure") or "MCM").upper()
            if construct == "OPTIONAL_OUTCOME":
                construct = "OUTCOME"
            db.execute(
                """INSERT OR IGNORE INTO dimensions(
                     version_id,code,construct,name,name_en,weight,source_type,source_reference,sort_order
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (version_id, code, construct, row.get("name_ar") or row.get("name") or code, row.get("name_en"), float(row.get("weight") or 1), row.get("source_type"), row.get("source_reference"), int(row.get("display_order") or row.get("sort_order") or dimension_sort)),
            )

        scale_ranges = {}
        for row in tables.get("SCALE_VALUES", []):
            code = str(row.get("scale_code") or row.get("scale") or "").strip()
            try:
                value = float(row.get("value"))
            except (TypeError, ValueError):
                continue
            scale_ranges.setdefault(code, []).append((value, row))
        for scale_code, scale_rows in scale_ranges.items():
            values = [entry[0] for entry in scale_rows]
            response_type = {"LIKERT_5_EXTENT": "LIKERT_EXTENT", "RELATIVE_5_COMPETITOR": "LIKERT_RELATIVE"}.get(scale_code, "LIKERT")
            scale_id = db.execute(
                "INSERT INTO scales(version_id,code,response_type,min_value,max_value) VALUES (?,?,?,?,?)",
                (version_id, scale_code, response_type, min(values), max(values)),
            ).lastrowid
            for value, row in scale_rows:
                db.execute(
                    "INSERT INTO scale_values(scale_id,value,label_ar,label_en) VALUES (?,?,?,?)",
                    (scale_id, value, row.get("label_ar"), row.get("label_en")),
                )
            for missing_type, label_ar, label_en in (("NOT_APPLICABLE", "لا ينطبق", "Not applicable"), ("DONT_KNOW", "لا أعرف", "Don't know")):
                db.execute(
                    "INSERT INTO scale_values(scale_id,value,label_ar,label_en,missing_type) VALUES (?,NULL,?,?,?)",
                    (scale_id, label_ar, label_en, missing_type),
                )

        for profile_sort, row in enumerate(tables.get("PROFILE_FIELDS", []), 1):
            db.execute(
                """INSERT INTO instrument_profile_fields(
                     version_id,code,construct,label_ar,label_en,response_type,include_in_score,source_reference,sort_order
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (version_id, row.get("code") or row.get("field_code"), row.get("construct") or row.get("construct_type") or "CONTEXT", row.get("label_ar") or row.get("arabic_label"), row.get("label_en") or row.get("english_label"), row.get("response_type") or "TEXT", int(str(row.get("include_in_score") or "NO").upper() in {"1", "TRUE", "YES"}), row.get("source_reference"), profile_sort),
            )

        for item_sort, row in enumerate(tables.get("ITEMS", []), 1):
            code = row.get("item_code") or row.get("code")
            setting = settings.get(code, {})
            construct = str(row.get("construct") or row.get("construct_type") or row.get("measure") or "MCM").upper()
            if construct == "OPTIONAL_OUTCOME":
                construct = "OUTCOME"
            reverse = str(setting.get("reverse_coded", "false")).lower() in {"1", "true", "yes"}
            required = str(setting.get("required", "true")).lower() not in {"0", "false", "no"}
            scale_code = setting.get("scale_code") or row.get("scale_code")
            response_type = setting.get("response_type") or row.get("response_type") or {"LIKERT_5_EXTENT": "LIKERT_EXTENT", "RELATIVE_5_COMPETITOR": "LIKERT_RELATIVE"}.get(scale_code, "LIKERT")
            values = [entry[0] for entry in scale_ranges.get(scale_code, [])]
            source_type = setting.get("source_type") or row.get("source_type")
            source_reference = setting.get("source_reference") or row.get("source_reference")
            source = row.get("source") or ":".join(filter(None, (source_type, source_reference))) or None
            db.execute(
                """INSERT INTO items(
                     version_id,code,construct,dimension_code,prompt_ar,prompt_en,source,lifecycle_status,
                     reverse_coded,required,weight,response_type,scale_code,include_in_score,score_group,
                     source_type,source_reference,min_value,max_value,sort_order
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (version_id, code, construct, row.get("dimension_code") or row.get("dimension"), row.get("prompt_ar") or row.get("arabic_item") or row.get("wording_ar") or row.get("prompt"), row.get("prompt_en") or row.get("english_item") or row.get("wording_en"), source, setting.get("item_status") or row.get("lifecycle_status") or "EXPERT_REVIEW", int(reverse), int(required), float(setting.get("weight") or 1), response_type, scale_code, int(str(setting.get("include_in_score") or "YES").upper() in {"1", "TRUE", "YES"}), setting.get("score_group"), source_type, source_reference, float(setting.get("min_value") or (min(values) if values else 1)), float(setting.get("max_value") or (max(values) if values else 5)), int(row.get("display_order") or row.get("sort_order") or item_sort)),
            )
        for index, row in enumerate(tables.get("MATURITY_LEVELS", []), 1):
            try:
                minimum = float(row.get("min_score") or row.get("min"))
                maximum = float(row.get("max_score") or row.get("max"))
            except (TypeError, ValueError) as exc:
                raise APIError("invalid_maturity_threshold", 422, {"row": index}) from exc
            db.execute(
                """INSERT INTO maturity_levels(
                     version_id,code,label_ar,label_en,min_score,max_score,threshold_status,source_reference,level_order
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (version_id, row.get("code") or row.get("level_code") or f"LEVEL_{index}", row.get("label_ar") or row.get("name_ar") or f"المستوى {index}", row.get("label_en") or row.get("name_en") or f"Level {index}", minimum, maximum, row.get("threshold_status") or "PROVISIONAL_LABEL_ONLY", row.get("source_reference"), int(row.get("level_order") or row.get("level_number") or index)),
            )
        dimension_codes = {row[0] for row in db.execute("SELECT code FROM dimensions WHERE version_id=?", (version_id,))}
        for rule_code, name_ar, dimensions, operator, threshold, severity, confidence in config.DIAGNOSTIC_RULES:
            if all(code in dimension_codes for code in dimensions.split(":")):
                db.execute(
                    "INSERT INTO diagnostic_rules(version_id,code,name_ar,dimensions,operator,threshold,severity,confidence) VALUES (?,?,?,?,?,?,?,?)",
                    (version_id, rule_code, name_ar, dimensions, operator, threshold, severity, confidence),
                )
        for dimension_code, (problem, action, owner, kpi) in config.RECOMMENDATIONS.items():
            if dimension_code in dimension_codes:
                db.execute(
                    """INSERT INTO recommendations(
                         version_id,dimension_code,problem,action,why_it_matters,implementation_guidance,
                         suggested_owner,expected_impact,effort,time_horizon,kpi,evidence_source
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (version_id, dimension_code, problem, action, "إغلاق الفجوة يدعم اتساق القرار والتنفيذ.", action, owner, "HIGH", "MEDIUM", "31-90", kpi, "MCM scientific instrument v0.2 improvement library"),
                )
        return version_id, version

    def _participant_for_user(self, db, context) -> int:
        select_for_update(db, "SELECT id FROM users WHERE id=?", (context["id"],))
        participant = db.execute("SELECT id FROM participants WHERE organization_id=? AND user_id=? ORDER BY id LIMIT 1", (context["organization_id"], context["id"])).fetchone()
        if participant:
            return int(participant["id"])
        participant_id = db.execute(
            "INSERT INTO participants(organization_id,user_id,full_name,email,job_title,created_at) VALUES (?,?,?,?,?,?)",
            (context["organization_id"], context["id"], context["name"], context["email"], context["job_title"], now()),
        ).lastrowid
        db.execute("UPDATE participants SET research_id=? WHERE id=?", (f"P{participant_id:06d}", participant_id))
        return int(participant_id)

    def _assessment(self, db, assessment_id: int, context):
        assessment = db.execute("SELECT * FROM assessments WHERE id=? AND organization_id=?", (assessment_id, context["organization_id"])).fetchone()
        if not assessment:
            raise APIError("assessment_not_found", 404)
        if context["role"] not in PRIVILEGED_ASSESSMENT_ROLES:
            assigned = db.execute(
                """SELECT 1 FROM assessment_participants ap JOIN participants p ON p.id=ap.participant_id
                   WHERE ap.assessment_id=? AND p.organization_id=? AND p.user_id=?""",
                (assessment_id, context["organization_id"], context["id"]),
            ).fetchone()
            if not assigned:
                raise APIError("assessment_not_found", 404)
        return assessment

    def _assigned_participant(self, db, assessment_id: int, context, required: bool = True):
        participant = db.execute(
            """SELECT p.id,ap.status FROM assessment_participants ap JOIN participants p ON p.id=ap.participant_id
               WHERE ap.assessment_id=? AND p.organization_id=? AND p.user_id=? ORDER BY p.id LIMIT 1""",
            (assessment_id, context["organization_id"], context["id"]),
        ).fetchone()
        if required and not participant:
            raise APIError("assessment_participation_required", 403)
        return participant

    def _save_answers(self, db, assessment, participant_id: int, answers: list) -> dict:
        db.execute("BEGIN IMMEDIATE")
        locked = select_for_update(db, "SELECT * FROM assessments WHERE id=?", (assessment["id"],))
        participant = select_for_update(
            db,
            "SELECT status FROM assessment_participants WHERE assessment_id=? AND participant_id=?",
            (assessment["id"], participant_id),
        )
        if not locked or locked["status"] not in {"DRAFT", "IN_PROGRESS"}:
            raise APIError("assessment_locked", 409)
        if not participant or participant["status"] == "COMPLETED":
            raise APIError("participant_submission_locked", 409)
        assessment = locked
        if not isinstance(answers, list) or len(answers) > 250:
            raise APIError("answers_array_invalid", 422)
        timestamp = now()
        saved = 0
        for answer in answers:
            if not isinstance(answer, dict):
                raise APIError("invalid_answer", 422)
            item_id = int(answer.get("item_id") or 0)
            item = db.execute("SELECT * FROM items WHERE id=? AND version_id=?", (item_id, assessment["version_id"])).fetchone()
            if not item:
                raise APIError("item_not_in_instrument_version", 422, {"item_id": item_id})
            missing = answer.get("missing_type")
            if missing is not None:
                missing = str(missing).upper()
                if missing == "NOT_ANSWERED":
                    db.execute(
                        "DELETE FROM responses WHERE assessment_id=? AND participant_id=? AND item_id=?",
                        (assessment["id"], participant_id, item_id),
                    )
                    saved += 1
                    continue
                if missing not in ALLOWED_MISSING:
                    raise APIError("invalid_missing_type", 422, {"item_id": item_id})
            numeric_value = None
            text_value = None
            raw_value = answer.get("value")
            response_type = str(item["response_type"] or "LIKERT").upper()
            if missing is None:
                if response_type == "TEXT":
                    text_value = str(raw_value or "").strip()
                    if item["required"] and not text_value:
                        raise APIError("required_text_response", 422, {"item_id": item_id})
                    if len(text_value) > 4000:
                        raise APIError("text_response_too_long", 422, {"item_id": item_id})
                else:
                    try:
                        numeric_value = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise APIError("numeric_response_required", 422, {"item_id": item_id}) from exc
                    minimum = float(item["min_value"] if item["min_value"] is not None else 1)
                    maximum = float(item["max_value"] if item["max_value"] is not None else 5)
                    if not math.isfinite(numeric_value) or numeric_value < minimum or numeric_value > maximum:
                        raise APIError("response_out_of_range", 422, {"item_id": item_id, "min": minimum, "max": maximum})
            db.execute(
                """INSERT INTO responses(assessment_id,participant_id,item_id,numeric_value,text_value,missing_type,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(assessment_id,participant_id,item_id) DO UPDATE SET numeric_value=excluded.numeric_value,text_value=excluded.text_value,missing_type=excluded.missing_type,updated_at=excluded.updated_at""",
                (assessment["id"], participant_id, item_id, numeric_value, text_value, missing, timestamp, timestamp),
            )
            saved += 1
        updated = db.execute(
            "UPDATE assessments SET status='IN_PROGRESS',updated_at=? WHERE id=? AND status IN ('DRAFT','IN_PROGRESS')",
            (timestamp, assessment["id"]),
        )
        if updated.rowcount != 1:
            raise APIError("assessment_locked", 409)
        return {"saved": saved, "saved_at": timestamp, "review": assessment_review(db, assessment["id"], participant_id)}

    def _assessment_detail(self, db, assessment, participant_id: int | None = None) -> dict:
        items = [dict(row) for row in db.execute(
            "SELECT id,code,construct,dimension_code,prompt_ar,prompt_en,required,response_type,min_value,max_value,sort_order FROM items WHERE version_id=? ORDER BY sort_order,id",
            (assessment["version_id"],),
        )]
        query = "SELECT item_id,numeric_value,text_value,missing_type,updated_at FROM responses WHERE assessment_id=?"
        params = [assessment["id"]]
        if participant_id is not None:
            query += " AND participant_id=?"
            params.append(participant_id)
        response_rows = db.execute(query, tuple(params)).fetchall()
        responses = {}
        for row in response_rows:
            responses[row["item_id"]] = {"value": row["numeric_value"] if row["numeric_value"] is not None else row["text_value"], "missing_type": row["missing_type"], "updated_at": row["updated_at"]}
        version = db.execute("SELECT version,status FROM instrument_versions WHERE id=?", (assessment["version_id"],)).fetchone()
        review = assessment_review(db, assessment["id"], participant_id) if participant_id is not None else assessment_review(db, assessment["id"])
        return {"assessment": dict(assessment), "instrument": dict(version), "items": items, "responses": responses, "review": review, "can_respond": participant_id is not None and assessment["status"] in {"DRAFT", "IN_PROGRESS"}}

    def _complete_participant(self, db, assessment, participant_id: int, actor_user_id: int | None) -> dict:
        db.execute("BEGIN IMMEDIATE")
        locked = select_for_update(db, "SELECT * FROM assessments WHERE id=?", (assessment["id"],))
        if not locked or locked["status"] not in {"DRAFT", "IN_PROGRESS"}:
            raise APIError("assessment_locked", 409)
        participant = select_for_update(
            db,
            "SELECT status FROM assessment_participants WHERE assessment_id=? AND participant_id=?",
            (assessment["id"], participant_id),
        )
        if not participant or participant["status"] == "COMPLETED":
            raise APIError("participant_submission_locked", 409)
        assessment = locked
        review = assessment_review(db, assessment["id"], participant_id)
        if not review["complete"]:
            raise APIError("required_answers_missing", 422, review)
        timestamp = now()
        db.execute("UPDATE assessment_participants SET status='COMPLETED' WHERE assessment_id=? AND participant_id=?", (assessment["id"], participant_id))
        audit(db, actor_user_id, "participant_submission", "assessment", assessment["id"], {"participant_id": participant_id})
        pending = db.execute("SELECT COUNT(*) FROM assessment_participants WHERE assessment_id=? AND status!='COMPLETED'", (assessment["id"],)).fetchone()[0]
        if pending:
            db.execute("UPDATE assessments SET status='IN_PROGRESS',submitted_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, assessment["id"]))
            return {"submitted": True, "assessment_complete": False, "pending_participants": pending, "message": "تم إرسال إجاباتك، وسيكتمل التقييم بعد بقية المشاركين."}
        db.execute("UPDATE assessments SET status='COMPLETED',submitted_at=?,completed_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, timestamp, assessment["id"]))
        result = calculate_scores(db, assessment["id"])
        db.execute(
            """INSERT INTO notifications(user_id,type,title,body,target_url,created_at)
               SELECT m.user_id,'ASSESSMENT_COMPLETED','اكتمل التقييم','أصبحت النتائج والتشخيص وخارطة التحسين جاهزة.',?,?
               FROM memberships m WHERE m.organization_id=? AND m.role IN ('COMPANY_ADMIN','CONSULTANT','SUPER_ADMIN')""",
            (f"#results/{assessment['id']}", timestamp, assessment["organization_id"]),
        )
        audit(db, actor_user_id, "assessment_submission", "assessment", assessment["id"], {"scoring_method": "MCM_DETERMINISTIC_1.0"})
        result["submitted"] = True
        result["assessment_complete"] = True
        return result

    def _assessments(self, method: str, path: str, data: dict, context):
        db = connect()
        try:
            ai_plan_match = re.fullmatch(r"/api/assessments/(\d+)/ai-plan", path)
            if ai_plan_match and method == "POST":
                self.require_roles(context, PRIVILEGED_ASSESSMENT_ROLES)
                assessment_id = int(ai_plan_match.group(1))
                assessment = self._assessment(db, assessment_id, context)
                if assessment["status"] != "COMPLETED":
                    raise APIError("assessment_not_completed", 409)
                self._rate_limit(f"ai_plan:{context['id']}", 10, 3600)
                result = score_payload(db, assessment_id)
                plan = generate_improvement_plan(
                    result,
                    provider=config.AI_PROVIDER,
                    model=config.AI_MODEL,
                    base_url=config.AI_BASE_URL,
                    timeout=config.AI_TIMEOUT,
                )
                generation = plan.get("generation") or {}
                audit(
                    db,
                    context["id"],
                    "ai_improvement_plan",
                    "assessment",
                    assessment_id,
                    {
                        "provider": generation.get("provider"),
                        "mode": generation.get("mode"),
                        "status": generation.get("status"),
                        "reason_code": generation.get("reason_code"),
                        "aggregate_only": True,
                    },
                )
                db.commit()
                return self.send_json({"assessment_id": assessment_id, "plan": plan})
            if path == "/api/assessments" and method == "GET":
                restricted = context["role"] not in PRIVILEGED_ASSESSMENT_ROLES
                scope = " AND EXISTS (SELECT 1 FROM assessment_participants ap JOIN participants p ON p.id=ap.participant_id WHERE ap.assessment_id=a.id AND p.user_id=?)" if restricted else ""
                params = (context["organization_id"], context["id"]) if restricted else (context["organization_id"],)
                rows = db.execute(
                    f"""SELECT a.*,v.version AS instrument_version,v.status AS instrument_status,
                              (SELECT total_score FROM assessment_scores s WHERE s.assessment_id=a.id AND s.construct='MCM') AS mcm_total,
                              (SELECT total_score FROM assessment_scores s WHERE s.assessment_id=a.id AND s.construct='SMCE') AS smce_total
                       FROM assessments a JOIN instrument_versions v ON v.id=a.version_id
                       WHERE a.organization_id=?{scope} ORDER BY a.created_at DESC,a.id DESC""",
                    params,
                ).fetchall()
                return self.send_json({"assessments": [dict(row) for row in rows]})
            if path == "/api/assessments" and method == "POST":
                self.require_roles(context, PRIVILEGED_ASSESSMENT_ROLES)
                assessment_type = str(data.get("assessment_type") or "FULL").upper()
                if assessment_type not in {"FULL", "REASSESSMENT", "PULSE"}:
                    raise APIError("invalid_assessment_type", 422)
                version_id = int(data.get("instrument_version_id") or 0)
                if version_id:
                    version = db.execute("SELECT * FROM instrument_versions WHERE id=? AND status IN ('PILOT','VALIDATED','PUBLISHED','published')", (version_id,)).fetchone()
                else:
                    version = db.execute("SELECT * FROM instrument_versions WHERE status IN ('PILOT','VALIDATED','PUBLISHED','published') ORDER BY id DESC LIMIT 1").fetchone()
                if not version:
                    raise APIError("published_instrument_required", 422)
                organization = db.execute("SELECT data_origin FROM organizations WHERE id=?", (context["organization_id"],)).fetchone()
                origin = str(data.get("data_origin") or organization["data_origin"] or "REAL").upper()
                if origin not in {"REAL", "SYNTHETIC", "DEMO", "TEST"}:
                    raise APIError("invalid_data_origin", 422)
                if origin != organization["data_origin"] and context["role"] != "SUPER_ADMIN":
                    origin = organization["data_origin"]
                timestamp = now()
                assessment_id = db.execute(
                    """INSERT INTO assessments(organization_id,version_id,created_by,assessment_type,status,data_origin,parent_assessment_id,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (context["organization_id"], version["id"], context["id"], assessment_type, "DRAFT", origin, data.get("parent_assessment_id"), timestamp, timestamp),
                ).lastrowid
                participant_id = self._participant_for_user(db, context)
                db.execute("INSERT INTO assessment_participants(assessment_id,participant_id,assessment_role,status) VALUES (?,?,?,?)", (assessment_id, participant_id, "OWNER", "IN_PROGRESS"))
                audit(db, context["id"], "create", "assessment", assessment_id, {"instrument_version_id": version["id"], "data_origin": origin})
                db.commit()
                return self.send_json({"id": assessment_id, "status": "DRAFT", "instrument_version_id": version["id"], "instrument_status": version["status"], "classification_notice": "Research Beta - provisional instrument."}, 201)
            detail = re.fullmatch(r"/api/assessments/(\d+)", path)
            if detail and method == "GET":
                assessment = self._assessment(db, int(detail.group(1)), context)
                assigned = self._assigned_participant(db, assessment["id"], context, required=False)
                participant_id = int(assigned["id"]) if assigned else None
                return self.send_json(self._assessment_detail(db, assessment, participant_id))
            answer_match = re.fullmatch(r"/api/assessments/(\d+)/answers", path)
            if answer_match and method == "POST":
                assessment = self._assessment(db, int(answer_match.group(1)), context)
                participant = self._assigned_participant(db, assessment["id"], context)
                if participant["status"] == "COMPLETED":
                    raise APIError("participant_submission_locked", 409)
                participant_id = int(participant["id"])
                result = self._save_answers(db, assessment, participant_id, data.get("answers", []))
                audit(db, context["id"], "autosave", "assessment", assessment["id"], {"saved": result["saved"]})
                db.commit()
                return self.send_json(result)
            review_match = re.fullmatch(r"/api/assessments/(\d+)/review", path)
            if review_match and method == "GET":
                assessment = self._assessment(db, int(review_match.group(1)), context)
                participant = self._assigned_participant(db, assessment["id"], context)
                return self.send_json(assessment_review(db, assessment["id"], int(participant["id"])))
            submit_match = re.fullmatch(r"/api/assessments/(\d+)/submit", path)
            if submit_match and method == "POST":
                assessment = self._assessment(db, int(submit_match.group(1)), context)
                if assessment["status"] not in {"DRAFT", "IN_PROGRESS"}:
                    raise APIError("assessment_locked", 409)
                participant = self._assigned_participant(db, assessment["id"], context)
                if participant["status"] == "COMPLETED":
                    raise APIError("participant_submission_locked", 409)
                result = self._complete_participant(db, assessment, int(participant["id"]), context["id"])
                db.commit()
                return self.send_json(result)
            repeat = re.fullmatch(r"/api/assessments/(\d+)/repeat", path)
            if repeat and method == "POST":
                self.require_roles(context, PRIVILEGED_ASSESSMENT_ROLES)
                source = self._assessment(db, int(repeat.group(1)), context)
                timestamp = now()
                new_id = db.execute("INSERT INTO assessments(organization_id,version_id,created_by,assessment_type,status,data_origin,parent_assessment_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (source["organization_id"], source["version_id"], context["id"], "REASSESSMENT", "DRAFT", source["data_origin"], source["id"], timestamp, timestamp)).lastrowid
                participant_id = self._participant_for_user(db, context)
                db.execute("INSERT INTO assessment_participants VALUES (?,?,?,?)", (new_id, participant_id, "OWNER", "IN_PROGRESS"))
                audit(db, context["id"], "repeat", "assessment", new_id, {"parent_assessment_id": source["id"]})
                db.commit()
                return self.send_json({"id": new_id, "status": "DRAFT", "parent_assessment_id": source["id"]}, 201)
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _dashboard(self, context):
        db = connect()
        try:
            organization = db.execute("SELECT * FROM organizations WHERE id=?", (context["organization_id"],)).fetchone()
            profile = db.execute("SELECT * FROM company_profiles WHERE organization_id=?", (context["organization_id"],)).fetchone()
            restricted = context["role"] not in PRIVILEGED_ASSESSMENT_ROLES
            scope = " AND EXISTS (SELECT 1 FROM assessment_participants ap JOIN participants p ON p.id=ap.participant_id WHERE ap.assessment_id=a.id AND p.user_id=?)" if restricted else ""
            params = (context["organization_id"], context["id"]) if restricted else (context["organization_id"],)
            latest = db.execute(f"SELECT a.id FROM assessments a WHERE a.organization_id=? AND a.status='COMPLETED'{scope} ORDER BY a.completed_at DESC,a.id DESC LIMIT 1", params).fetchone()
            draft_count = db.execute(f"SELECT COUNT(*) FROM assessments a WHERE a.organization_id=? AND a.status IN ('DRAFT','IN_PROGRESS'){scope}", params).fetchone()[0]
            history = [dict(row) for row in db.execute(
                f"""SELECT a.id,a.completed_at,
                          MAX(CASE WHEN s.construct='MCM' THEN s.total_score END) AS mcm,
                          MAX(CASE WHEN s.construct='SMCE' THEN s.total_score END) AS smce
                   FROM assessments a LEFT JOIN assessment_scores s ON s.assessment_id=a.id
                   WHERE a.organization_id=? AND a.status='COMPLETED'{scope} GROUP BY a.id ORDER BY a.completed_at""",
                params,
            )]
            payload = {
                "organization": _row(organization), "profile_completion": profile["completion"] if profile else 0,
                "draft_count": draft_count, "history": history, "latest": None, "diagnoses": [], "priorities": [],
            }
            if latest:
                payload["latest"] = score_payload(db, latest["id"])
                payload["diagnoses"] = diagnostic_payload(db, latest["id"])["diagnoses"][:3]
                payload["priorities"] = priority_payload(db, latest["id"])["priorities"][:5]
            return self.send_json(payload)
        finally:
            db.close()

    def _results(self, method: str, path: str, query: dict, data: dict, context):
        db = connect()
        try:
            result_match = re.fullmatch(r"/api/results/(\d+)", path)
            dimension_match = re.fullmatch(r"/api/results/(\d+)/dimensions/([A-Za-z0-9_-]+)", path)
            smce_match = re.fullmatch(r"/api/results/(\d+)/smce", path)
            diagnostic_match = re.fullmatch(r"/api/diagnostics/(\d+)", path)
            gap_match = re.fullmatch(r"/api/gaps/(\d+)", path)
            priority_match = re.fullmatch(r"/api/priorities/(\d+)", path)
            roadmap_match = re.fullmatch(r"/api/roadmap/(\d+)", path)
            benchmark_match = re.fullmatch(r"/api/benchmark/(\d+)", path)
            id_match = result_match or dimension_match or smce_match or diagnostic_match or gap_match or priority_match or roadmap_match or benchmark_match
            if id_match:
                assessment_id = int(id_match.group(1))
                assessment = self._assessment(db, assessment_id, context)
                if assessment["status"] != "COMPLETED" and not roadmap_match:
                    raise APIError("assessment_not_completed", 409)
            if result_match and method == "GET":
                return self.send_json(score_payload(db, assessment_id))
            if dimension_match and method == "GET":
                code = dimension_match.group(2).upper()
                dimension = db.execute("SELECT ds.*,d.name,d.name_en FROM dimension_scores ds LEFT JOIN dimensions d ON d.version_id=? AND d.code=ds.dimension_code WHERE ds.assessment_id=? AND ds.dimension_code=? LIMIT 1", (assessment["version_id"], assessment_id, code)).fetchone()
                if not dimension:
                    raise APIError("dimension_result_not_found", 404)
                recommendation = db.execute("SELECT r.*,ar.priority_score,ar.gap,ar.rank FROM recommendations r LEFT JOIN assessment_recommendations ar ON ar.recommendation_id=r.id AND ar.assessment_id=? WHERE r.version_id=? AND r.dimension_code=?", (assessment_id, assessment["version_id"], code)).fetchone()
                diagnoses = [row for row in diagnostic_payload(db, assessment_id)["diagnoses"] if code in row["affected_dimensions"]]
                return self.send_json({"assessment_id": assessment_id, "dimension": dict(dimension), "diagnoses": diagnoses, "recommendation": _row(recommendation), "evidence_notice": "Respondent-level raw answers are not exposed on this route."})
            if smce_match and method == "GET":
                result = score_payload(db, assessment_id)
                return self.send_json({"assessment_id": assessment_id, "SMCE": result["scores"]["SMCE"], "comparison_to_mcm": {"mcm_total": result["scores"]["MCM"]["total"], "difference": round((result["scores"]["SMCE"]["total"] or 0) - (result["scores"]["MCM"]["total"] or 0), 2)}, "label": "Communication Efficiency Outcome"})
            if diagnostic_match and method == "GET":
                return self.send_json(diagnostic_payload(db, assessment_id))
            if gap_match and method == "GET":
                return self.send_json(gap_payload(db, assessment_id))
            if priority_match and method == "GET":
                return self.send_json(priority_payload(db, assessment_id))
            if roadmap_match and method == "GET":
                rows = db.execute("SELECT * FROM roadmap_items WHERE assessment_id=? ORDER BY sort_order,id", (assessment_id,)).fetchall()
                grouped = {"0-30": [], "31-90": [], "3-6": []}
                for row in rows:
                    grouped.setdefault(row["horizon"], []).append(dict(row))
                return self.send_json({"assessment_id": assessment_id, "roadmap": grouped})
            if roadmap_match and method == "PATCH":
                self.require_roles(context, {"COMPANY_ADMIN", "SUPER_ADMIN"})
                item_id = int(data.get("item_id") or 0)
                item = db.execute("SELECT * FROM roadmap_items WHERE id=? AND assessment_id=?", (item_id, assessment_id)).fetchone()
                if not item:
                    raise APIError("roadmap_item_not_found", 404)
                status = str(data.get("status") or item["status"]).upper()
                if status not in ROADMAP_STATUSES:
                    raise APIError("invalid_roadmap_status", 422)
                owner = str(data.get("owner") if "owner" in data else item["owner"] or "").strip() or None
                target_date = data.get("target_date") if "target_date" in data else item["target_date"]
                if target_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(target_date)):
                    raise APIError("invalid_target_date", 422)
                db.execute("UPDATE roadmap_items SET owner=?,target_date=?,status=? WHERE id=?", (owner, target_date, status, item_id))
                audit(db, context["id"], "roadmap_update", "roadmap_item", item_id, {"status": status})
                db.commit()
                return self.send_json({"id": item_id, "owner": owner, "target_date": target_date, "status": status})
            if path == "/api/history" and method == "GET":
                restricted = context["role"] not in PRIVILEGED_ASSESSMENT_ROLES
                scope = " AND EXISTS (SELECT 1 FROM assessment_participants ap JOIN participants p ON p.id=ap.participant_id WHERE ap.assessment_id=a.id AND p.user_id=?)" if restricted else ""
                params = (context["organization_id"], context["id"]) if restricted else (context["organization_id"],)
                rows = db.execute(
                    f"""SELECT a.id,a.assessment_type,a.completed_at,v.version AS instrument_version,
                              MAX(CASE WHEN s.construct='MCM' THEN s.total_score END) AS mcm_total,
                              MAX(CASE WHEN s.construct='SMCE' THEN s.total_score END) AS smce_total,
                              MAX(CASE WHEN s.construct='MCM' THEN ml.label_ar END) AS maturity_level
                       FROM assessments a JOIN instrument_versions v ON v.id=a.version_id
                       LEFT JOIN assessment_scores s ON s.assessment_id=a.id LEFT JOIN maturity_levels ml ON ml.id=s.maturity_level_id
                       WHERE a.organization_id=? AND a.status='COMPLETED'{scope} GROUP BY a.id,v.id ORDER BY a.completed_at""",
                    params,
                ).fetchall()
                return self.send_json({"range": (query.get("range") or ["all"])[0], "history": [dict(row) for row in rows]})
            if benchmark_match and method == "GET":
                return self.send_json(self._benchmark(db, assessment, (query.get("cohort") or ["overall"])[0]))
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _benchmark(self, db, assessment, cohort: str) -> dict:
        minimum = int(get_config(db, "MIN_BENCHMARK_SAMPLE", 10))
        if assessment["data_origin"] != "REAL":
            return {"assessment_id": assessment["id"], "available": False, "reason": "NON_REAL_ASSESSMENT", "minimum_sample": minimum}
        organization = db.execute("SELECT sector,size FROM organizations WHERE id=?", (assessment["organization_id"],)).fetchone()
        conditions = ["a.status='COMPLETED'", "a.data_origin='REAL'", "a.version_id=?", "cp.research_consent=1"]
        params = [assessment["version_id"]]
        if cohort == "sector":
            conditions.append("o.sector=?")
            params.append(organization["sector"])
        elif cohort == "size":
            conditions.append("o.size=?")
            params.append(organization["size"])
        rows = db.execute(
            f"""SELECT a.id,s.total_score FROM assessment_scores s JOIN assessments a ON a.id=s.assessment_id
                 JOIN organizations o ON o.id=a.organization_id JOIN company_profiles cp ON cp.organization_id=o.id
                 WHERE s.construct='MCM' AND {' AND '.join(conditions)}
                   AND a.id=(SELECT a2.id FROM assessments a2 WHERE a2.organization_id=a.organization_id AND a2.status='COMPLETED' AND a2.data_origin='REAL' ORDER BY a2.completed_at DESC,a2.id DESC LIMIT 1)""",
            tuple(params),
        ).fetchall()
        values = sorted(float(row["total_score"]) for row in rows if assessment_research_eligible(db, row["id"]))
        if len(values) < minimum:
            return {"assessment_id": assessment["id"], "available": False, "reason": "INSUFFICIENT_SAMPLE", "sample_display": f"<{minimum}", "minimum_sample": minimum, "cohort": cohort}
        index = (len(values) - 1) * .75
        lower, upper = math.floor(index), math.ceil(index)
        top_quartile = values[lower] if lower == upper else values[lower] + (values[upper] - values[lower]) * (index - lower)
        company = db.execute("SELECT total_score FROM assessment_scores WHERE assessment_id=? AND construct='MCM'", (assessment["id"],)).fetchone()
        return {"assessment_id": assessment["id"], "available": True, "cohort": cohort, "sample_size": len(values), "company_score": company["total_score"] if company else None, "cohort_average": round(statistics.mean(values), 2), "top_quartile": round(top_quartile, 2), "generated_at": now(), "unit_of_analysis": "LATEST_COMPLETED_ASSESSMENT_PER_ORGANIZATION"}

    def _reports(self, method: str, path: str, query: dict, data: dict, context):
        db = connect()
        try:
            if path == "/api/reports" and method == "GET":
                restricted = context["role"] not in PRIVILEGED_ASSESSMENT_ROLES
                scope = " AND EXISTS (SELECT 1 FROM assessment_participants ap JOIN participants p ON p.id=ap.participant_id WHERE ap.assessment_id=a.id AND p.user_id=?)" if restricted else ""
                params = (context["organization_id"], context["id"]) if restricted else (context["organization_id"],)
                rows = db.execute(
                    f"""SELECT r.id,r.assessment_id,r.report_type,r.status,r.created_by,r.created_at,r.content_type,r.filename,r.sha256,a.completed_at,o.name AS organization_name FROM reports r
                       JOIN assessments a ON a.id=r.assessment_id JOIN organizations o ON o.id=a.organization_id
                       WHERE a.organization_id=?{scope} ORDER BY r.created_at DESC,r.id DESC""",
                    params,
                ).fetchall()
                return self.send_json({"reports": [dict(row) for row in rows]})
            if path == "/api/reports" and method == "POST":
                self.require_roles(context, {"COMPANY_ADMIN", "CONSULTANT", "SUPER_ADMIN"})
                assessment_id = int(data.get("assessment_id") or 0)
                assessment = self._assessment(db, assessment_id, context)
                if assessment["status"] != "COMPLETED":
                    raise APIError("assessment_not_completed", 409)
                report_type = str(data.get("report_type") or "EXECUTIVE").upper()
                if report_type not in {"EXECUTIVE", "DETAILED"}:
                    raise APIError("invalid_report_type", 422)
                payload = assessment_pdf(db, assessment_id, report_type == "DETAILED")
                filename = f"nudj-mcm-{assessment_id}-{report_type.lower()}.pdf"
                digest = fingerprint(payload)
                report_id = db.execute("INSERT INTO reports(assessment_id,report_type,status,created_by,created_at,payload,content_type,filename,sha256) VALUES (?,?,?,?,?,?,?,?,?)", (assessment_id, report_type, "READY", context["id"], now(), payload, "application/pdf", filename, digest)).lastrowid
                audit(db, context["id"], "report_generation", "report", report_id, {"assessment_id": assessment_id, "type": report_type, "sha256": digest})
                db.commit()
                return self.send_json({"id": report_id, "assessment_id": assessment_id, "report_type": report_type, "status": "READY", "download_url": f"/api/reports/{report_id}/download"}, 201)
            match = re.fullmatch(r"/api/reports/(\d+)/download", path)
            if match and method == "GET":
                report = db.execute("SELECT r.*,a.organization_id FROM reports r JOIN assessments a ON a.id=r.assessment_id WHERE r.id=?", (int(match.group(1)),)).fetchone()
                if not report or report["organization_id"] != context["organization_id"]:
                    raise APIError("report_not_found", 404)
                self._assessment(db, report["assessment_id"], context)
                payload = bytes(report["payload"]) if report["payload"] is not None else assessment_pdf(db, report["assessment_id"], report["report_type"] == "DETAILED")
                filename = report["filename"] or f"nudj-mcm-{report['assessment_id']}-{report['report_type'].lower()}.pdf"
                if report["payload"] is None:
                    db.execute("UPDATE reports SET payload=?,content_type='application/pdf',filename=?,sha256=? WHERE id=?", (payload, filename, fingerprint(payload), report["id"]))
                audit(db, context["id"], "report_download", "report", report["id"], {"sha256": fingerprint(payload)})
                db.commit()
                return self.send_bytes(payload, report["content_type"] or "application/pdf", filename)
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _export_artifact(self, db, export_format: str, origin: str):
        if export_format in {"XLSX", "CODEBOOK"}:
            return research_workbook(db, origin), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"nudj-mcm-{origin.lower()}.xlsx"
        if export_format == "CSV":
            headers, rows = build_research_sheets(db, origin)["01_RESPONSES_WIDE"]
            return csv_bytes(headers, rows), "text/csv; charset=utf-8", f"nudj-mcm-{origin.lower()}.csv"
        if export_format in {"SPSS", "SAV"}:
            return spss_package(db, origin), "application/zip", f"nudj-mcm-{origin.lower()}-spss-package.zip"
        sheets = build_research_sheets(db, origin)
        headers, rows = sheets["09_INSTRUMENT"]
        payload = _json_dumps({"columns": headers, "rows": rows, "notice": "Research Beta - provisional instrument."})
        return payload, "application/json; charset=utf-8", "nudj-mcm-instrument.json"

    def _research(self, method: str, path: str, query: dict, data: dict, context):
        self.require_roles(context, RESEARCH_ROLES)
        db = connect()
        try:
            if path == "/api/research/summary" and method == "GET":
                counts = {row["data_origin"]: row["count"] for row in db.execute("SELECT data_origin,COUNT(*) AS count FROM assessments GROUP BY data_origin")}
                completed = db.execute("SELECT COUNT(*) FROM assessments WHERE status='COMPLETED'").fetchone()[0]
                incomplete = db.execute("SELECT COUNT(*) FROM assessments WHERE status!='COMPLETED'").fetchone()[0]
                consented = db.execute("SELECT COUNT(*) FROM company_profiles WHERE research_consent=1").fetchone()[0]
                version = db.execute("SELECT id,version,status FROM instrument_versions ORDER BY id DESC LIMIT 1").fetchone()
                sectors = [dict(row) for row in db.execute("SELECT COALESCE(o.sector,'غير محدد') AS label,COUNT(*) AS count FROM assessments a JOIN organizations o ON o.id=a.organization_id GROUP BY o.sector ORDER BY count DESC")]
                return self.send_json({"total_cases": sum(counts.values()), "completed": completed, "incomplete": incomplete, "research_consent_organizations": consented, "origins": counts, "current_instrument": _row(version), "cases_by_sector": sectors, "empty": not bool(sum(counts.values()))})
            if path == "/api/research/dataset" and method == "GET":
                origin = (query.get("data_origin") or ["REAL"])[0]
                sheets = build_research_sheets(db, origin)
                headers, rows = sheets["01_RESPONSES_WIDE"]
                limit = min(500, max(1, int((query.get("limit") or [100])[0])))
                return self.send_json({"data_origin": str(origin).upper(), "columns": headers, "rows": [dict(zip(headers, row)) for row in rows[:limit]], "row_count": len(rows), "pii_included": False})
            if path == "/api/research/statistics" and method == "GET":
                origin = (query.get("data_origin") or ["REAL"])[0]
                sheets = build_research_sheets(db, origin)
                mcm_headers, mcm_rows = sheets["03_MCM_SCORES"]
                smce_headers, smce_rows = sheets["04_SMCE_SCORES"]
                mcm_idx, smce_idx = mcm_headers.index("MCM_TOTAL"), smce_headers.index("SMCE_TOTAL")
                mcm = [float(row[mcm_idx]) for row in mcm_rows if row[mcm_idx] is not None]
                smce = [float(row[smce_idx]) for row in smce_rows if row[smce_idx] is not None]

                def describe(values):
                    if not values:
                        return None
                    return {"n": len(values), "mean": round(statistics.mean(values), 2), "median": round(statistics.median(values), 2), "sd": round(statistics.stdev(values), 2) if len(values) > 1 else None, "min": min(values), "max": max(values)}

                return self.send_json({"data_origin": str(origin).upper(), "MCM": describe(mcm), "SMCE": describe(smce), "reliability": {"available": False, "reason": "NOT_IMPLEMENTED_WITHOUT_VALIDATED_SAMPLE"}, "validity": {"available": False, "reason": "INSTRUMENT_IS_RESEARCH_BETA"}, "empty": not (mcm or smce)})
            if path == "/api/research/data-quality" and method == "GET":
                rows = db.execute("SELECT f.*,a.data_origin,a.completed_at FROM data_quality_flags f JOIN assessments a ON a.id=f.assessment_id ORDER BY f.created_at DESC,f.id DESC").fetchall()
                incomplete = [dict(row) for row in db.execute("SELECT id AS assessment_id,status,data_origin,created_at,updated_at FROM assessments WHERE status!='COMPLETED' ORDER BY updated_at DESC")]
                return self.send_json({"flags": [dict(row) for row in rows], "incomplete_cases": incomplete, "auto_deleted": 0})
            if path == "/api/research/audit" and method == "GET":
                rows = db.execute("SELECT a.*,u.email AS actor_email FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.created_at DESC,a.id DESC LIMIT 500").fetchall()
                return self.send_json({"events": [dict(row) for row in rows]})
            if path == "/api/research/exports" and method == "POST":
                export_format = str(data.get("format") or "XLSX").upper()
                if export_format not in {"XLSX", "CSV", "SPSS", "SAV", "CODEBOOK", "INSTRUMENT"}:
                    raise APIError("unsupported_export_format", 422)
                origin = str(data.get("data_origin") or "REAL").upper()
                payload, content_type, filename = self._export_artifact(db, export_format, origin)
                digest = fingerprint(payload)
                export_id = db.execute("INSERT INTO research_exports(actor_user_id,format,data_origin,filters_json,status,created_at,payload,content_type,filename,sha256) VALUES (?,?,?,?,?,?,?,?,?,?)", (context["id"], export_format, origin, json.dumps(data.get("filters") or {}, ensure_ascii=False), "READY", now(), payload, content_type, filename, digest)).lastrowid
                audit(db, context["id"], "export_generation", "research_export", export_id, {"format": export_format, "data_origin": origin, "sha256": digest})
                db.commit()
                return self.send_json({"id": export_id, "format": export_format, "data_origin": origin, "status": "READY", "download_url": f"/api/research/exports/{export_id}/download"}, 201)
            export_match = re.fullmatch(r"/api/research/exports/(\d+)/download", path)
            if export_match and method == "GET":
                export = db.execute("SELECT * FROM research_exports WHERE id=? AND actor_user_id=?", (int(export_match.group(1)), context["id"])).fetchone()
                if not export:
                    raise APIError("research_export_not_found", 404)
                fmt, origin = export["format"], export["data_origin"]
                if export["payload"] is not None:
                    payload, content_type, filename = bytes(export["payload"]), export["content_type"], export["filename"]
                else:
                    payload, content_type, filename = self._export_artifact(db, fmt, origin)
                    db.execute("UPDATE research_exports SET payload=?,content_type=?,filename=?,sha256=? WHERE id=?", (payload, content_type, filename, fingerprint(payload), export["id"]))
                audit(db, context["id"], "export_download", "research_export", export["id"], {"sha256": fingerprint(payload), "bytes": len(payload)})
                db.commit()
                return self.send_bytes(payload, content_type, filename)
            raise APIError("route_not_found", 404)
        finally:
            db.close()

    def _admin(self, method: str, path: str, data: dict, context):
        self.require_roles(context, {"SUPER_ADMIN"})
        db = connect()
        try:
            if path == "/api/admin" and method == "GET":
                return self.send_json({
                    "organizations": db.execute("SELECT COUNT(*) FROM organizations").fetchone()[0],
                    "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                    "assessments": db.execute("SELECT COUNT(*) FROM assessments").fetchone()[0],
                    "active_sessions": db.execute("SELECT COUNT(*) FROM sessions WHERE expires_at>?", (now(),)).fetchone()[0],
                    "configuration": {row["key"]: json.loads(row["value_json"]) for row in db.execute("SELECT key,value_json FROM system_configuration")},
                    "health": {"database": "ok", "storage": config.STORAGE_MODE},
                })
            if path == "/api/admin/organizations" and method == "GET":
                rows = db.execute("SELECT o.*,COUNT(DISTINCT m.user_id) AS users,COUNT(DISTINCT a.id) AS assessments FROM organizations o LEFT JOIN memberships m ON m.organization_id=o.id LEFT JOIN assessments a ON a.organization_id=o.id GROUP BY o.id ORDER BY o.id DESC").fetchall()
                return self.send_json({"organizations": [dict(row) for row in rows]})
            if path == "/api/admin/users" and method == "GET":
                rows = db.execute("SELECT u.id,u.name,u.email,u.job_title,u.is_active,u.created_at,m.organization_id,m.role,m.status,o.name AS organization_name FROM users u LEFT JOIN memberships m ON m.user_id=u.id LEFT JOIN organizations o ON o.id=m.organization_id ORDER BY u.id DESC").fetchall()
                return self.send_json({"users": [dict(row) for row in rows]})
            if path == "/api/admin/users" and method == "POST":
                email = _slug_email(data.get("email"))
                name = str(data.get("name") or "").strip()
                password = str(data.get("password") or "")
                role = _role(data.get("role"))
                org_id = int(data.get("organization_id") or context["organization_id"])
                if not _valid_email(email) or len(name) < 2 or not _password_ok(password):
                    raise APIError("invalid_user_data", 422)
                if db.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
                    raise APIError("email_already_exists", 409)
                if not db.execute("SELECT 1 FROM organizations WHERE id=?", (org_id,)).fetchone():
                    raise APIError("organization_not_found", 404)
                user_id = db.execute("INSERT INTO users(email,name,password_hash,verified,is_active,created_at) VALUES (?,?,?,1,1,?)", (email, name, password_hash(password), now())).lastrowid
                db.execute("INSERT INTO memberships VALUES (?,?,?,?)", (user_id, org_id, role, "ACTIVE"))
                db.execute("INSERT INTO user_settings(user_id) VALUES (?)", (user_id,))
                audit(db, context["id"], "create", "user", user_id, {"role": role, "organization_id": org_id})
                db.commit()
                return self.send_json({"id": user_id, "email": email, "name": name, "role": role, "organization_id": org_id}, 201)
            user_match = re.fullmatch(r"/api/admin/users/(\d+)", path)
            if user_match and method == "PATCH":
                user_id = int(user_match.group(1))
                user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
                if not user:
                    raise APIError("user_not_found", 404)
                is_active = int(bool(data.get("is_active", user["is_active"])))
                db.execute("UPDATE users SET is_active=?,name=?,job_title=? WHERE id=?", (is_active, str(data.get("name") or user["name"]).strip(), data.get("job_title", user["job_title"]), user_id))
                if not is_active:
                    db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                if data.get("organization_id") and data.get("role"):
                    db.execute("INSERT INTO memberships VALUES (?,?,?,?) ON CONFLICT(user_id,organization_id) DO UPDATE SET role=excluded.role,status=excluded.status", (user_id, int(data["organization_id"]), _role(data["role"]), str(data.get("membership_status") or "ACTIVE").upper()))
                audit(db, context["id"], "update", "user", user_id, {"is_active": bool(is_active)})
                db.commit()
                return self.send_json({"id": user_id, "is_active": bool(is_active)})
            if path == "/api/admin/configuration" and method == "PATCH":
                allowed = {"MIN_BENCHMARK_SAMPLE", "GAP_THRESHOLD", "PRIORITY_WEIGHTS"}
                key = str(data.get("key") or "").upper()
                if key not in allowed:
                    raise APIError("configuration_key_not_allowed", 422)
                value = data.get("value")
                if key == "MIN_BENCHMARK_SAMPLE" and (not isinstance(value, int) or value < 5):
                    raise APIError("benchmark_minimum_invalid", 422)
                db.execute("INSERT INTO system_configuration(key,value_json,updated_by,updated_at) VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_by=excluded.updated_by,updated_at=excluded.updated_at", (key, json.dumps(value, ensure_ascii=False), context["id"], now()))
                audit(db, context["id"], "configuration_change", "system_configuration", None, {"key": key})
                db.commit()
                return self.send_json({"key": key, "value": value})
            raise APIError("route_not_found", 404)
        finally:
            db.close()
