from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Any

from . import config
from .postgres import connect_postgres, postgres_schema, schema_table_names


try:
    from psycopg import IntegrityError as PostgresIntegrityError
except ImportError:  # SQLite-only local development does not need psycopg installed.
    PostgresIntegrityError = None


INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + (
    (PostgresIntegrityError,) if PostgresIntegrityError is not None else ()
)
REQUIRED_SCHEMA_VERSION = 7
# Schema versions this release can upgrade in place. Version 4 differs from 5
# only by additive columns and a stage-label revision, both of which are
# applied and verified by migrate_postgres(). Any other older version is still
# refused rather than silently marked complete.
SUPPORTED_UPGRADE_VERSIONS = frozenset({4, 5, 6})

CONSULTATION_STATUSES = (
    "NEW", "ASSIGNED", "CONTACTED", "QUALIFIED",
    "CONSULTATION_SCHEDULED", "CONVERTED", "CLOSED", "DO_NOT_CONTACT",
)
CONSULTATION_EVENTS = (
    "CREATED", "ASSIGNED", "CONTACT_ATTEMPTED", "CONTACTED", "QUALIFIED",
    "SCHEDULED", "CONVERTED", "CLOSED", "CONSENT_WITHDRAWN", "DELETION_REQUESTED",
)
CONSULTATION_TOPICS = (
    "STRATEGY_AND_GOVERNANCE", "STAKEHOLDER_COMMUNICATION", "INFORMATION_GOVERNANCE",
    "CUSTOMER_JOURNEY", "PROMISE_EXPERIENCE_ALIGNMENT", "MEASUREMENT_AND_LEARNING",
    "CAPABILITY_SUSTAINABILITY", "FULL_90_DAY_PLAN", "OTHER",
)
CONTACT_METHODS = ("PHONE", "EMAIL", "WHATSAPP", "VIDEO_MEETING")
# Stored with every lead so a later change to the wording can never be applied
# retroactively to a consent someone already gave.
CONTACT_CONSENT_VERSION = "CONTACT_CONSENT_1.0"
MARKETING_CONSENT_VERSION = "MARKETING_CONSENT_1.0"
PRIVACY_NOTICE_VERSION = "PRIVACY_NOTICE_1.0"

# Product lifecycle is an operational decision; scientific status is an
# evidentiary claim. They are deliberately separate so that publishing a
# version can never imply validation. Scientific status is never inferred or
# advanced automatically — only an authorised researcher or super administrator
# may change it, and every change is audited.
PRODUCT_STATUSES = ("DRAFT", "ACTIVE", "INACTIVE", "ARCHIVED")
SCIENTIFIC_STATUSES = ("EVIDENCE_INFORMED", "EXPERT_REVIEWED", "EMPIRICALLY_VALIDATED", "ARCHIVED")
# Backfill map from the pre-existing single `status` column.
_PRODUCT_STATUS_BACKFILL = {
    "DRAFT": "DRAFT",
    "EXPERT_REVIEW": "DRAFT",
    "PILOT": "ACTIVE",
    "PUBLISHED": "ACTIVE",
    "published": "ACTIVE",
    "VALIDATED": "ACTIVE",
    "ARCHIVED": "ARCHIVED",
}


def now() -> int:
    return int(time.time())


def connect(*, migration: bool = False):
    database_url = config.DATABASE_MIGRATION_URL if migration else config.DATABASE_URL
    if database_url:
        return connect_postgres(
            database_url,
            application_name="mcm-migration" if migration else "mcm-platform",
        )
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def select_for_update(db, sql: str, params=()):
    """Lock one selected row on PostgreSQL while preserving SQLite parity."""
    if getattr(db, "backend", "sqlite") == "postgresql":
        sql = f"{sql.rstrip().rstrip(';')} FOR UPDATE"
    return db.execute(sql, params).fetchone()


