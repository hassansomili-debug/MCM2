"""Minimal production-shaped API for the MCM MVP.

Uses only Python's standard library so the app can run without package installation.
Replace the HTTP server/session implementation with a managed identity provider and
PostgreSQL adapter before public deployment.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
DB_PATH = Path("/tmp/mcm.sqlite3") if __import__("os").environ.get("VERCEL") else ROOT / "mcm.sqlite3"
PORT = 8000

MCM_DIMENSIONS = [
    ("MCM01", "الحوكمة والتوجيه الاستراتيجي"),
    ("MCM02", "ذكاء أصحاب المصلحة والسياق"),
    ("MCM03", "حوكمة المعلومات والنزاهة"),
    ("MCM04", "التنسيق ورحلة العميل"),
    ("MCM05", "مواءمة الوعد والتجربة"),
    ("MCM06", "الأدلة والتعلم التكيفي"),
    ("MCM07", "المأسسة وقابلية التوسع"),
]
SMCE_DIMENSIONS = [
    ("SMCE01", "الاستجابة والحل"),
    ("SMCE02", "جودة التفاعل"),
    ("SMCE03", "كفاءة الفعل"),
    ("SMCE04", "اتساق الخدمة"),
    ("SMCE05", "التعلم من المجتمع"),
]
PLATFORM_ADMIN_EMAIL = "hmsomili@gmail.com"
PLATFORM_ADMIN_PASSWORD_HASH = "d69150839d2b0aab796c8b5b51e159f3$741508a73f4e2816d73b385e331bc424fc314de7cfdda31e88b0ebabd3f0b0a6"


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    salt, expected = stored.split("$", 1)
    actual = password_hash(password, salt).split("$", 1)[1]
    return secrets.compare_digest(actual, expected)


def init_db():
    db = connect()
    db.executescript("""
      CREATE TABLE IF NOT EXISTS organizations (id INTEGER PRIMARY KEY, name TEXT NOT NULL, locale TEXT NOT NULL DEFAULT 'ar');
      CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, password_hash TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS memberships (user_id INTEGER, organization_id INTEGER, role TEXT NOT NULL, PRIMARY KEY(user_id, organization_id), FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(organization_id) REFERENCES organizations(id));
      CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
      CREATE TABLE IF NOT EXISTS instruments (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS instrument_versions (id INTEGER PRIMARY KEY, instrument_id INTEGER NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL, FOREIGN KEY(instrument_id) REFERENCES instruments(id));
      CREATE TABLE IF NOT EXISTS dimensions (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, construct TEXT NOT NULL, name TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, code TEXT NOT NULL, construct TEXT NOT NULL, dimension_code TEXT NOT NULL, prompt_ar TEXT NOT NULL, FOREIGN KEY(version_id) REFERENCES instrument_versions(id));
      CREATE TABLE IF NOT EXISTS assessments (id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL, version_id INTEGER NOT NULL, created_by INTEGER NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL, completed_at INTEGER, FOREIGN KEY(organization_id) REFERENCES organizations(id), FOREIGN KEY(version_id) REFERENCES instrument_versions(id));
      CREATE TABLE IF NOT EXISTS answers (assessment_id INTEGER, item_id INTEGER, value REAL NOT NULL, updated_at INTEGER NOT NULL, PRIMARY KEY(assessment_id, item_id), FOREIGN KEY(assessment_id) REFERENCES assessments(id), FOREIGN KEY(item_id) REFERENCES items(id));
      CREATE TABLE IF NOT EXISTS scores (assessment_id INTEGER, construct TEXT, dimension_code TEXT, score REAL NOT NULL, PRIMARY KEY(assessment_id, construct, dimension_code), FOREIGN KEY(assessment_id) REFERENCES assessments(id));
      CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS organization_profiles (organization_id INTEGER PRIMARY KEY, industry TEXT, website TEXT, completion INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(organization_id) REFERENCES organizations(id));
    CREATE TABLE IF NOT EXISTS invitations (id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL, assessment_id INTEGER, email TEXT NOT NULL, role TEXT NOT NULL, token TEXT UNIQUE NOT NULL, status TEXT NOT NULL, expires_at INTEGER NOT NULL, created_by INTEGER NOT NULL, FOREIGN KEY(organization_id) REFERENCES organizations(id), FOREIGN KEY(assessment_id) REFERENCES assessments(id));
    CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, read_at INTEGER, created_at INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY, locale TEXT NOT NULL DEFAULT 'ar', email_notifications INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(user_id) REFERENCES users(id));
    """)
    if not db.execute("SELECT 1 FROM organizations LIMIT 1").fetchone():
        db.execute("INSERT INTO organizations(name) VALUES (?)", ("أفق الرقمية",))
        db.execute("INSERT INTO users(email,name,password_hash) VALUES (?,?,?)", ("sara@example.com", "سارة الحربي", password_hash("ChangeMe-2026")))
        db.execute("INSERT INTO memberships VALUES (1,1,'admin')")
        db.execute("INSERT INTO organization_profiles(organization_id,industry,completion) VALUES (1,'التسويق الرقمي',100)")
        db.execute("INSERT INTO user_settings(user_id) VALUES (1)")
        db.execute("INSERT INTO notifications(user_id,title,body,created_at) VALUES (1,?,?,?)", ("مرحبًا بك في مساحة العمل", "يمكنك إنشاء أول تقييم من لوحة البيانات.", int(time.time())))
        db.execute("INSERT INTO instruments(name) VALUES (?)", ("MCM / SMCE Core Instrument",))
        db.execute("INSERT INTO instrument_versions(instrument_id,version,status) VALUES (1,'1.0.0','published')")
        for code, name in MCM_DIMENSIONS:
            db.execute("INSERT INTO dimensions(code,construct,name) VALUES (?,?,?)", (code, "MCM", name))
        for code, name in SMCE_DIMENSIONS:
            db.execute("INSERT INTO dimensions(code,construct,name) VALUES (?,?,?)", (code, "SMCE", name))
        item_id = 1
        for construct, dimensions in (("MCM", MCM_DIMENSIONS), ("SMCE", SMCE_DIMENSIONS)):
            for code, name in dimensions:
                for item_number in range(1, 3):
                    db.execute("INSERT INTO items VALUES (?,?,?,?,?,?)", (item_id, 1, f"{code}-{item_number:02d}", construct, code, f"{name} - بند القياس {item_number}"))
                    item_id += 1
        db.commit()
    organization = db.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()
    admin = db.execute("SELECT id FROM users WHERE email=?", (PLATFORM_ADMIN_EMAIL,)).fetchone()
    if not admin:
        cursor = db.execute("INSERT INTO users(email,name,password_hash) VALUES (?,?,?)", (PLATFORM_ADMIN_EMAIL, "مدير منصة نضج MCM", PLATFORM_ADMIN_PASSWORD_HASH))
        db.execute("INSERT OR REPLACE INTO memberships(user_id,organization_id,role) VALUES (?,?,?)", (cursor.lastrowid, organization["id"], "super_admin"))
        db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES (?)", (cursor.lastrowid,))
        db.commit()
    db.close()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class API(BaseHTTPRequestHandler):
    def requested_path(self):
        parsed = urlparse(self.path)
        routed_path = parse_qs(parsed.query).get("route", [""])[0]
        return f"/api{routed_path}" if routed_path else parsed.path

    def send_json(self, value, status=200):
        payload = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def user(self):
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        db = connect()
        row = db.execute("SELECT u.*, m.organization_id, m.role FROM sessions s JOIN users u ON u.id=s.user_id JOIN memberships m ON m.user_id=u.id WHERE s.token=? AND s.expires_at>?", (token, int(time.time()))).fetchone()
        db.close()
        return row

    def require_user(self):
        user = self.user()
        if not user:
            self.send_json({"error": "authentication_required"}, 401)
        return user

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        path = self.requested_path()
        data = self.body()
        db = connect()
        if path == "/api/auth/login":
            user = db.execute("SELECT * FROM users WHERE email=?", (data.get("email", ""),)).fetchone()
            if not user or not verify_password(data.get("password", ""), user["password_hash"]):
                db.close(); return self.send_json({"error": "invalid_credentials"}, 401)
            token = secrets.token_urlsafe(32)
            role = db.execute("SELECT role FROM memberships WHERE user_id=? ORDER BY organization_id LIMIT 1", (user["id"],)).fetchone()["role"]
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (token, user["id"], int(time.time()) + 86_400)); db.commit(); db.close()
            return self.send_json({"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": role}})
        user = self.require_user()
        if not user: db.close(); return
        if path == "/api/assessments":
            if user["role"] not in ("admin", "assessor"):
                db.close(); return self.send_json({"error": "permission_denied"}, 403)
            version = db.execute("SELECT id FROM instrument_versions WHERE status='published' ORDER BY id DESC LIMIT 1").fetchone()
            cursor = db.execute("INSERT INTO assessments(organization_id,version_id,created_by,status,created_at) VALUES (?,?,?,?,?)", (user["organization_id"], version["id"], user["id"], "draft", int(time.time())))
            assessment_id = cursor.lastrowid
            db.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,created_at) VALUES (?,?,?,?,?)", (user["id"], "create", "assessment", assessment_id, int(time.time())))
            db.commit(); db.close(); return self.send_json({"id": assessment_id, "status": "draft", "version_id": version["id"]}, 201)
        if path.startswith("/api/assessments/") and path.endswith("/answers"):
            assessment_id = int(path.split("/")[3])
            assessment = db.execute("SELECT * FROM assessments WHERE id=? AND organization_id=?", (assessment_id, user["organization_id"])).fetchone()
            if not assessment: db.close(); return self.send_json({"error": "assessment_not_found"}, 404)
            now = int(time.time())
            for answer in data.get("answers", []):
                value = float(answer["value"])
                item = db.execute("SELECT id FROM items WHERE id=? AND version_id=?", (answer["item_id"], assessment["version_id"])).fetchone()
                if not item or value < 0 or value > 5:
                    db.close(); return self.send_json({"error": "invalid_answer"}, 422)
                db.execute("INSERT INTO answers VALUES (?,?,?,?) ON CONFLICT(assessment_id,item_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (assessment_id, answer["item_id"], value, now))
            db.commit(); db.close(); return self.send_json({"saved": len(data.get("answers", [])), "saved_at": now})
        if path.startswith("/api/assessments/") and path.endswith("/submit"):
            assessment_id = int(path.split("/")[3])
            assessment = db.execute("SELECT * FROM assessments WHERE id=? AND organization_id=?", (assessment_id, user["organization_id"])).fetchone()
            if not assessment: db.close(); return self.send_json({"error": "assessment_not_found"}, 404)
            answers = db.execute("SELECT i.construct,i.dimension_code,a.value FROM answers a JOIN items i ON i.id=a.item_id WHERE a.assessment_id=?", (assessment_id,)).fetchall()
            if not answers: db.close(); return self.send_json({"error": "answers_required"}, 422)
            db.execute("DELETE FROM scores WHERE assessment_id=?", (assessment_id,))
            for construct in ("MCM", "SMCE"):
                groups = {}
                for row in answers:
                    if row["construct"] == construct: groups.setdefault(row["dimension_code"], []).append(row["value"])
                for dimension_code, values in groups.items():
                    db.execute("INSERT INTO scores VALUES (?,?,?,?)", (assessment_id, construct, dimension_code, round(sum(values) / len(values) * 20, 2)))
            db.execute("UPDATE assessments SET status='completed',completed_at=? WHERE id=?", (int(time.time()), assessment_id))
            db.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,created_at) VALUES (?,?,?,?,?)", (user["id"], "score", "assessment", assessment_id, int(time.time())))
            db.commit(); db.close(); return self.send_json(self.assessment_payload(assessment_id, user["organization_id"]))
        if path == "/api/instrument-versions/import":
            if user["role"] not in ("admin", "researcher"):
                db.close(); return self.send_json({"error": "permission_denied"}, 403)
            tables = data.get("tables", {})
            items = tables.get("ITEMS", [])
            dimensions = tables.get("DIMENSIONS", [])
            if not items or not dimensions:
                db.close(); return self.send_json({"error": "items_and_dimensions_required"}, 422)
            instrument = db.execute("SELECT id FROM instruments ORDER BY id LIMIT 1").fetchone()
            latest = db.execute("SELECT version FROM instrument_versions WHERE instrument_id=? ORDER BY id DESC LIMIT 1", (instrument["id"],)).fetchone()
            current_major = int(str(latest["version"]).split(".")[0]) if latest else 0
            next_version = f"{current_major + 1}.0.0"
            cursor = db.execute("INSERT INTO instrument_versions(instrument_id,version,status) VALUES (?,?,?)", (instrument["id"], next_version, "draft"))
            version_id = cursor.lastrowid
            for dimension in dimensions:
                code = dimension.get("dimension_code") or dimension.get("code")
                name = dimension.get("name_ar") or dimension.get("name") or code
                construct = str(dimension.get("construct") or dimension.get("measure") or "MCM").upper()
                db.execute("INSERT OR IGNORE INTO dimensions(code,construct,name) VALUES (?,?,?)", (code, construct, name))
            for item in items:
                code = item.get("item_code") or item.get("code")
                dimension_code = item.get("dimension_code") or item.get("dimension")
                construct = str(item.get("construct") or item.get("measure") or "MCM").upper()
                prompt = item.get("prompt_ar") or item.get("prompt") or code
                if not code or not dimension_code: continue
                db.execute("INSERT INTO items(version_id,code,construct,dimension_code,prompt_ar) VALUES (?,?,?,?,?)", (version_id, code, construct, dimension_code, prompt))
            db.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,created_at) VALUES (?,?,?,?,?)", (user["id"], "import", "instrument_version", version_id, int(time.time())))
            db.commit(); db.close(); return self.send_json({"id": version_id, "version": next_version, "status": "draft"}, 201)
        if path.startswith("/api/instrument-versions/") and path.endswith("/approve"):
            if user["role"] not in ("admin", "researcher"):
                db.close(); return self.send_json({"error": "permission_denied"}, 403)
            version_id = int(path.split("/")[3])
            version = db.execute("SELECT id FROM instrument_versions WHERE id=? AND status='draft'", (version_id,)).fetchone()
            if not version:
                db.close(); return self.send_json({"error": "draft_version_not_found"}, 404)
            db.execute("UPDATE instrument_versions SET status='published' WHERE id=?", (version_id,))
            db.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,created_at) VALUES (?,?,?,?,?)", (user["id"], "approve", "instrument_version", version_id, int(time.time())))
            db.commit(); db.close(); return self.send_json({"id": version_id, "status": "published"})
        if path == "/api/invitations":
            if user["role"] not in ("admin", "assessor"):
                db.close(); return self.send_json({"error": "permission_denied"}, 403)
            email = str(data.get("email", "")).strip()
            if "@" not in email:
                db.close(); return self.send_json({"error": "valid_email_required"}, 422)
            token = secrets.token_urlsafe(24); expires_at = int(time.time()) + 7 * 86_400
            cursor = db.execute("INSERT INTO invitations(organization_id,assessment_id,email,role,token,status,expires_at,created_by) VALUES (?,?,?,?,?,?,?,?)", (user["organization_id"], data.get("assessment_id"), email, data.get("role", "respondent"), token, "pending", expires_at, user["id"]))
            db.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,created_at) VALUES (?,?,?,?,?)", (user["id"], "invite", "invitation", cursor.lastrowid, int(time.time())))
            db.commit(); db.close(); return self.send_json({"id": cursor.lastrowid, "email": email, "status": "pending", "expires_at": expires_at}, 201)
        if path == "/api/notifications/read":
            db.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (int(time.time()), user["id"])); db.commit(); db.close(); return self.send_json({"marked_read": True})
        if path == "/api/settings":
            locale = data.get("locale", "ar")
            if locale not in ("ar", "en"):
                db.close(); return self.send_json({"error": "unsupported_locale"}, 422)
            db.execute("INSERT INTO user_settings(user_id,locale,email_notifications) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET locale=excluded.locale,email_notifications=excluded.email_notifications", (user["id"], locale, int(bool(data.get("email_notifications", True)))))
            db.commit(); db.close(); return self.send_json({"locale": locale, "email_notifications": bool(data.get("email_notifications", True))})
        if path == "/api/admin/users":
            if user["role"] != "super_admin":
                db.close(); return self.send_json({"error": "permission_denied"}, 403)
            email = str(data.get("email", "")).strip().lower()
            name = str(data.get("name", "")).strip()
            password = str(data.get("password", ""))
            role = str(data.get("role", "company_respondent")).strip().lower()
            roles = {"company_respondent", "company_admin", "consultant", "researcher", "super_admin"}
            if "@" not in email or not name or len(password) < 8 or role not in roles:
                db.close(); return self.send_json({"error": "invalid_user_data"}, 422)
            organization_id = data.get("organization_id") or user["organization_id"]
            if not db.execute("SELECT 1 FROM organizations WHERE id=?", (organization_id,)).fetchone():
                db.close(); return self.send_json({"error": "organization_not_found"}, 404)
            if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                db.close(); return self.send_json({"error": "email_already_exists"}, 409)
            cursor = db.execute("INSERT INTO users(email,name,password_hash) VALUES (?,?,?)", (email, name, password_hash(password)))
            db.execute("INSERT INTO memberships(user_id,organization_id,role) VALUES (?,?,?)", (cursor.lastrowid, organization_id, role))
            db.execute("INSERT INTO user_settings(user_id) VALUES (?)", (cursor.lastrowid,))
            db.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,created_at) VALUES (?,?,?,?,?)", (user["id"], "create", "user", cursor.lastrowid, int(time.time())))
            db.commit(); db.close(); return self.send_json({"id": cursor.lastrowid, "email": email, "name": name, "role": role}, 201)
        db.close(); self.send_json({"error": "route_not_found"}, 404)

    def assessment_payload(self, assessment_id, organization_id):
        db = connect()
        assessment = db.execute("SELECT id,status,version_id,created_at,completed_at FROM assessments WHERE id=? AND organization_id=?", (assessment_id, organization_id)).fetchone()
        scores = db.execute("SELECT s.construct,s.dimension_code,s.score,d.name FROM scores s LEFT JOIN dimensions d ON d.code=s.dimension_code WHERE s.assessment_id=? ORDER BY s.construct,s.dimension_code", (assessment_id,)).fetchall()
        answers = {row["item_id"]: row["value"] for row in db.execute("SELECT item_id,value FROM answers WHERE assessment_id=?", (assessment_id,))}
        db.close()
        grouped = {"MCM": [], "SMCE": []}
        for score in scores: grouped[score["construct"]].append(dict(score))
        return {"assessment": dict(assessment), "scores": grouped, "answers": answers}

    def do_GET(self):
        path = self.requested_path()
        if not path.startswith("/api/"):
            file_path = ROOT / ("index.html" if path in ("", "/") else path.lstrip("/"))
            if file_path.is_file() and file_path.parent == ROOT:
                payload = file_path.read_bytes()
                content_type = "text/html; charset=utf-8" if file_path.suffix == ".html" else "text/css; charset=utf-8" if file_path.suffix == ".css" else "application/javascript; charset=utf-8"
                self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
            return self.send_json({"error": "not_found"}, 404)
        user = self.require_user()
        if not user: return
        db = connect()
        if path == "/api/me":
            result = {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"], "organization": user["organization_id"]}
        elif path == "/api/admin/users":
            if user["role"] != "super_admin":
                db.close(); return self.send_json({"error": "permission_denied"}, 403)
            result = {"users": [dict(row) for row in db.execute("SELECT u.id,u.name,u.email,m.role,m.organization_id FROM users u LEFT JOIN memberships m ON m.user_id=u.id ORDER BY u.id") ]}
        elif path == "/api/organizations":
            result = {"organizations": [dict(row) for row in db.execute("SELECT o.id,o.name,o.locale,m.role FROM organizations o JOIN memberships m ON m.organization_id=o.id WHERE m.user_id=?", (user["id"],))]}
        elif path == "/api/notifications":
            result = {"notifications": [dict(row) for row in db.execute("SELECT id,title,body,read_at,created_at FROM notifications WHERE user_id=? ORDER BY created_at DESC", (user["id"],))]}
        elif path == "/api/settings":
            row = db.execute("SELECT locale,email_notifications FROM user_settings WHERE user_id=?", (user["id"],)).fetchone()
            profile = db.execute("SELECT industry,website,completion FROM organization_profiles WHERE organization_id=?", (user["organization_id"],)).fetchone()
            result = {"user": dict(row) if row else {"locale": "ar", "email_notifications": 1}, "organization": dict(profile) if profile else {"completion": 0}}
        elif path == "/api/invitations":
            result = {"invitations": [dict(row) for row in db.execute("SELECT id,email,role,status,expires_at,assessment_id FROM invitations WHERE organization_id=? ORDER BY id DESC", (user["organization_id"],))]}
        elif path == "/api/instruments":
            result = {"versions": [dict(row) for row in db.execute("SELECT iv.id,iv.version,iv.status,i.name FROM instrument_versions iv JOIN instruments i ON i.id=iv.instrument_id ORDER BY iv.id DESC")]}
        elif path == "/api/assessments":
            result = {"assessments": [dict(row) for row in db.execute("SELECT id,status,version_id,created_at,completed_at FROM assessments WHERE organization_id=? ORDER BY id DESC", (user["organization_id"],))]}
        elif path.startswith("/api/assessments/"):
            assessment_id = int(path.split("/")[3])
            items = [dict(row) for row in db.execute("SELECT id,code,construct,dimension_code,prompt_ar FROM items WHERE version_id=(SELECT version_id FROM assessments WHERE id=? AND organization_id=?) ORDER BY id", (assessment_id, user["organization_id"]))]
            result = {**self.assessment_payload(assessment_id, user["organization_id"]), "items": items}
        elif path == "/api/dashboard":
            latest = db.execute("SELECT id FROM assessments WHERE organization_id=? AND status='completed' ORDER BY completed_at DESC LIMIT 1", (user["organization_id"],)).fetchone()
            if latest: result = self.assessment_payload(latest["id"], user["organization_id"])
            else: result = {"assessment": None, "scores": {"MCM": [], "SMCE": []}}
        else:
            db.close(); return self.send_json({"error": "route_not_found"}, 404)
        db.close(); self.send_json(result)

    def log_message(self, *_):
        return


if __name__ == "__main__":
    init_db()
    print(f"MCM API listening on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), API).serve_forever()
