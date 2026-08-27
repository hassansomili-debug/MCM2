# MCM control audit

Audit date: 2026-08-27
Source: local files and deployed dashboard at https://mcm-2-navy.vercel.app/

The current app is a static HTML/JavaScript MVP. No authentication, API, database, persistence, route handler, or server-side scoring exists. The only data processing is browser-local DOCX parsing.

## Control map

| Control | Current behavior | Target function | Route/API | Permission | Database entity |
| --- | --- | --- | --- | --- | --- |
| Organization switcher | No handler | List and switch organization context | `GET /api/organizations`, `POST /api/session/organization` | Organization member | `organizations`, `organization_members` |
| Overview nav | Hash-only active state | Navigate dashboard | `GET /` / client route `overview` | Authenticated member | `organizations`, `assessments`, `scores` |
| Assessments nav | Toast placeholder | List, create, resume, repeat assessments | `GET /api/assessments`, `POST /api/assessments` | Assessor, admin | `assessments` |
| Roadmap nav | Toast placeholder | Show deterministic gaps, actions, and dated roadmap | `GET /api/roadmap` | Authenticated member | `diagnostics`, `recommendations`, `roadmap_actions` |
| Reports nav | Toast placeholder | Generate/download executive report | `GET /api/reports`, `POST /api/reports` | Admin, executive | `reports` |
| Researcher nav | Renders import UI | Manage instrument versions and dataset tools | `GET /api/instruments` | Researcher | `instruments`, `instrument_versions` |
| Methodology nav | Toast placeholder | Display construct definitions, scoring rules, maturity levels | `GET /api/methodology` | Authenticated member | `constructs`, `dimensions`, `maturity_levels` |
| Settings icon | No handler | Profile, organization, locale, notifications | `GET/PATCH /api/settings` | Admin for org settings | `users`, `organizations`, `notification_preferences` |
| Notifications icon | No handler | Read notification list and mark read | `GET/PATCH /api/notifications` | Authenticated member | `notifications` |
| User chip | No handler | Account menu and sign out | `GET /api/me`, `POST /api/auth/logout` | Authenticated user | `users`, `sessions` |
| New assessment | “Coming soon” toast | Create draft tied to published instrument version | `POST /api/assessments` | Assessor, admin | `assessments`, `instrument_versions` |
| Executive insight menu | Generic toast | Export/copy insight and open diagnostic | `GET /api/diagnostics/latest`, `POST /api/reports` | Authenticated member | `diagnostics`, `reports` |
| Deep diagnosis link | Hash-only | Open diagnostic and cross-dimension gaps | `GET /api/diagnostics/:assessmentId` | Authenticated member | `diagnostics`, `gap_analysis` |
| Add participants | Generic toast | Invite respondents with expiry and role | `POST /api/invitations` | Admin, assessor | `invitations`, `assessment_participants` |
| Dimension filter | No filtering | Select assessment/construct and reload scores | `GET /api/dashboard?assessment_id=&construct=` | Authenticated member | `assessments`, `scores` |
| Maturity chart filter | Generic toast | Query historical series by date range | `GET /api/trends?range=` | Authenticated member | `assessments`, `scores` |
| SMCE menu | Generic toast | View/export SMCE diagnostic detail | `GET /api/scores/:assessmentId?construct=SMCE` | Authenticated member | `scores`, `dimensions`, `answers` |
| Full roadmap link | Hash-only | Open roadmap page | `GET /api/roadmap` | Authenticated member | `roadmap_actions` |
| Priority row arrows | Generic toast | Open gap detail and recommendation | `GET /api/gaps/:gapId` | Authenticated member | `gap_analysis`, `recommendations` |
| DOCX file picker | Browser-only parser | Upload and validate an immutable instrument draft | `POST /api/instrument-versions/import` | Researcher | `instrument_versions`, `instrument_items` |
| Import approval | Button-only state change | Publish validated version with audit record | `POST /api/instrument-versions/:id/approve` | Researcher approver | `instrument_versions`, `audit_logs` |
| Cards and score values | Hard-coded demo data | Render API-backed MCM/SMCE scores | `GET /api/dashboard` | Authenticated member | `scores`, `dimensions`, `maturity_levels` |

## Scientific constraints

- MCM and SMCE are separate constructs and are scored independently.
- Items are loaded only from an immutable instrument version; the UI must never own questionnaire item definitions.
- Raw answers are stored separately from deterministic scores.
- Scoring, maturity classification, dimension aggregation, gap analysis, and roadmap priority are server-side deterministic operations.
- AI, if added later, receives scored diagnostics and may produce narrative text only; it cannot write scores or maturity levels.

## Implementation order

1. API foundation, SQLite schema, seed instrument, deterministic MCM/SMCE scoring, and audit logging.
2. Replace dashboard hard-coded values with authenticated API data and real navigation state.
3. Assessment draft flow with autosave, save/resume, repeat, invitations, and RBAC.
4. Researcher import persistence, approval, instrument versioning, dataset explorer, Excel/SPSS/codebook exports.
5. Diagnostic/recommendation/roadmap/report services, trend and benchmark queries, notifications, settings, and bilingual routing.
6. Production deployment hardening: external identity provider, PostgreSQL migration, CSRF/session policy, backups, observability, and PDF generation.
