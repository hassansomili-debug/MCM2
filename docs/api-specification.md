# API specification

All JSON endpoints are same-origin under `/api`. Authenticated calls send `Authorization: Bearer <raw-session-token>`; only a SHA-256 token digest is stored. Errors have a stable `error` code and may include a safe `details` object. File routes return `Content-Disposition: attachment`.

## Public and identity

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api` or `/api/health` | Service health. |
| GET | `/api/public-config` | Public branding, direct-entry and storage-mode flags; never returns credentials. |
| POST | `/api/public/assessments` | Create an anonymous SME assessment, demographic snapshot and participant session without an account. |
| POST | `/api/auth/register` | Create a user, organization, admin membership, settings and consents. |
| POST | `/api/auth/login`, `/api/auth/logout` | Create/revoke session. |
| POST | `/api/auth/forgot-password`, `/api/auth/reset-password` | One-time reset flow without account enumeration. |
| GET | `/api/me` | User, active tenant, role and memberships. |

## Organization and participant

| Method | Route | Permission/purpose |
| --- | --- | --- |
| GET/POST | `/api/organizations` | List memberships / create a new tenant. |
| POST | `/api/session/organization` | Switch to a tenant where the user has an active membership. |
| GET/PATCH | `/api/company/profile` | Read profile / update as company admin. |
| GET/POST/PATCH | `/api/company/team` | List or manage memberships as company admin. |
| GET/PATCH | `/api/consents` | Read/update versioned service and research consent. |
| GET/POST | `/api/invitations` | List/create invitations for authorized company roles. |
| GET | `/api/invitations/{token}` | Public invitation summary. |
| POST | `/api/invitations/{token}/accept` | Accept an unexpired invitation and create a participant session. |
| GET/POST | `/api/participant/session/{token}` | Load participant questionnaire. |
| POST | `/api/participant/session/{token}/answers` | Autosave participant answers. |
| POST | `/api/participant/session/{token}/submit` | Validate required items, lock and score. |
| GET, POST/PATCH | `/api/notifications`, `/api/notifications/read` | Inbox and read state. |
| GET/PATCH | `/api/settings` | Account and notification preferences. |

## Instrument lifecycle

Research and super-admin roles can call:

- `GET /api/instruments` or `/api/research/instruments`
- `GET /api/instruments/{version_id}`
- `GET /api/instruments/{version_id}/items`
- `GET /api/research/items?version_id=...`
- `GET /api/research/codebook?version_id=...`
- `POST /api/instrument-versions/preview`
- `POST /api/instrument-versions/import`
- `POST /api/instrument-versions/{id}/approve` (alias: `publish`)
- `POST /api/instrument-versions/{id}/duplicate`
- `POST /api/instrument-versions/{id}/archive`

DOCX payloads contain `filename`, the official Office MIME type and `docx_base64`; JSON `tables` is accepted for deterministic testing. Preview never writes. Import creates a `DRAFT`; approval creates a `PILOT`, never silently `VALIDATED`.

## Assessment and results

| Method | Route | Purpose |
| --- | --- | --- |
| GET/POST | `/api/assessments` | List tenant assessments / create `FULL` or `REASSESSMENT`. |
| GET | `/api/assessments/{id}` | Versioned items, saved responses and review state. |
| POST | `/api/assessments/{id}/answers` | Idempotent validated autosave batch. |
| GET | `/api/assessments/{id}/review` | Required/missing/completion summary. |
| POST | `/api/assessments/{id}/submit` | Lock, score, diagnose and create roadmap. |
| POST | `/api/assessments/{id}/repeat` | Create a linked reassessment. |
| GET | `/api/dashboard` | Tenant dashboard using real stored state. |
| GET | `/api/results/{id}` | Separate MCM/SMCE totals, dimensions, five-stage classification, demographics and provisional relationship interpretation. |
| GET | `/api/results/{id}/dimensions/{code}` | One dimension, evidence-safe diagnostics and recommendation. |
| GET | `/api/results/{id}/smce` | Independent SMCE result and explicit comparison. |
| GET | `/api/diagnostics/{id}`, `/api/gaps/{id}`, `/api/priorities/{id}` | Deterministic improvement evidence. |
| GET/PATCH | `/api/roadmap/{id}` | Read roadmap / update one item by `item_id`. |
| GET | `/api/history?range=...` | Completed tenant assessments. |
| GET | `/api/benchmark/{id}?cohort=overall|sector|size` | Consent/version/origin-filtered aggregate with minimum N. |

All assessment/result routes enforce tenant membership on the server. Submit rejects incomplete required items with HTTP 422 and never trusts a score from the client.

## Reports, research and administration

| Method | Route | Purpose |
| --- | --- | --- |
| GET/POST | `/api/reports` | List/generate completed-assessment report records. |
| GET | `/api/reports/{id}/download` | Generate and download a real PDF from authorized state. |
| GET | `/api/research/summary` | Counts and origin breakdown. |
| GET | `/api/research/dataset?data_origin=...` | Anonymized, filtered cases. |
| GET | `/api/research/statistics?data_origin=...` | Descriptive statistics only where observations exist. |
| GET | `/api/research/data-quality` | Materialized quality findings. |
| GET | `/api/research/audit` | Research/admin audit stream. |
| POST | `/api/research/exports` | Create `XLSX` or `SPSS` export metadata. |
| GET | `/api/research/exports/{id}/download` | Regenerate authorized export for its creator. |
| GET | `/api/admin` | Platform counts and storage status. |
| GET | `/api/admin/organizations`, `/api/admin/users` | Cross-tenant administration. |
| POST/PATCH | `/api/admin/users`, `/api/admin/users/{id}` | Create/update users and role membership. |
| PATCH | `/api/admin/configuration` | Update allowlisted operational/scientific configuration. |

Research routes require `RESEARCHER` or `SUPER_ADMIN`; admin routes require `SUPER_ADMIN`. Real-data research selection additionally requires affirmative organization research consent.

## Score response guarantee

The response contains `assessment_id`, instrument metadata, `scores.MCM`, `scores.SMCE`, `context`, `maturity_progression`, `relationship` and the Research Beta notice. `relationship.status=PROVISIONAL_ASSOCIATION_NOT_CAUSAL` prevents presenting the proposed MCM → SMCE path as established causality. MCM and SMCE totals never share dimensions, and every output can be traced to the frozen input/configuration hashes in `score_runs`.
