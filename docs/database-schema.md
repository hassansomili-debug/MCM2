# Database schema

`mcm/database.py` owns the executable schema, additive SQLite migration, scientific seed and indexes. SQLite enables foreign keys, WAL and a busy timeout locally. Supabase uses `mcm/postgres.py`, which converts DB-API placeholders and identity writes, preserves row compatibility, disables prepared statements for Supavisor, and opens one short-lived connection per request/transaction.

## Identity and tenancy

| Tables | Purpose |
| --- | --- |
| `users`, `sessions`, `password_reset_tokens` | PBKDF2 identities, hashed bearer sessions, one-time password reset tokens. |
| `organizations`, `memberships` | Tenant and many-to-many role membership. |
| `company_profiles`, `organization_profiles` | Organization onboarding and operational profile. |
| `consents` | Versioned, separate service and research consent for users or participants. |
| `user_settings`, `notifications` | Locale/preferences and notification inbox. |

Roles are `COMPANY_RESPONDENT`, `COMPANY_ADMIN`, `CONSULTANT`, `RESEARCHER`, and `SUPER_ADMIN`.

## Instrument

| Tables | Purpose |
| --- | --- |
| `instruments`, `instrument_versions` | Logical instrument and lifecycle snapshots (`DRAFT`, `EXPERT_REVIEW`, `PILOT`, `VALIDATED`, `ARCHIVED`). |
| `dimensions` | Versioned MCM, SMCE, ENABLER and OUTCOME dimensions with weights/order. |
| `scales`, `scale_values` | Response bounds, localized labels and explicit missing semantics. |
| `items` | Versioned wording, construct, dimension, response type, required flag, weight and reverse-coding flag. |
| `maturity_levels` | Server-side MCM maturity intervals. |
| `diagnostic_rules`, `recommendations` | Versioned deterministic evidence library. |

SQLite and PostgreSQL preserve the same 46-table application surface. The Supabase SQL snapshot is `supabase/migrations/202608280001_mcm_platform.sql`; it retains epoch timestamps, numeric flags and text JSON so API and export semantics remain identical across backends.

## Assessment and scoring

| Tables | Purpose |
| --- | --- |
| `assessments` | Tenant, version, type, origin, status, timestamps and reassessment parent. |
| `assessment_context` | Per-case SME demographics and four enabling conditions, retained outside the MCM score denominator. |
| `participants`, `assessment_participants`, `participant_sessions`, `invitations` | Multi-respondent identity boundary and invitation access. |
| `responses` | Raw numeric/text value or missing type, unique per assessment/participant/item. |
| `score_runs` | Append-only run number, scoring/configuration snapshot and input/output hashes. |
| `response_item_scores`, `score_run_dimensions`, `score_run_totals` | Complete trace of the current and previous calculations. |
| `dimension_scores`, `assessment_scores` | Current materialized results for fast reads. |

The legacy `answers` and `scores` tables remain only for safe migration of the earlier repository; new writes use `responses` and the explicit score tables.

## Diagnosis, research and operations

| Tables | Purpose |
| --- | --- |
| `diagnostic_results`, `assessment_recommendations`, `roadmap_items` | Evidence, ranked improvement work and execution status. |
| `reports`, `research_exports` | Audited generation requests with immutable report/export payloads and hashes. |
| `data_quality_flags` | Straight-line, incomplete and related quality findings. |
| `audit_logs` | Actor, action, entity and safe JSON metadata. |
| `system_configuration` | Typed JSON configuration such as minimum benchmark N, gap threshold and priority weights. |
| `schema_migrations` | Applied baseline version. |

## Critical constraints

- Unique membership per user/organization and response per assessment/participant/item.
- Unique dimension and item code inside an instrument version.
- Foreign keys from assessments to frozen instrument versions and from score rows to the assessment/run.
- Tenant filtering is mandatory in service queries in addition to relational constraints.
- Research exports default to `REAL`, require research consent for real organizations, omit direct PII, and preserve explicit origin metadata.
- Submitted assessments are locked; recalculation creates a new score run rather than updating prior evidence.

## Backup

Stop writes or use SQLite online backup before copying the database. Back up the database and deployment configuration together, encrypt at rest, verify restoration regularly, and never commit `mcm.sqlite3` or generated export files.

For Supabase, use scheduled database backups appropriate to the project plan and test a restore into a separate project. Connection URLs and database passwords remain deployment secrets and must never be committed or exposed through `/api/public-config`.
