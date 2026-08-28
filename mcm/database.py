from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager

from . import config


def now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA journal_mode = WAL")
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def password_hash(password: str, salt: str | None = None, iterations: int = 310_000) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, raw_iterations, salt, expected = stored.split("$", 3)
            actual = password_hash(password, salt, int(raw_iterations)).rsplit("$", 1)[1]
        else:
            salt, expected = stored.split("$", 1)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return secrets.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}


def _ensure_columns(db: sqlite3.Connection, table: str, definitions: dict[str, str]) -> None:
    existing = _columns(db, table)
    for name, definition in definitions.items():
        if name not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS organizations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  locale TEXT NOT NULL DEFAULT 'ar',
  sector TEXT,
  subsector TEXT,
  size TEXT,
  country TEXT,
  region TEXT,
  data_origin TEXT NOT NULL DEFAULT 'REAL',
  created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  job_title TEXT,
  phone TEXT,
  preferred_language TEXT NOT NULL DEFAULT 'ar',
  verified INTEGER NOT NULL DEFAULT 1,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memberships (
  user_id INTEGER NOT NULL,
  organization_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  PRIMARY KEY(user_id, organization_id),
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(organization_id) REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  active_org_id INTEGER,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL DEFAULT 0,
  last_seen_at INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(active_org_id) REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS consents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  participant_id INTEGER,
  consent_type TEXT NOT NULL,
  consent_version TEXT NOT NULL,
  accepted INTEGER NOT NULL,
  accepted_at INTEGER NOT NULL,
  UNIQUE(user_id, participant_id, consent_type, consent_version)
);
CREATE TABLE IF NOT EXISTS company_profiles (
  organization_id INTEGER PRIMARY KEY,
  website TEXT,
  business_model TEXT,
  employee_count TEXT,
  annual_revenue_band TEXT,
  communication_team_size TEXT,
  channels_json TEXT NOT NULL DEFAULT '[]',
  crm_system TEXT,
  analytics_system TEXT,
  research_consent INTEGER NOT NULL DEFAULT 0,
  completion INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(organization_id) REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS organization_profiles (
  organization_id INTEGER PRIMARY KEY,
  industry TEXT,
  website TEXT,
  completion INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(organization_id) REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS instruments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS instrument_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instrument_id INTEGER NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  notes TEXT,
  created_by INTEGER,
  created_at INTEGER NOT NULL DEFAULT 0,
  published_at INTEGER,
  archived_at INTEGER,
  UNIQUE(instrument_id, version),
  FOREIGN KEY(instrument_id) REFERENCES instruments(id)
);
CREATE TABLE IF NOT EXISTS dimensions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id INTEGER,
  code TEXT NOT NULL,
  construct TEXT NOT NULL,
  name TEXT NOT NULL,
  name_en TEXT,
  weight REAL NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE(version_id, code),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
);
CREATE TABLE IF NOT EXISTS scales (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  response_type TEXT NOT NULL DEFAULT 'LIKERT',
  min_value REAL,
  max_value REAL,
  UNIQUE(version_id, code),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
);
CREATE TABLE IF NOT EXISTS scale_values (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scale_id INTEGER NOT NULL,
  value REAL,
  label_ar TEXT,
  label_en TEXT,
  missing_type TEXT,
  FOREIGN KEY(scale_id) REFERENCES scales(id)
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  construct TEXT NOT NULL,
  dimension_code TEXT NOT NULL,
  prompt_ar TEXT NOT NULL,
  prompt_en TEXT,
  source TEXT,
  lifecycle_status TEXT NOT NULL DEFAULT 'PILOT',
  reverse_coded INTEGER NOT NULL DEFAULT 0,
  required INTEGER NOT NULL DEFAULT 1,
  weight REAL NOT NULL DEFAULT 1,
  response_type TEXT NOT NULL DEFAULT 'LIKERT',
  min_value REAL DEFAULT 1,
  max_value REAL DEFAULT 5,
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE(version_id, code),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
);
CREATE TABLE IF NOT EXISTS maturity_levels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  label_ar TEXT NOT NULL,
  label_en TEXT NOT NULL,
  min_score REAL NOT NULL,
  max_score REAL NOT NULL,
  level_order INTEGER NOT NULL,
  UNIQUE(version_id, code),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
);
CREATE TABLE IF NOT EXISTS assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id INTEGER NOT NULL,
  version_id INTEGER NOT NULL,
  created_by INTEGER NOT NULL,
  assessment_type TEXT NOT NULL DEFAULT 'FULL',
  status TEXT NOT NULL,
  data_origin TEXT NOT NULL DEFAULT 'REAL',
  parent_assessment_id INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT 0,
  submitted_at INTEGER,
  completed_at INTEGER,
  FOREIGN KEY(organization_id) REFERENCES organizations(id),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id),
  FOREIGN KEY(parent_assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS participants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  research_id TEXT UNIQUE,
  organization_id INTEGER NOT NULL,
  user_id INTEGER,
  full_name TEXT,
  email TEXT,
  job_title TEXT,
  department TEXT,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(organization_id) REFERENCES organizations(id),
  FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS assessment_participants (
  assessment_id INTEGER NOT NULL,
  participant_id INTEGER NOT NULL,
  assessment_role TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'INVITED',
  PRIMARY KEY(assessment_id, participant_id),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(participant_id) REFERENCES participants(id)
);
CREATE TABLE IF NOT EXISTS responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  participant_id INTEGER NOT NULL DEFAULT 0,
  item_id INTEGER NOT NULL,
  numeric_value REAL,
  text_value TEXT,
  missing_type TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(assessment_id, participant_id, item_id),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(item_id) REFERENCES items(id)
);
CREATE TABLE IF NOT EXISTS answers (
  assessment_id INTEGER,
  item_id INTEGER,
  value REAL NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(assessment_id, item_id),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(item_id) REFERENCES items(id)
);
CREATE TABLE IF NOT EXISTS assessment_scores (
  assessment_id INTEGER NOT NULL,
  construct TEXT NOT NULL,
  total_score REAL NOT NULL,
  maturity_level_id INTEGER,
  answered_count INTEGER NOT NULL,
  method_version TEXT NOT NULL,
  calculated_at INTEGER NOT NULL,
  PRIMARY KEY(assessment_id, construct),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(maturity_level_id) REFERENCES maturity_levels(id)
);
CREATE TABLE IF NOT EXISTS score_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  run_number INTEGER NOT NULL,
  instrument_version_id INTEGER NOT NULL,
  scoring_version TEXT NOT NULL,
  configuration_json TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  output_hash TEXT,
  is_current INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  UNIQUE(assessment_id, run_number),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(instrument_version_id) REFERENCES instrument_versions(id)
);
CREATE TABLE IF NOT EXISTS response_item_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  score_run_id INTEGER NOT NULL,
  item_id INTEGER NOT NULL,
  raw_value REAL,
  effective_value REAL,
  normalized_score REAL,
  reverse_coded INTEGER NOT NULL,
  item_weight REAL NOT NULL,
  FOREIGN KEY(score_run_id) REFERENCES score_runs(id),
  FOREIGN KEY(item_id) REFERENCES items(id)
);
CREATE TABLE IF NOT EXISTS score_run_dimensions (
  score_run_id INTEGER NOT NULL,
  dimension_code TEXT NOT NULL,
  construct TEXT NOT NULL,
  score REAL,
  answered_count INTEGER NOT NULL,
  eligible_count INTEGER NOT NULL,
  PRIMARY KEY(score_run_id, dimension_code),
  FOREIGN KEY(score_run_id) REFERENCES score_runs(id)
);
CREATE TABLE IF NOT EXISTS score_run_totals (
  score_run_id INTEGER NOT NULL,
  construct TEXT NOT NULL,
  total_score REAL,
  maturity_level_id INTEGER,
  PRIMARY KEY(score_run_id, construct),
  FOREIGN KEY(score_run_id) REFERENCES score_runs(id),
  FOREIGN KEY(maturity_level_id) REFERENCES maturity_levels(id)
);
CREATE TABLE IF NOT EXISTS dimension_scores (
  assessment_id INTEGER NOT NULL,
  dimension_code TEXT NOT NULL,
  construct TEXT NOT NULL,
  score REAL NOT NULL,
  answered_count INTEGER NOT NULL,
  eligible_count INTEGER NOT NULL,
  method_version TEXT NOT NULL,
  calculated_at INTEGER NOT NULL,
  PRIMARY KEY(assessment_id, dimension_code),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS scores (
  assessment_id INTEGER,
  construct TEXT,
  dimension_code TEXT,
  score REAL NOT NULL,
  PRIMARY KEY(assessment_id, construct, dimension_code),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS diagnostic_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  name_ar TEXT NOT NULL,
  dimensions TEXT NOT NULL,
  operator TEXT NOT NULL,
  threshold REAL NOT NULL,
  severity TEXT NOT NULL,
  confidence REAL NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(version_id, code),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
);
CREATE TABLE IF NOT EXISTS diagnostic_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  rule_id INTEGER NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(assessment_id, rule_id),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(rule_id) REFERENCES diagnostic_rules(id)
);
CREATE TABLE IF NOT EXISTS recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id INTEGER NOT NULL,
  dimension_code TEXT NOT NULL,
  problem TEXT NOT NULL,
  action TEXT NOT NULL,
  why_it_matters TEXT,
  implementation_guidance TEXT,
  suggested_owner TEXT,
  expected_impact TEXT NOT NULL DEFAULT 'HIGH',
  effort TEXT NOT NULL DEFAULT 'MEDIUM',
  time_horizon TEXT NOT NULL DEFAULT '31-90',
  kpi TEXT,
  evidence_source TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(version_id, dimension_code),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
);
CREATE TABLE IF NOT EXISTS assessment_recommendations (
  assessment_id INTEGER NOT NULL,
  recommendation_id INTEGER NOT NULL,
  priority_score REAL NOT NULL,
  gap REAL NOT NULL,
  rank INTEGER NOT NULL,
  rationale TEXT,
  PRIMARY KEY(assessment_id, recommendation_id),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(recommendation_id) REFERENCES recommendations(id)
);
CREATE TABLE IF NOT EXISTS roadmap_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  recommendation_id INTEGER,
  horizon TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  owner TEXT,
  status TEXT NOT NULL DEFAULT 'NOT_STARTED',
  target_date TEXT,
  impact TEXT,
  effort TEXT,
  kpi TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(recommendation_id) REFERENCES recommendations(id)
);
CREATE TABLE IF NOT EXISTS invitations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id INTEGER NOT NULL,
  assessment_id INTEGER,
  email TEXT NOT NULL,
  full_name TEXT,
  job_title TEXT,
  department TEXT,
  role TEXT NOT NULL,
  token TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_by INTEGER NOT NULL,
  accepted_at INTEGER,
  FOREIGN KEY(organization_id) REFERENCES organizations(id),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS participant_sessions (
  token TEXT PRIMARY KEY,
  participant_id INTEGER,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  assessment_id INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  FOREIGN KEY(participant_id) REFERENCES participants(id),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  type TEXT NOT NULL DEFAULT 'INFO',
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  target_url TEXT,
  read_at INTEGER,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS user_settings (
  user_id INTEGER PRIMARY KEY,
  locale TEXT NOT NULL DEFAULT 'ar',
  email_notifications INTEGER NOT NULL DEFAULT 1,
  security_notifications INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  report_type TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  payload BLOB,
  content_type TEXT,
  filename TEXT,
  sha256 TEXT,
  FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS research_exports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_user_id INTEGER NOT NULL,
  format TEXT NOT NULL,
  data_origin TEXT NOT NULL,
  filters_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  payload BLOB,
  content_type TEXT,
  filename TEXT,
  sha256 TEXT
);
CREATE TABLE IF NOT EXISTS data_quality_flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  flag_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  details TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN',
  created_at INTEGER NOT NULL,
  UNIQUE(assessment_id, flag_type),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS system_configuration (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_by INTEGER,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memberships_org ON memberships(organization_id, role);
CREATE INDEX IF NOT EXISTS idx_sessions_user_expiry ON sessions(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_assessments_org_status ON assessments(organization_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_responses_assessment ON responses(assessment_id, participant_id);
CREATE INDEX IF NOT EXISTS idx_dimension_scores_assessment ON dimension_scores(assessment_id, construct);
CREATE INDEX IF NOT EXISTS idx_score_runs_assessment ON score_runs(assessment_id, is_current, created_at);
CREATE INDEX IF NOT EXISTS idx_invitations_token_status ON invitations(token, status);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity, entity_id, created_at);
"""


def _migrate_legacy(db: sqlite3.Connection) -> None:
    additions = {
        "organizations": {
            "sector": "TEXT", "subsector": "TEXT", "size": "TEXT", "country": "TEXT",
            "region": "TEXT", "data_origin": "TEXT NOT NULL DEFAULT 'REAL'", "created_at": "INTEGER NOT NULL DEFAULT 0",
        },
        "users": {
            "job_title": "TEXT", "phone": "TEXT", "preferred_language": "TEXT NOT NULL DEFAULT 'ar'",
            "verified": "INTEGER NOT NULL DEFAULT 1", "is_active": "INTEGER NOT NULL DEFAULT 1", "created_at": "INTEGER NOT NULL DEFAULT 0",
        },
        "memberships": {"status": "TEXT NOT NULL DEFAULT 'ACTIVE'"},
        "sessions": {"active_org_id": "INTEGER", "created_at": "INTEGER NOT NULL DEFAULT 0", "last_seen_at": "INTEGER NOT NULL DEFAULT 0"},
        "instruments": {"code": "TEXT", "status": "TEXT NOT NULL DEFAULT 'ACTIVE'", "created_at": "INTEGER NOT NULL DEFAULT 0"},
        "instrument_versions": {"notes": "TEXT", "created_by": "INTEGER", "created_at": "INTEGER NOT NULL DEFAULT 0", "published_at": "INTEGER", "archived_at": "INTEGER"},
        "dimensions": {"version_id": "INTEGER", "name_en": "TEXT", "weight": "REAL NOT NULL DEFAULT 1", "sort_order": "INTEGER NOT NULL DEFAULT 0"},
        "items": {
            "prompt_en": "TEXT", "source": "TEXT", "lifecycle_status": "TEXT NOT NULL DEFAULT 'PILOT'",
            "reverse_coded": "INTEGER NOT NULL DEFAULT 0", "required": "INTEGER NOT NULL DEFAULT 1",
            "weight": "REAL NOT NULL DEFAULT 1", "response_type": "TEXT NOT NULL DEFAULT 'LIKERT'",
            "min_value": "REAL DEFAULT 1", "max_value": "REAL DEFAULT 5", "sort_order": "INTEGER NOT NULL DEFAULT 0",
        },
        "assessments": {
            "assessment_type": "TEXT NOT NULL DEFAULT 'FULL'", "data_origin": "TEXT NOT NULL DEFAULT 'REAL'",
            "parent_assessment_id": "INTEGER", "updated_at": "INTEGER NOT NULL DEFAULT 0", "submitted_at": "INTEGER",
        },
        "invitations": {"full_name": "TEXT", "job_title": "TEXT", "department": "TEXT", "accepted_at": "INTEGER"},
        "participant_sessions": {"participant_id": "INTEGER"},
        "notifications": {"type": "TEXT NOT NULL DEFAULT 'INFO'", "target_url": "TEXT"},
        "user_settings": {"security_notifications": "INTEGER NOT NULL DEFAULT 1"},
        "reports": {"payload": "BLOB", "content_type": "TEXT", "filename": "TEXT", "sha256": "TEXT"},
        "research_exports": {"payload": "BLOB", "content_type": "TEXT", "filename": "TEXT", "sha256": "TEXT"},
        "audit_logs": {"metadata_json": "TEXT NOT NULL DEFAULT '{}'"},
    }
    for table, definitions in additions.items():
        if _columns(db, table):
            _ensure_columns(db, table, definitions)
    db.execute("UPDATE memberships SET role=CASE lower(role) WHEN 'admin' THEN 'COMPANY_ADMIN' WHEN 'assessor' THEN 'CONSULTANT' WHEN 'respondent' THEN 'COMPANY_RESPONDENT' ELSE upper(role) END")
    db.execute("UPDATE dimensions SET version_id=COALESCE(version_id, 1)")


def audit(db: sqlite3.Connection, user_id: int | None, action: str, entity: str, entity_id: int | None = None, metadata: dict | None = None) -> None:
    db.execute(
        "INSERT INTO audit_logs(user_id,action,entity,entity_id,metadata_json,created_at) VALUES (?,?,?,?,?,?)",
        (user_id, action, entity, entity_id, json.dumps(metadata or {}, ensure_ascii=False), now()),
    )


def _seed_version(db: sqlite3.Connection, instrument_id: int, version: str) -> int:
    timestamp = now()
    cur = db.execute(
        "INSERT INTO instrument_versions(instrument_id,version,status,notes,created_at,published_at) VALUES (?,?,?,?,?,?)",
        (instrument_id, version, "PILOT", "Research Beta - provisional instrument", timestamp, timestamp),
    )
    version_id = int(cur.lastrowid)
    dimension_groups = [
        ("MCM", config.MCM_DIMENSIONS), ("SMCE", config.SMCE_DIMENSIONS),
        ("ENABLER", config.ENABLER_DIMENSIONS), ("OUTCOME", config.OUTCOME_DIMENSIONS),
    ]
    order = 0
    for construct, dimensions in dimension_groups:
        for code, name_ar, name_en in dimensions:
            order += 1
            db.execute(
                "INSERT OR IGNORE INTO dimensions(version_id,code,construct,name,name_en,weight,sort_order) VALUES (?,?,?,?,?,?,?)",
                (version_id, code, construct, name_ar, name_en, 1, order),
            )
    scale = db.execute(
        "INSERT INTO scales(version_id,code,response_type,min_value,max_value) VALUES (?,?,?,?,?)",
        (version_id, "LIKERT_1_5", "LIKERT", 1, 5),
    ).lastrowid
    labels = [(1, "لا ينطبق إطلاقًا", "Not at all"), (2, "ينطبق بدرجة ضعيفة", "Slightly"), (3, "ينطبق جزئيًا", "Partly"), (4, "ينطبق بدرجة كبيرة", "Mostly"), (5, "ينطبق بالكامل", "Fully")]
    for value, ar, en in labels:
        db.execute("INSERT INTO scale_values(scale_id,value,label_ar,label_en) VALUES (?,?,?,?)", (scale, value, ar, en))
    item_order = 0
    for construct, dimensions in dimension_groups:
        for code, _, _ in dimensions:
            for index, prompt in enumerate(config.ITEM_PROMPTS[code], 1):
                item_order += 1
                required = 0 if construct == "OUTCOME" else 1
                db.execute(
                    """INSERT INTO items(version_id,code,construct,dimension_code,prompt_ar,prompt_en,source,lifecycle_status,reverse_coded,required,weight,response_type,min_value,max_value,sort_order)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (version_id, f"{code}_{index:02d}", construct, code, prompt, None, "DEMO provisional item bank - not empirically validated", "PILOT", 0, required, 1, "LIKERT", 1, 5, item_order),
                )
    for level in config.MATURITY_LEVELS:
        db.execute(
            "INSERT INTO maturity_levels(version_id,code,label_ar,label_en,min_score,max_score,level_order) VALUES (?,?,?,?,?,?,?)",
            (version_id, *level),
        )
    for code, name_ar, dimensions, operator, threshold, severity, confidence in config.DIAGNOSTIC_RULES:
        db.execute(
            "INSERT INTO diagnostic_rules(version_id,code,name_ar,dimensions,operator,threshold,severity,confidence) VALUES (?,?,?,?,?,?,?,?)",
            (version_id, code, name_ar, dimensions, operator, threshold, severity, confidence),
        )
    for code, (problem, action, owner, kpi) in config.RECOMMENDATIONS.items():
        db.execute(
            """INSERT INTO recommendations(version_id,dimension_code,problem,action,why_it_matters,implementation_guidance,suggested_owner,expected_impact,effort,time_horizon,kpi,evidence_source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (version_id, code, problem, action, "إغلاق الفجوة يحسن اتساق القرار والتنفيذ.", action, owner, "HIGH", "MEDIUM", "31-90", kpi, "MCM provisional evidence library v0.1"),
        )
    return version_id


def _ensure_seed_data(db: sqlite3.Connection) -> None:
    timestamp = now()
    organization = db.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()
    if not organization:
        organization_id = db.execute(
            "INSERT INTO organizations(name,locale,sector,size,country,region,data_origin,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (config.BOOTSTRAP_ORG_NAME, "ar", "التسويق الرقمي" if config.SEED_DEMO else None, "SMALL" if config.SEED_DEMO else None, "Saudi Arabia", "Riyadh", "DEMO" if config.SEED_DEMO else "TEST", timestamp),
        ).lastrowid
    else:
        organization_id = organization["id"]
    db.execute(
        "INSERT OR IGNORE INTO company_profiles(organization_id,website,business_model,employee_count,communication_team_size,completion,updated_at) VALUES (?,?,?,?,?,?,?)",
        (organization_id, "https://example.com", "B2B", "11-50", "2-5", 100, timestamp),
    )
    seed_users = [(config.PLATFORM_ADMIN_EMAIL, "مدير منصة نضج", config.PLATFORM_ADMIN_PASSWORD, "SUPER_ADMIN")]
    if config.SEED_DEMO:
        seed_users.insert(0, (config.DEMO_EMAIL, "سارة الحربي", config.DEMO_PASSWORD, "COMPANY_ADMIN"))
    for email, name, password, role in seed_users:
        row = db.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
        if row:
            user_id = row["id"]
        else:
            user_id = db.execute(
                "INSERT INTO users(email,name,password_hash,preferred_language,verified,is_active,created_at) VALUES (?,?,?,?,?,?,?)",
                (email, name, password_hash(password), "ar", 1, 1, timestamp),
            ).lastrowid
        db.execute(
            "INSERT OR IGNORE INTO memberships(user_id,organization_id,role,status) VALUES (?,?,?,?)",
            (user_id, organization_id, role, "ACTIVE"),
        )
        db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES (?)", (user_id,))
    instrument = db.execute("SELECT id FROM instruments WHERE code='MCM_CORE' ORDER BY id LIMIT 1").fetchone()
    if instrument:
        instrument_id = instrument["id"]
    else:
        legacy = db.execute("SELECT id FROM instruments ORDER BY id LIMIT 1").fetchone()
        if legacy:
            instrument_id = legacy["id"]
            db.execute("UPDATE instruments SET code='MCM_CORE',status='ACTIVE',created_at=CASE WHEN created_at=0 THEN ? ELSE created_at END WHERE id=?", (timestamp, instrument_id))
        else:
            instrument_id = db.execute("INSERT INTO instruments(code,name,status,created_at) VALUES (?,?,?,?)", ("MCM_CORE", "MCM / SMCE Scientific Instrument", "ACTIVE", timestamp)).lastrowid
    versions = db.execute(
        """SELECT v.id,v.version,COUNT(i.id) AS item_count
           FROM instrument_versions v LEFT JOIN items i ON i.version_id=v.id
           WHERE v.instrument_id=? GROUP BY v.id ORDER BY v.id""",
        (instrument_id,),
    ).fetchall()
    if not versions:
        _seed_version(db, instrument_id, "0.1.0")
    elif max(row["item_count"] for row in versions) < 51:
        existing = {row["version"] for row in versions}
        version = "0.2.0"
        counter = 2
        while version in existing:
            counter += 1
            version = f"0.{counter}.0"
        _seed_version(db, instrument_id, version)
    db.execute("INSERT OR IGNORE INTO system_configuration(key,value_json,updated_at) VALUES ('MIN_BENCHMARK_SAMPLE','10',?)", (timestamp,))
    db.execute("INSERT OR IGNORE INTO system_configuration(key,value_json,updated_at) VALUES ('GAP_THRESHOLD','15',?)", (timestamp,))
    db.execute("INSERT OR IGNORE INTO system_configuration(key,value_json,updated_at) VALUES ('PRIORITY_WEIGHTS',?,?)", (json.dumps({"gap": 0.45, "impact": 0.25, "dependency": 0.15, "effort": 0.10, "confidence": 0.05}), timestamp))
    demo_user = db.execute("SELECT id FROM users WHERE lower(email)=?", (config.DEMO_EMAIL,)).fetchone() if config.SEED_DEMO else None
    if demo_user and not db.execute("SELECT 1 FROM notifications WHERE user_id=? LIMIT 1", (demo_user["id"],)).fetchone():
        db.execute(
            "INSERT INTO notifications(user_id,type,title,body,target_url,created_at) VALUES (?,?,?,?,?,?)",
            (demo_user["id"], "WELCOME", "مرحبًا بك في نضج MCM", "أكمل ملف الشركة ثم ابدأ أول تقييم بحثي.", "#assessment", timestamp),
        )


def init_db() -> None:
    db = connect()
    try:
        db.executescript(SCHEMA)
        _migrate_legacy(db)
        _ensure_seed_data(db)
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (1,'full_platform_baseline',?)", (now(),))
        db.execute("PRAGMA optimize")
        db.commit()
    finally:
        db.close()


def get_config(db: sqlite3.Connection, key: str, default=None):
    row = db.execute("SELECT value_json FROM system_configuration WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value_json"])
    except (TypeError, json.JSONDecodeError):
        return row["value_json"]


def assessment_research_eligible(db: sqlite3.Connection, assessment_id: int) -> bool:
    """Require controller consent and consent from every real-data contributor."""
    assessment = db.execute(
        """SELECT a.id,a.created_by,a.data_origin,COALESCE(cp.research_consent,0) AS organization_consent
           FROM assessments a LEFT JOIN company_profiles cp ON cp.organization_id=a.organization_id
           WHERE a.id=?""",
        (assessment_id,),
    ).fetchone()
    if not assessment:
        return False
    if assessment["data_origin"] != "REAL":
        return True
    if not assessment["organization_consent"]:
        return False
    contributors = [row[0] for row in db.execute("SELECT DISTINCT participant_id FROM responses WHERE assessment_id=?", (assessment_id,))]
    if not contributors:
        return False
    for participant_id in contributors:
        if int(participant_id or 0) == 0:
            consent = db.execute(
                """SELECT accepted FROM consents
                   WHERE user_id=? AND participant_id IS NULL AND consent_type='RESEARCH_USE'
                   ORDER BY accepted_at DESC,id DESC LIMIT 1""",
                (assessment["created_by"],),
            ).fetchone()
        else:
            participant = db.execute("SELECT user_id FROM participants WHERE id=?", (participant_id,)).fetchone()
            if participant and participant["user_id"]:
                consent = db.execute(
                    """SELECT accepted FROM consents
                       WHERE user_id=? AND participant_id IS NULL AND consent_type='RESEARCH_USE'
                       ORDER BY accepted_at DESC,id DESC LIMIT 1""",
                    (participant["user_id"],),
                ).fetchone()
            else:
                consent = db.execute(
                    """SELECT accepted FROM consents
                       WHERE participant_id=? AND user_id IS NULL AND consent_type='RESEARCH_USE'
                       ORDER BY accepted_at DESC,id DESC LIMIT 1""",
                    (participant_id,),
                ).fetchone()
        if not consent or not consent["accepted"]:
            return False
    return True