@contextmanager
def transaction():
    db = connect()
    try:
        if not config.DATABASE_URL:
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
  CHECK ((user_id IS NOT NULL AND participant_id IS NULL) OR (user_id IS NULL AND participant_id IS NOT NULL)),
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
  product_status TEXT NOT NULL DEFAULT 'DRAFT',
  scientific_status TEXT NOT NULL DEFAULT 'EVIDENCE_INFORMED',
  scientific_status_changed_at INTEGER,
  scientific_status_changed_by INTEGER,
  notes TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
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
  source_type TEXT,
  source_reference TEXT,
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
  scale_code TEXT,
  include_in_score INTEGER NOT NULL DEFAULT 1,
  score_group TEXT,
  source_type TEXT,
  source_reference TEXT,
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
  threshold_status TEXT NOT NULL DEFAULT 'PROVISIONAL_LABEL_ONLY',
  source_reference TEXT,
  level_order INTEGER NOT NULL,
  content_json TEXT,
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
CREATE TABLE IF NOT EXISTS assessment_context (
  assessment_id INTEGER PRIMARY KEY,
  sector TEXT NOT NULL,
  firm_size TEXT NOT NULL,
  employee_count INTEGER,
  firm_age_years INTEGER NOT NULL,
  business_model TEXT,
  region TEXT NOT NULL,
  social_platform_count INTEGER NOT NULL,
  social_team_size INTEGER,
  regulated INTEGER,
  respondent_role TEXT NOT NULL,
  leadership_support REAL,
  human_competencies REAL,
  technology_infrastructure REAL,
  data_readiness REAL,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
CREATE TABLE IF NOT EXISTS instrument_profile_fields (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  construct TEXT NOT NULL DEFAULT 'CONTEXT',
  label_ar TEXT NOT NULL,
  label_en TEXT,
  response_type TEXT NOT NULL,
  include_in_score INTEGER NOT NULL DEFAULT 0,
  source_reference TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE(version_id, code),
  FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
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
CREATE TABLE IF NOT EXISTS consultation_leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  organization_id INTEGER,
  participant_id INTEGER,
  participant_user_id INTEGER,
  full_name TEXT NOT NULL,
  organization_name TEXT,
  job_title TEXT,
  email TEXT NOT NULL,
  phone_e164 TEXT NOT NULL,
  preferred_contact_method TEXT,
  preferred_contact_time TEXT,
  consultation_topics TEXT NOT NULL DEFAULT '[]',
  notes TEXT,
  consent_to_contact INTEGER NOT NULL,
  contact_consent_version TEXT NOT NULL,
  contact_consent_at INTEGER NOT NULL,
  marketing_consent INTEGER NOT NULL DEFAULT 0,
  marketing_consent_at INTEGER,
  privacy_notice_version TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'ASSESSMENT_RESULTS',
  status TEXT NOT NULL DEFAULT 'NEW',
  assigned_consultant_id INTEGER,
  first_contacted_at INTEGER,
  scheduled_at INTEGER,
  closed_at INTEGER,
  closure_reason TEXT,
  idempotency_key TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  deleted_at INTEGER,
  UNIQUE(assessment_id, email, phone_e164),
  UNIQUE(idempotency_key),
  FOREIGN KEY(assessment_id) REFERENCES assessments(id),
  FOREIGN KEY(organization_id) REFERENCES organizations(id),
  FOREIGN KEY(participant_id) REFERENCES participants(id),
  FOREIGN KEY(participant_user_id) REFERENCES users(id),
  FOREIGN KEY(assigned_consultant_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS consultation_lead_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  consultation_lead_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  previous_status TEXT,
  new_status TEXT,
  note TEXT,
  actor_user_id INTEGER,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(consultation_lead_id) REFERENCES consultation_leads(id),
  FOREIGN KEY(actor_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_consultation_leads_assessment ON consultation_leads(assessment_id);
CREATE INDEX IF NOT EXISTS idx_consultation_leads_org ON consultation_leads(organization_id);
CREATE INDEX IF NOT EXISTS idx_consultation_leads_status ON consultation_leads(status, created_at);
CREATE INDEX IF NOT EXISTS idx_consultation_leads_consultant ON consultation_leads(assigned_consultant_id, status);
CREATE INDEX IF NOT EXISTS idx_consultation_leads_email ON consultation_leads(email);
CREATE INDEX IF NOT EXISTS idx_consultation_leads_phone ON consultation_leads(phone_e164);
CREATE INDEX IF NOT EXISTS idx_consultation_lead_events_lead ON consultation_lead_events(consultation_lead_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memberships_org ON memberships(organization_id, role);
CREATE INDEX IF NOT EXISTS idx_sessions_user_expiry ON sessions(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_assessments_org_status ON assessments(organization_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_assessment_context_demographics ON assessment_context(sector, firm_size, region);
CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_org_user ON participants(organization_id, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_org_email ON participants(organization_id, lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_consents_user_type_version ON consents(user_id, consent_type, consent_version) WHERE user_id IS NOT NULL AND participant_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_consents_participant_type_version ON consents(participant_id, consent_type, consent_version) WHERE participant_id IS NOT NULL AND user_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_responses_assessment ON responses(assessment_id, participant_id);
CREATE INDEX IF NOT EXISTS idx_dimension_scores_assessment ON dimension_scores(assessment_id, construct);
CREATE INDEX IF NOT EXISTS idx_score_runs_assessment ON score_runs(assessment_id, is_current, created_at);
CREATE INDEX IF NOT EXISTS idx_invitations_token_status ON invitations(token, status);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity, entity_id, created_at);
"""

POSTGRES_SCHEMA = postgres_schema(SCHEMA)
POSTGRES_TABLES = tuple(schema_table_names(POSTGRES_SCHEMA))

# Columns added after schema version 4 shipped. `CREATE TABLE IF NOT EXISTS`
# leaves an existing table untouched, so these run separately during migration.
POSTGRES_ADDITIVE_COLUMNS = (
    "ALTER TABLE maturity_levels ADD COLUMN IF NOT EXISTS content_json TEXT",
    "ALTER TABLE instrument_versions ADD COLUMN IF NOT EXISTS product_status TEXT NOT NULL DEFAULT 'DRAFT'",
    "ALTER TABLE instrument_versions ADD COLUMN IF NOT EXISTS scientific_status TEXT NOT NULL DEFAULT 'EVIDENCE_INFORMED'",
    "ALTER TABLE instrument_versions ADD COLUMN IF NOT EXISTS scientific_status_changed_at BIGINT",
    "ALTER TABLE instrument_versions ADD COLUMN IF NOT EXISTS scientific_status_changed_by BIGINT",
)


def _migrate_assessment_context(db: sqlite3.Connection) -> None:
    """Expand the context snapshot and make legacy aggregate enablers nullable.

    SQLite cannot remove a NOT NULL constraint with ALTER TABLE. Rebuilding this
    small child table is therefore required so the v0.4 questionnaire can store
    the twelve scientific enabler items without manufacturing four aggregate
    values at assessment creation time.
    """
    table_info = db.execute("PRAGMA table_info(assessment_context)").fetchall()
    if not table_info:
        return
    existing = {row["name"]: row for row in table_info}
    desired_columns = (
        "assessment_id", "sector", "firm_size", "employee_count", "firm_age_years",
        "business_model", "region", "social_platform_count", "social_team_size",
        "regulated", "respondent_role", "leadership_support", "human_competencies",
        "technology_infrastructure", "data_readiness", "created_at",
    )
    legacy_enablers = (
        "leadership_support", "human_competencies",
        "technology_infrastructure", "data_readiness",
    )
    requires_rebuild = any(column not in existing for column in desired_columns) or any(
        bool(existing[column]["notnull"])
        for column in legacy_enablers
        if column in existing
    )
    if not requires_rebuild:
        return

    db.execute("DROP TABLE IF EXISTS assessment_context_migration_v3")
    db.execute(
        """CREATE TABLE assessment_context_migration_v3 (
             assessment_id INTEGER PRIMARY KEY,
             sector TEXT NOT NULL,
             firm_size TEXT NOT NULL,
             employee_count INTEGER,
             firm_age_years INTEGER NOT NULL,
             business_model TEXT,
             region TEXT NOT NULL,
             social_platform_count INTEGER NOT NULL,
             social_team_size INTEGER,
             regulated INTEGER,
             respondent_role TEXT NOT NULL,
             leadership_support REAL,
             human_competencies REAL,
             technology_infrastructure REAL,
             data_readiness REAL,
             created_at INTEGER NOT NULL,
             FOREIGN KEY(assessment_id) REFERENCES assessments(id)
           )"""
    )
    copied_columns = [column for column in desired_columns if column in existing]
    column_sql = ",".join(copied_columns)
    db.execute(
        f"INSERT INTO assessment_context_migration_v3({column_sql}) "
        f"SELECT {column_sql} FROM assessment_context"
    )
    db.execute("DROP TABLE assessment_context")
    db.execute("ALTER TABLE assessment_context_migration_v3 RENAME TO assessment_context")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_assessment_context_demographics "
        "ON assessment_context(sector, firm_size, region)"
    )


def _migrate_dimension_version_constraint(db: sqlite3.Connection) -> None:
    """Replace the legacy global dimension-code constraint with a versioned one."""
    columns = _columns(db, "dimensions")
    if not columns:
        return
    unique_indexes = db.execute("PRAGMA index_list(dimensions)").fetchall()
    has_global_code_constraint = False
    for index in unique_indexes:
        if not index["unique"]:
            continue
        indexed = [row["name"] for row in db.execute(f"PRAGMA index_info('{index['name']}')")]
        if indexed == ["code"]:
            has_global_code_constraint = True
            break
    if not has_global_code_constraint:
        return
    if db.execute("SELECT COUNT(*) FROM dimensions WHERE version_id IS NULL").fetchone()[0]:
        db.execute("UPDATE dimensions SET version_id=1 WHERE version_id IS NULL")
    db.execute("DROP TABLE IF EXISTS dimensions_migration_v3")
    db.execute(
        """CREATE TABLE dimensions_migration_v3 (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             version_id INTEGER NOT NULL,
             code TEXT NOT NULL,
             construct TEXT NOT NULL,
             name TEXT NOT NULL,
             name_en TEXT,
             weight REAL NOT NULL DEFAULT 1,
             source_type TEXT,
             source_reference TEXT,
             sort_order INTEGER NOT NULL DEFAULT 0,
             UNIQUE(version_id, code),
             FOREIGN KEY(version_id) REFERENCES instrument_versions(id)
           )"""
    )
    db.execute(
        """INSERT INTO dimensions_migration_v3(
             id,version_id,code,construct,name,name_en,weight,source_type,source_reference,sort_order
           )
           SELECT id,version_id,code,construct,name,name_en,weight,source_type,source_reference,sort_order
           FROM dimensions"""
    )
    db.execute("DROP TABLE dimensions")
    db.execute("ALTER TABLE dimensions_migration_v3 RENAME TO dimensions")


def _migrate_legacy(db: sqlite3.Connection) -> None:
    _migrate_assessment_context(db)
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
        "instrument_versions": {
            "notes": "TEXT", "metadata_json": "TEXT NOT NULL DEFAULT '{}'", "created_by": "INTEGER",
            "created_at": "INTEGER NOT NULL DEFAULT 0", "published_at": "INTEGER", "archived_at": "INTEGER",
            "product_status": "TEXT NOT NULL DEFAULT 'DRAFT'",
            "scientific_status": "TEXT NOT NULL DEFAULT 'EVIDENCE_INFORMED'",
            "scientific_status_changed_at": "INTEGER", "scientific_status_changed_by": "INTEGER",
        },
        "dimensions": {
            "version_id": "INTEGER", "name_en": "TEXT", "weight": "REAL NOT NULL DEFAULT 1",
            "source_type": "TEXT", "source_reference": "TEXT", "sort_order": "INTEGER NOT NULL DEFAULT 0",
        },
        "items": {
            "prompt_en": "TEXT", "source": "TEXT", "lifecycle_status": "TEXT NOT NULL DEFAULT 'PILOT'",
            "reverse_coded": "INTEGER NOT NULL DEFAULT 0", "required": "INTEGER NOT NULL DEFAULT 1",
            "weight": "REAL NOT NULL DEFAULT 1", "response_type": "TEXT NOT NULL DEFAULT 'LIKERT'",
            "scale_code": "TEXT", "include_in_score": "INTEGER NOT NULL DEFAULT 1", "score_group": "TEXT",
            "source_type": "TEXT", "source_reference": "TEXT",
            "min_value": "REAL DEFAULT 1", "max_value": "REAL DEFAULT 5", "sort_order": "INTEGER NOT NULL DEFAULT 0",
        },
        "maturity_levels": {
            "threshold_status": "TEXT NOT NULL DEFAULT 'PROVISIONAL_LABEL_ONLY'", "source_reference": "TEXT",
            "content_json": "TEXT",
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
    _migrate_dimension_version_constraint(db)


def audit(db: sqlite3.Connection, user_id: int | None, action: str, entity: str, entity_id: int | None = None, metadata: dict | None = None) -> None:
    db.execute(
        "INSERT INTO audit_logs(user_id,action,entity,entity_id,metadata_json,created_at) VALUES (?,?,?,?,?,?)",
        (user_id, action, entity, entity_id, json.dumps(metadata or {}, ensure_ascii=False), now()),
    )


def _seed_version(db: sqlite3.Connection, instrument_id: int, version: str) -> int:
    timestamp = now()
    metadata = dict(config.INSTRUMENT_METADATA)
    metadata["source_instrument_version"] = metadata.get("version")
    metadata["platform_version"] = version
    cur = db.execute(
        """INSERT INTO instrument_versions(
             instrument_id,version,status,notes,metadata_json,created_at,published_at
           ) VALUES (?,?,?,?,?,?,?)""",
        (
            instrument_id,
            version,
            "PILOT",
            "Platform v0.4 seeded from scientific instrument v0.2; expert-review and provisionally unvalidated.",
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            timestamp,
            timestamp,
        ),
    )
    version_id = int(cur.lastrowid)

    for dimension in config.INSTRUMENT_DIMENSIONS:
        db.execute(
            """INSERT INTO dimensions(
                 version_id,code,construct,name,name_en,weight,source_type,source_reference,sort_order
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                version_id,
                dimension["code"],
                dimension["construct"],
                dimension["name_ar"],
                dimension.get("name_en"),
                float(dimension.get("weight", 1)),
                dimension.get("source_type"),
                dimension.get("source_reference"),
                int(dimension.get("display_order", 0)),
            ),
        )

    scale_ranges: dict[str, tuple[float, float]] = {}
    for scale_code, values in config.SCALE_DEFINITIONS.items():
        numeric_values = [float(row["value"]) for row in values]
        scale_ranges[scale_code] = (min(numeric_values), max(numeric_values))
        response_types = {
            str(item.get("response_type") or "LIKERT")
            for item in config.INSTRUMENT_ITEMS
            if item.get("scale_code") == scale_code
        }
        response_type = sorted(response_types)[0] if len(response_types) == 1 else "LIKERT"
        scale_id = db.execute(
            "INSERT INTO scales(version_id,code,response_type,min_value,max_value) VALUES (?,?,?,?,?)",
            (version_id, scale_code, response_type, *scale_ranges[scale_code]),
        ).lastrowid
        for scale_value in values:
            db.execute(
                "INSERT INTO scale_values(scale_id,value,label_ar,label_en,missing_type) VALUES (?,?,?,?,NULL)",
                (
                    scale_id,
                    float(scale_value["value"]),
                    scale_value.get("label_ar"),
                    scale_value.get("label_en"),
                ),
            )
        if str(metadata.get("allow_not_applicable", "NO")).upper() == "YES":
            db.execute(
                "INSERT INTO scale_values(scale_id,value,label_ar,label_en,missing_type) VALUES (?,NULL,?,?,?)",
                (scale_id, "لا ينطبق", "Not applicable", metadata.get("not_applicable_code", "NOT_APPLICABLE")),
            )
        if str(metadata.get("allow_dont_know", "NO")).upper() == "YES":
            db.execute(
                "INSERT INTO scale_values(scale_id,value,label_ar,label_en,missing_type) VALUES (?,NULL,?,?,?)",
                (scale_id, "لا أعرف", "Don't know", metadata.get("dont_know_code", "DONT_KNOW")),
            )

    for order, field in enumerate(config.INSTRUMENT_PROFILE_FIELDS, 1):
        db.execute(
            """INSERT INTO instrument_profile_fields(
                 version_id,code,construct,label_ar,label_en,response_type,
                 include_in_score,source_reference,sort_order
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                version_id,
                field["code"],
                field.get("construct", "CONTEXT"),
                field["label_ar"],
                field.get("label_en"),
                field["response_type"],
                int(bool(field.get("include_in_score", False))),
                field.get("source_reference"),
                order,
            ),
        )

    for item in config.INSTRUMENT_ITEMS:
        scale_code = item["scale_code"]
        minimum, maximum = scale_ranges[scale_code]
        source_type = item.get("source_type")
        source_reference = item.get("source_reference")
        source = ":".join(filter(None, (source_type, source_reference))) or None
        db.execute(
            """INSERT INTO items(
                 version_id,code,construct,dimension_code,prompt_ar,prompt_en,source,lifecycle_status,
                 reverse_coded,required,weight,response_type,scale_code,include_in_score,score_group,
                 source_type,source_reference,min_value,max_value,sort_order
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                version_id,
                item["code"],
                item["construct"],
                item["dimension_code"],
                item["prompt_ar"],
                item.get("prompt_en"),
                source,
                item.get("item_status", "EXPERT_REVIEW"),
                int(bool(item.get("reverse_coded", False))),
                int(bool(item.get("required", True))),
                float(item.get("weight", 1)),
                item.get("response_type", "LIKERT"),
                scale_code,
                int(bool(item.get("include_in_score", True))),
                item.get("score_group"),
                source_type,
                source_reference,
                minimum,
                maximum,
                int(item.get("display_order", 0)),
            ),
        )

    for level in config.INSTRUMENT_MATURITY_LEVELS:
        db.execute(
            """INSERT INTO maturity_levels(
                 version_id,code,label_ar,label_en,min_score,max_score,
                 threshold_status,source_reference,level_order,content_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                version_id,
                level["code"],
                level["label_ar"],
                level["label_en"],
                float(level["min_score"]),
                float(level["max_score"]),
                level.get("threshold_status", "PROVISIONAL_LABEL_ONLY"),
                level.get("source_reference"),
                int(level["level_order"]),
                json.dumps(level.get("content_ar") or {}, ensure_ascii=False, sort_keys=True),
            ),
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


def _ensure_seed_data(db: sqlite3.Connection, *, reset_admin_password: bool = False) -> None:
    timestamp = now()
    organization = db.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()
    if not organization:
        organization_id = db.execute(
            "INSERT INTO organizations(name,locale,sector,size,country,region,data_origin,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (config.BOOTSTRAP_ORG_NAME, "ar", None, None, "Saudi Arabia", "Riyadh", "TEST", timestamp),
        ).lastrowid
    else:
        organization_id = organization["id"]
    db.execute(
        "INSERT OR IGNORE INTO company_profiles(organization_id,website,business_model,employee_count,communication_team_size,completion,updated_at) VALUES (?,?,?,?,?,?,?)",
        (organization_id, None, None, None, None, 0, timestamp),
    )
    for obsolete in db.execute("SELECT id FROM users WHERE lower(email)='sara@example.com'").fetchall():
        obsolete_id = int(obsolete["id"])
        db.execute("UPDATE participants SET user_id=NULL WHERE user_id=?", (obsolete_id,))
        db.execute("UPDATE audit_logs SET user_id=NULL WHERE user_id=?", (obsolete_id,))
        for table in ("sessions", "password_reset_tokens", "memberships", "notifications", "user_settings"):
            db.execute(f"DELETE FROM {table} WHERE user_id=?", (obsolete_id,))
        db.execute("DELETE FROM consents WHERE user_id=?", (obsolete_id,))
        db.execute("DELETE FROM users WHERE id=?", (obsolete_id,))

    row = db.execute("SELECT id,password_hash FROM users WHERE lower(email)=?", (config.PLATFORM_ADMIN_EMAIL,)).fetchone()
    if row:
        user_id = int(row["id"])
        if reset_admin_password:
            db.execute(
                "UPDATE users SET name=?,password_hash=?,preferred_language='ar',verified=1,is_active=1 WHERE id=?",
                (config.PLATFORM_ADMIN_NAME, password_hash(config.PLATFORM_ADMIN_PASSWORD), user_id),
            )
        else:
            db.execute(
                "UPDATE users SET name=?,preferred_language='ar',verified=1,is_active=1 WHERE id=?",
                (config.PLATFORM_ADMIN_NAME, user_id),
            )
    else:
        user_id = db.execute(
            "INSERT INTO users(email,name,password_hash,preferred_language,verified,is_active,created_at) VALUES (?,?,?,?,?,?,?)",
            (config.PLATFORM_ADMIN_EMAIL, config.PLATFORM_ADMIN_NAME, password_hash(config.PLATFORM_ADMIN_PASSWORD), "ar", 1, 1, timestamp),
        ).lastrowid
    db.execute(
        "INSERT INTO memberships(user_id,organization_id,role,status) VALUES (?,?,?,?) ON CONFLICT(user_id,organization_id) DO UPDATE SET role='SUPER_ADMIN',status='ACTIVE'",
        (user_id, organization_id, "SUPER_ADMIN", "ACTIVE"),
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
    existing = {row["version"] for row in versions}
    if "0.4.0" not in existing:
        _seed_version(db, instrument_id, "0.4.0")
    current_version = db.execute(
        "SELECT id FROM instrument_versions WHERE instrument_id=? AND version='0.4.0' ORDER BY id DESC LIMIT 1",
        (instrument_id,),
    ).fetchone()
    if current_version:
        for level in config.INSTRUMENT_MATURITY_LEVELS:
            # A stage rename updates the row in place so that every historical
            # assessment keeps its maturity_level_id and its classification.
            # Scores are never rewritten; only the display label moves. The
            # previous wording is preserved in the audit trail.
            previous = db.execute(
                "SELECT label_ar,label_en FROM maturity_levels WHERE version_id=? AND code=?",
                (current_version["id"], level["code"]),
            ).fetchone()
            db.execute(
                """UPDATE maturity_levels SET label_ar=?,label_en=?,min_score=?,max_score=?,threshold_status=?,source_reference=?,level_order=?,content_json=?
                   WHERE version_id=? AND code=?""",
                (
                    level["label_ar"], level["label_en"], level["min_score"], level["max_score"],
                    level["threshold_status"], level["source_reference"], level["level_order"],
                    json.dumps(level.get("content_ar") or {}, ensure_ascii=False, sort_keys=True),
                    current_version["id"], level["code"],
                ),
            )
            if previous and previous["label_ar"] != level["label_ar"]:
                audit(
                    db,
                    None,
                    "MATURITY_LABEL_RENAMED",
                    "maturity_levels",
                    current_version["id"],
                    {
                        "code": level["code"],
                        "previous_label_ar": previous["label_ar"],
                        "new_label_ar": level["label_ar"],
                        "label_en": level["label_en"],
                        "scores_rewritten": False,
                    },
                )
    _backfill_version_statuses(db)
    db.execute("INSERT OR IGNORE INTO system_configuration(key,value_json,updated_at) VALUES ('MIN_BENCHMARK_SAMPLE','10',?)", (timestamp,))
    db.execute("INSERT OR IGNORE INTO system_configuration(key,value_json,updated_at) VALUES ('GAP_THRESHOLD','15',?)", (timestamp,))
    db.execute("INSERT OR IGNORE INTO system_configuration(key,value_json,updated_at) VALUES ('PRIORITY_WEIGHTS',?,?)", (json.dumps({"gap": 0.45, "impact": 0.25, "dependency": 0.15, "effort": 0.10, "confidence": 0.05}), timestamp))
    if not db.execute("SELECT 1 FROM notifications WHERE user_id=? LIMIT 1", (user_id,)).fetchone():
        db.execute(
            "INSERT INTO notifications(user_id,type,title,body,target_url,created_at) VALUES (?,?,?,?,?,?)",
            (user_id, "WELCOME", "مرحبًا بك في مقياس النضج الاتصالي التسويقي", "يمكن للمشاركين البدء مباشرة، ويمكنك متابعة الحالات وتصدير بيانات SPSS.", "#research", timestamp),
        )


class PhoneNumberError(ValueError):
    """Raised when a supplied phone number cannot be stored in E.164 form."""


def normalize_phone_e164(raw: str, default_country_code: str = "966") -> str:
    """Return a single canonical E.164 string, or refuse the input.

    One number must never be stored in two shapes, so every accepted value is
    reduced to `+` followed by digits. Local `0` trunk prefixes and `00`
    international prefixes are resolved against the configured default country
    rather than guessed per call site.
    """
    text = str(raw or "").strip()
    if not text:
        raise PhoneNumberError("phone_required")
    # Arabic-Indic digits are common in this interface; fold them to ASCII
    # before parsing so an Arabic keyboard entry is not silently rejected.
    folded = "".join(
        str(ord(char) - 0x0660) if "٠" <= char <= "٩"
        else str(ord(char) - 0x06F0) if "۰" <= char <= "۹"
        else char
        for char in text
    )
    explicit_plus = folded.startswith("+")
    digits = re.sub(r"\D", "", folded)
    if not digits:
        raise PhoneNumberError("phone_invalid")
    if not explicit_plus:
        if digits.startswith("00"):
            digits = digits[2:]
        elif digits.startswith("0"):
            digits = default_country_code + digits.lstrip("0")
        elif not digits.startswith(default_country_code):
            digits = default_country_code + digits
    # E.164 allows at most 15 digits; a country code is at least one.
    if not 8 <= len(digits) <= 15:
        raise PhoneNumberError("phone_invalid")
    return "+" + digits


def _backfill_version_statuses(db: sqlite3.Connection) -> None:
    """Derive product status from the operational lifecycle, once, per version.

    Scientific status is deliberately *not* derived. Every version starts at
    `EVIDENCE_INFORMED`, the weakest claim, and only an authorised researcher or
    super administrator can advance it through the API. Publishing a version,
    archiving it, or running this migration can never assert validation.
    """
    rows = db.execute(
        "SELECT id,status,product_status,archived_at FROM instrument_versions"
    ).fetchall()
    for row in rows:
        # Only fill a column still holding its default, so an explicit
        # operational decision recorded later is never overwritten by a reseed.
        if row["product_status"] not in (None, "", "DRAFT"):
            continue
        target = _PRODUCT_STATUS_BACKFILL.get(row["status"], "DRAFT")
        if row["archived_at"]:
            target = "ARCHIVED"
        if target != row["product_status"]:
            db.execute(
                "UPDATE instrument_versions SET product_status=? WHERE id=?",
                (target, row["id"]),
            )


def _sqlite_table_exists(db: sqlite3.Connection, table: str) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _deduplicate_legacy_consents(db: sqlite3.Connection) -> None:
    if not _sqlite_table_exists(db, "consents"):
        return
    db.execute(
        """DELETE FROM consents
           WHERE user_id IS NOT NULL AND participant_id IS NULL
             AND id NOT IN (
               SELECT MAX(id) FROM consents
               WHERE user_id IS NOT NULL AND participant_id IS NULL
               GROUP BY user_id,consent_type,consent_version
             )"""
    )
    db.execute(
        """DELETE FROM consents
           WHERE participant_id IS NOT NULL AND user_id IS NULL
             AND id NOT IN (
               SELECT MAX(id) FROM consents
               WHERE participant_id IS NOT NULL AND user_id IS NULL
               GROUP BY participant_id,consent_type,consent_version
             )"""
    )


def init_db() -> None:
    if config.DATABASE_URL:
        verify_postgres()
        return
    db = connect()
    try:
        previous_version = 0
        if _sqlite_table_exists(db, "schema_migrations"):
            previous_version = int(
                db.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0]
            )
        _deduplicate_legacy_consents(db)
        db.executescript(SCHEMA)
        _migrate_legacy(db)
        _ensure_seed_data(
            db,
            reset_admin_password=(
                previous_version < REQUIRED_SCHEMA_VERSION
                and config.PLATFORM_ADMIN_PASSWORD_CONFIGURED
            ),
        )
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (1,'full_platform_baseline',?)", (now(),))
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (2,'direct_participant_context_and_revised_model',?)", (now(),))
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (3,'scientific_instrument_v02_platform_v040',?)", (now(),))
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (4,'supabase_postgresql_adapter_and_data_integrity',?)", (now(),))
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (5,'maturity_stage_labels_and_public_stage_content',?)", (now(),))
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (6,'separate_product_and_scientific_status',?)", (now(),))
        db.execute("INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (7,'consultation_leads_and_consent_versioning',?)", (now(),))
        db.execute("PRAGMA optimize")
        db.commit()
    finally:
        db.close()


def migrate_postgres() -> dict[str, int]:
    """Apply the durable schema once, seed it, and deny Supabase Data API roles."""
    if not config.DATABASE_MIGRATION_URL:
        raise RuntimeError("MCM_DATABASE_MIGRATION_URL or MCM_DATABASE_URL is required")
    db = connect(migration=True)
    try:
        db.execute("SELECT pg_advisory_xact_lock(?)", (742_026_082_804,))
        migration_table = db.execute("SELECT to_regclass('public.schema_migrations')").fetchone()[0]
        previous_version = 0
        if migration_table:
            previous_version = int(
                db.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0]
            )
        if previous_version > REQUIRED_SCHEMA_VERSION:
            raise RuntimeError(
                "The PostgreSQL schema is newer than this application release."
            )
        existing_tables = {
            row[0]
            for row in db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
        }
        existing_application_tables = existing_tables.intersection(POSTGRES_TABLES)
        if (
            existing_application_tables
            and previous_version < REQUIRED_SCHEMA_VERSION
            and previous_version not in SUPPORTED_UPGRADE_VERSIONS
        ):
            raise RuntimeError(
                "An unsupported PostgreSQL application schema version "
                f"({previous_version}) was detected; an explicit upgrade "
                "migration is required before this release can be applied."
            )
        db.executescript(POSTGRES_SCHEMA)
        # CREATE TABLE IF NOT EXISTS cannot widen a table that already exists,
        # so additive columns introduced after a shipped schema version are
        # applied explicitly here. Each statement must stay idempotent.
        for statement in POSTGRES_ADDITIVE_COLUMNS:
            db.execute(statement)
        created_tables = {
            row[0]
            for row in db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
        }
        missing_tables = sorted(set(POSTGRES_TABLES).difference(created_tables))
        if missing_tables:
            raise RuntimeError(
                "PostgreSQL schema creation is incomplete: " + ",".join(missing_tables)
            )
        _ensure_seed_data(
            db,
            reset_admin_password=(
                previous_version < REQUIRED_SCHEMA_VERSION
                and config.PLATFORM_ADMIN_PASSWORD_CONFIGURED
            ),
        )
        seeded_items = db.execute(
            """SELECT COUNT(i.id)
               FROM instrument_versions v JOIN items i ON i.version_id=v.id
               WHERE v.version='0.4.0' AND v.status='PILOT'"""
        ).fetchone()[0]
        if int(seeded_items or 0) != 67:
            raise RuntimeError("PostgreSQL scientific instrument seed is incomplete")
        migration_rows = (
            (1, "full_platform_baseline"),
            (2, "direct_participant_context_and_revised_model"),
            (3, "scientific_instrument_v02_platform_v040"),
            (4, "supabase_postgresql_adapter_and_data_integrity"),
            (5, "maturity_stage_labels_and_public_stage_content"),
            (6, "separate_product_and_scientific_status"),
            (7, "consultation_leads_and_consent_versioning"),
        )
        for version, name in migration_rows:
            db.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (?,?,?) ON CONFLICT(version) DO UPDATE SET name=excluded.name,applied_at=excluded.applied_at",
                (version, name, now()),
            )
        for table in POSTGRES_TABLES:
            db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        exposed_roles = {
            row[0]
            for row in db.execute(
                "SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')"
            )
        }
        if exposed_roles:
            roles = ",".join(sorted(exposed_roles))
            db.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {roles}")
            db.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {roles}")
            db.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {roles}")
            db.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {roles}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"schema_version": REQUIRED_SCHEMA_VERSION, "table_count": len(POSTGRES_TABLES)}


def verify_postgres() -> None:
    """Fast startup check; DDL is deliberately not run in Vercel cold starts."""
    db = connect()
    try:
        version = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        if not version or int(version[0] or 0) < REQUIRED_SCHEMA_VERSION:
            raise RuntimeError("PostgreSQL schema migration 4 has not been applied")
        instrument = db.execute(
            """SELECT COUNT(i.id) AS item_count
               FROM instrument_versions v JOIN items i ON i.version_id=v.id
               WHERE v.version='0.4.0' AND v.status='PILOT'"""
        ).fetchone()
        if not instrument or int(instrument[0] or 0) != 67:
            raise RuntimeError("PostgreSQL scientific instrument seed is incomplete")
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
