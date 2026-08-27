# Database Schema

This is the target PostgreSQL schema for Phase 2 onward. The current SQLite schema is a partial prototype and does not yet implement all entities below.

## Identity and organization

| Table | Key fields | Purpose |
| --- | --- | --- |
| `users` | `id`, `auth_user_id`, `email`, `full_name`, `job_title`, `phone`, `preferred_language` | PII-backed application identity; email should be owned by managed auth where possible. |
| `organizations` | `id`, `name`, `sector`, `subsector`, `size`, `country`, `region`, `data_origin` | Company tenant and research origin metadata. |
| `organization_users` | `organization_id`, `user_id`, `role`, `status` | Many-to-many membership and server-side RBAC. |
| `consents` | `id`, `participant_id`, `consent_type`, `consent_version`, `accepted`, `accepted_at` | Separate service consent from research consent. |
| `company_profiles` | `organization_id`, onboarding fields, CRM/analytics fields | Company setup and profile data. |

Required roles: `COMPANY_RESPONDENT`, `COMPANY_ADMIN`, `CONSULTANT`, `RESEARCHER`, `SUPER_ADMIN`.

## Scientific instrument

| Table | Key fields | Purpose |
| --- | --- | --- |
| `instruments` | `id`, `code`, `name`, `status` | Logical instrument identity. |
| `instrument_versions` | `id`, `instrument_id`, `version`, `status`, `validated_at`, `published_at` | Immutable lifecycle: DRAFT, EXPERT_REVIEW, PILOT, VALIDATED, ARCHIVED. |
| `dimensions` | `id`, `instrument_version_id`, `code`, `construct_type`, `name_ar`, `name_en`, `weight` | Versioned MCM/SMCE dimensions. |
| `scales` | `id`, `instrument_version_id`, `code`, `response_type`, `min_value`, `max_value` | Configurable response scales. |
| `scale_values` | `id`, `scale_id`, `value`, `label_ar`, `label_en`, `missing_type` | Valid values and missing-value semantics. |
| `items` | `id`, `code`, `source`, `lifecycle_status` | Stable scientific item identity. |
| `item_versions` | `id`, `item_id`, `instrument_version_id`, `dimension_id`, wording, `reverse_coded`, `required`, `weight`, `response_type` | Item wording and scoring metadata per instrument version. |
| `item_options` | `id`, `item_version_id`, `value`, labels | Multiple-choice options. |
| `maturity_levels` | `id`, `instrument_version_id`, `code`, labels, threshold/configuration | Configurable five-level classification; no frontend cutoff constants. |

## Assessment and scoring

| Table | Key fields | Purpose |
| --- | --- | --- |
| `assessments` | `id`, `organization_id`, `instrument_version_id`, `assessment_type`, `status`, timestamps, `data_origin` | Assessment lifecycle and frozen instrument reference. |
| `assessment_participants` | `assessment_id`, `participant_id`, `role`, `token_status` | Multi-respondent-ready participant membership. |
| `participants` | `id`, `research_id`, PII reference, role metadata | Separate PII from anonymized research identifier such as `P000001`. |
| `responses` | `id`, `assessment_id`, `participant_id`, `item_version_id`, `value`, `missing_type`, timestamps | Raw response storage; never coerce missing to zero. |
| `assessment_scores` | `assessment_id`, `construct_type`, `total_score`, `maturity_level_id`, method metadata | Separate MCM_TOTAL and SMCE_TOTAL. |
| `dimension_scores` | `assessment_id`, `dimension_id`, `score`, `answered_count`, method metadata | Server-generated dimension results. |

## Diagnostics and improvement

| Table | Key fields | Purpose |
| --- | --- | --- |
| `diagnostic_rules` | `id`, `instrument_version_id`, conditions JSON, severity, confidence, diagnosis type | Database-driven deterministic rules. |
| `diagnostic_results` | `assessment_id`, `rule_id`, evidence JSON, affected dimensions | Materialized diagnostic output. |
| `recommendations` | `id`, `dimension_id`, problem, action, KPI, owner, impact, effort, horizon, version, active | Reusable evidence-backed recommendation catalog. |
| `assessment_recommendations` | `assessment_id`, `recommendation_id`, priority, rationale | Assessment-specific recommendation selection. |
| `roadmap_items` | `id`, `assessment_id`, recommendation, owner, target date, status, impact, effort, KPI | 30/90/180-day implementation tracking. |

## Research and operations

| Table | Key fields | Purpose |
| --- | --- | --- |
| `benchmarks` | cohort fields, sample size, scores, generated_at | Privacy-aware benchmark aggregates. |
| `research_exports` | `id`, actor, filters, origin policy, format, status, file reference | Audited export jobs. |
| `reports` | `id`, `assessment_id`, type, status, file reference, created_by | Executive and detailed PDFs. |
| `notifications` | `id`, `user_id`, `type`, title, body, `target_url`, `read_at` | Notification center. |
| `audit_logs` | `id`, actor, action, entity type/id, metadata, timestamp | Administrative and scientific audit trail. |
| `system_configuration` | `key`, typed value, version, updated_by | Benchmark minimum N, scoring methods, priority weights, feature flags. |

## Database rules

- Foreign keys enforce organization and instrument-version ownership.
- Unique constraints prevent duplicate dimension codes within a version and duplicate item codes within an instrument version.
- Published versions are append-only and cannot be edited in place.
- Research views expose anonymized IDs and exclude default PII.
- `data_origin` is required on assessments and research cases and is filtered explicitly on export/benchmark queries.
- Row-level security or an equivalent service-layer tenant check must protect every organization-scoped table.
