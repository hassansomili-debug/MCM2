-- Target PostgreSQL 15+ schema for the durable-storage adapter.
-- The current application SQL is SQLite-specific; do not apply this file alone and
-- point the existing process at PostgreSQL without the adapter/parity tests.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE organizations (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL, locale text NOT NULL DEFAULT 'ar', sector text, subsector text,
  size text, country text, region text,
  data_origin text NOT NULL CHECK (data_origin IN ('REAL','SYNTHETIC','DEMO','TEST')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE users (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email citext UNIQUE NOT NULL, name text NOT NULL, password_hash text NOT NULL,
  job_title text, phone text, preferred_language text NOT NULL DEFAULT 'ar',
  verified boolean NOT NULL DEFAULT false, is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE memberships (
  user_id bigint NOT NULL REFERENCES users(id), organization_id bigint NOT NULL REFERENCES organizations(id),
  role text NOT NULL CHECK (role IN ('COMPANY_RESPONDENT','COMPANY_ADMIN','CONSULTANT','RESEARCHER','SUPER_ADMIN')),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED')),
  PRIMARY KEY (user_id,organization_id)
);
CREATE TABLE sessions (
  token_hash text PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id), active_org_id bigint REFERENCES organizations(id),
  expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE password_reset_tokens (
  token_hash text PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id), expires_at timestamptz NOT NULL, used_at timestamptz
);
CREATE TABLE company_profiles (
  organization_id bigint PRIMARY KEY REFERENCES organizations(id), website text, business_model text,
  employee_count text, annual_revenue_band text, communication_team_size text,
  channels_json jsonb NOT NULL DEFAULT '[]', crm_system text, analytics_system text,
  research_consent boolean NOT NULL DEFAULT false, completion smallint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE participants (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, research_id text UNIQUE NOT NULL,
  organization_id bigint NOT NULL REFERENCES organizations(id), user_id bigint REFERENCES users(id),
  full_name text, email text, job_title text, department text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE consents (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, user_id bigint REFERENCES users(id), participant_id bigint REFERENCES participants(id),
  consent_type text NOT NULL CHECK (consent_type IN ('SERVICE_DIAGNOSTIC','RESEARCH_USE')),
  consent_version text NOT NULL, accepted boolean NOT NULL, accepted_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((user_id IS NULL) <> (participant_id IS NULL))
);
CREATE UNIQUE INDEX consents_user_unique ON consents(user_id,consent_type,consent_version) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX consents_participant_unique ON consents(participant_id,consent_type,consent_version) WHERE participant_id IS NOT NULL;

CREATE TABLE instruments (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, code text UNIQUE NOT NULL, name text NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE instrument_versions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, instrument_id bigint NOT NULL REFERENCES instruments(id),
  version text NOT NULL, status text NOT NULL CHECK (status IN ('DRAFT','EXPERT_REVIEW','PILOT','VALIDATED','ARCHIVED')),
  notes text, created_by bigint REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz, archived_at timestamptz, UNIQUE(instrument_id,version)
);
CREATE TABLE dimensions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version_id bigint NOT NULL REFERENCES instrument_versions(id),
  code text NOT NULL, construct text NOT NULL CHECK (construct IN ('MCM','SMCE','ENABLER','OUTCOME')),
  name_ar text NOT NULL, name_en text, weight numeric NOT NULL DEFAULT 1 CHECK (weight > 0), sort_order integer NOT NULL,
  UNIQUE(version_id,code)
);
CREATE TABLE scales (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version_id bigint NOT NULL REFERENCES instrument_versions(id),
  code text NOT NULL, response_type text NOT NULL, min_value numeric, max_value numeric, UNIQUE(version_id,code)
);
CREATE TABLE scale_values (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, scale_id bigint NOT NULL REFERENCES scales(id),
  value numeric, label_ar text, label_en text, missing_type text
);
CREATE TABLE items (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version_id bigint NOT NULL REFERENCES instrument_versions(id),
  code text NOT NULL, construct text NOT NULL, dimension_code text NOT NULL, prompt_ar text NOT NULL, prompt_en text,
  source text, lifecycle_status text NOT NULL, reverse_coded boolean NOT NULL DEFAULT false,
  required boolean NOT NULL DEFAULT true, weight numeric NOT NULL DEFAULT 1 CHECK (weight > 0),
  response_type text NOT NULL, min_value numeric, max_value numeric, sort_order integer NOT NULL,
  UNIQUE(version_id,code)
);
CREATE TABLE maturity_levels (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version_id bigint NOT NULL REFERENCES instrument_versions(id),
  code text NOT NULL, label_ar text NOT NULL, label_en text NOT NULL,
  min_score numeric NOT NULL, max_score numeric NOT NULL, level_order integer NOT NULL, UNIQUE(version_id,code)
);

CREATE TABLE assessments (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, organization_id bigint NOT NULL REFERENCES organizations(id),
  version_id bigint NOT NULL REFERENCES instrument_versions(id), created_by bigint NOT NULL REFERENCES users(id),
  assessment_type text NOT NULL, status text NOT NULL CHECK (status IN ('DRAFT','IN_PROGRESS','COMPLETED')),
  data_origin text NOT NULL CHECK (data_origin IN ('REAL','SYNTHETIC','DEMO','TEST')),
  parent_assessment_id bigint REFERENCES assessments(id), created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(), submitted_at timestamptz, completed_at timestamptz
);
CREATE TABLE assessment_participants (
  assessment_id bigint NOT NULL REFERENCES assessments(id), participant_id bigint NOT NULL REFERENCES participants(id),
  assessment_role text NOT NULL, status text NOT NULL, PRIMARY KEY(assessment_id,participant_id)
);
CREATE TABLE responses (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, assessment_id bigint NOT NULL REFERENCES assessments(id),
  participant_id bigint NOT NULL REFERENCES participants(id), item_id bigint NOT NULL REFERENCES items(id),
  numeric_value numeric, text_value text, missing_type text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(assessment_id,participant_id,item_id)
);
CREATE TABLE score_runs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, assessment_id bigint NOT NULL REFERENCES assessments(id),
  run_number integer NOT NULL, instrument_version_id bigint NOT NULL REFERENCES instrument_versions(id),
  scoring_version text NOT NULL, configuration_json jsonb NOT NULL, input_hash text NOT NULL, output_hash text,
  is_current boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(assessment_id,run_number)
);
CREATE TABLE response_item_scores (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, score_run_id bigint NOT NULL REFERENCES score_runs(id),
  item_id bigint NOT NULL REFERENCES items(id), raw_value numeric, effective_value numeric,
  normalized_score numeric, reverse_coded boolean NOT NULL, item_weight numeric NOT NULL
);
CREATE TABLE dimension_scores (
  assessment_id bigint NOT NULL REFERENCES assessments(id), dimension_code text NOT NULL, construct text NOT NULL,
  score numeric NOT NULL, answered_count integer NOT NULL, eligible_count integer NOT NULL,
  method_version text NOT NULL, calculated_at timestamptz NOT NULL, PRIMARY KEY(assessment_id,dimension_code)
);
CREATE TABLE assessment_scores (
  assessment_id bigint NOT NULL REFERENCES assessments(id), construct text NOT NULL,
  total_score numeric NOT NULL, maturity_level_id bigint REFERENCES maturity_levels(id), answered_count integer NOT NULL,
  method_version text NOT NULL, calculated_at timestamptz NOT NULL, PRIMARY KEY(assessment_id,construct)
);

CREATE TABLE diagnostic_rules (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version_id bigint NOT NULL REFERENCES instrument_versions(id),
  code text NOT NULL, name_ar text NOT NULL, dimensions text NOT NULL, operator text NOT NULL,
  threshold numeric NOT NULL, severity text NOT NULL, confidence numeric NOT NULL, active boolean NOT NULL DEFAULT true,
  UNIQUE(version_id,code)
);
CREATE TABLE diagnostic_results (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, assessment_id bigint NOT NULL REFERENCES assessments(id),
  rule_id bigint NOT NULL REFERENCES diagnostic_rules(id), evidence_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(assessment_id,rule_id)
);
CREATE TABLE recommendations (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version_id bigint NOT NULL REFERENCES instrument_versions(id),
  dimension_code text NOT NULL, problem text NOT NULL, action text NOT NULL, why_it_matters text,
  implementation_guidance text, suggested_owner text, expected_impact text NOT NULL, effort text NOT NULL,
  time_horizon text NOT NULL, kpi text, evidence_source text, active boolean NOT NULL DEFAULT true,
  UNIQUE(version_id,dimension_code)
);
CREATE TABLE roadmap_items (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, assessment_id bigint NOT NULL REFERENCES assessments(id),
  recommendation_id bigint REFERENCES recommendations(id), horizon text NOT NULL, title text NOT NULL,
  description text NOT NULL, owner text, status text NOT NULL, target_date date, impact text, effort text, kpi text,
  sort_order integer NOT NULL
);

CREATE TABLE reports (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, assessment_id bigint NOT NULL REFERENCES assessments(id),
  report_type text NOT NULL, status text NOT NULL, created_by bigint NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(), payload bytea, content_type text, filename text, sha256 text
);
CREATE TABLE research_exports (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, actor_user_id bigint NOT NULL REFERENCES users(id),
  format text NOT NULL, data_origin text NOT NULL, filters_json jsonb NOT NULL, status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), payload bytea, content_type text, filename text, sha256 text
);
CREATE TABLE notifications (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id), type text NOT NULL,
  title text NOT NULL, body text NOT NULL, target_url text, read_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit_logs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, user_id bigint REFERENCES users(id), action text NOT NULL,
  entity text NOT NULL, entity_id bigint, metadata_json jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE system_configuration (
  key text PRIMARY KEY, value_json jsonb NOT NULL, updated_by bigint REFERENCES users(id), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX assessments_org_status_idx ON assessments(organization_id,status,created_at DESC);
CREATE INDEX responses_assessment_idx ON responses(assessment_id,participant_id);
CREATE INDEX score_runs_assessment_idx ON score_runs(assessment_id,is_current,created_at DESC);
CREATE INDEX audit_entity_idx ON audit_logs(entity,entity_id,created_at DESC);
COMMIT;
