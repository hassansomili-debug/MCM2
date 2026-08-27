# Current UI Audit

Audit date: 2026-08-27
Application: نضج MCM / Marketing Communication Maturity
Scope: Phase 1 repository and deployed UI audit. No visual redesign proposed.

## Current stack

- Frontend: static `index.html`, vanilla `app.js`, `styles.css`, and `import.css`.
- Backend: Python standard library `BaseHTTPRequestHandler` in `server.py`.
- Local persistence: SQLite initialized by `server.py`.
- Deployment: Vercel Python Function entrypoint `api/index.py` and `vercel.json` rewrites.
- Client routing: hash routes rendered by JavaScript; no framework router.

## Control inventory

| Current element | Current page | Current behavior | Required behavior | Destination route | API endpoint | Permission required | Implementation status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Organization switcher | Dashboard shell | Shows organization list in a toast | Switch active organization and reload scoped data | `/company/profile` or organization context | `GET /api/organizations`, `POST /api/session/organization` | Organization member | Partial: list only |
| Overview navigation | All | Changes hash and active navigation state | Load dashboard route and persisted data | `/dashboard` | `GET /api/dashboard` | Authenticated member | Partial: hash route |
| Assessments navigation | All | Loads assessment list | List, create, repeat, resume assessments | `/assessment/new`, `/assessment/:id` | `GET/POST /api/assessments` | COMPANY_ADMIN, CONSULTANT | Partial: list/create/resume |
| New assessment | Dashboard, assessments | Creates a draft assessment | Start wizard with type, participants, and instrument confirmation | `/assessment/new` | `POST /api/assessments` | COMPANY_ADMIN, CONSULTANT | Partial: direct draft |
| Assessment answers | Assessment form | Inputs autosave to SQLite | Persist typed responses with retry and review state | `/assessment/:id` | `POST /api/assessments/:id/answers` | Assigned participant | Partial |
| Submit assessment | Assessment form | Calculates scores on server | Validate required items, confirm, submit immutable response set | `/assessment/:id/review` | `POST /api/assessments/:id/submit` | Assigned participant, admin | Partial: no review gate |
| Dimension cards | Dashboard | Render API scores when completed | Open dimension result and evidence | `/results/:id/dimensions/:code` | `GET /api/results/:id/dimensions/:code` | Authorized organization member | Partial: not clickable |
| MCM total card | Dashboard | Render API-derived MCM average | Show configurable maturity level and provisional notice | `/results/:id` | `GET /api/results/:id` | Authorized organization member | Partial |
| SMCE card | Dashboard | Render separate API-derived SMCE average | Show five dimensions, trend, and diagnostics separately | `/results/:id/smce` | `GET /api/results/:id/smce` | Authorized organization member | Partial |
| Dimension filter | Dashboard | Toast only | Select assessment and construct | `/dashboard` | `GET /api/dashboard?assessment_id=&construct=` | Authorized organization member | Missing |
| Maturity chart filter | Dashboard | Toast only; chart is static SVG | Query real historical assessment scores | `/history` | `GET /api/history?range=` | Authorized organization member | Missing |
| Executive insight menu | Dashboard | No meaningful action | Open diagnosis/export actions | `/results/:id/diagnosis` | `GET /api/diagnostics/:id`, `POST /api/reports` | Authorized organization member | Missing |
| Diagnosis link | Dashboard | Hash-only link | Open deterministic diagnosis and gaps | `/results/:id/diagnosis` | `GET /api/diagnostics/:id` | Authorized organization member | Partial: placeholder view |
| Add participants | Dashboard | Opens participant view | Invite participants with secure token and assessment role | `/company/participants` | `GET/POST /api/invitations` | COMPANY_ADMIN, CONSULTANT | Partial |
| Priority table | Dashboard | Static rows and arrows | Load calculated gaps, recommendations, and roadmap actions | `/results/:id/priorities` | `GET /api/priorities/:id` | Authorized organization member | Missing |
| Roadmap navigation | All | Placeholder explanatory page | Show 30/90/180-day actions and update status | `/roadmap/:id` | `GET/PATCH /api/roadmap/:id` | COMPANY_ADMIN for updates | Missing |
| Reports navigation | All | Placeholder explanatory page | List, view, print, and download generated reports | `/reports` | `GET/POST /api/reports` | COMPANY_ADMIN, CONSULTANT | Missing |
| Notifications icon | Shell | Opens API-backed notification view | Show target links and mark read | `/notifications` | `GET/PATCH /api/notifications` | Authenticated member | Partial |
| User chip | Shell | Browser confirm then deletes local token | Account menu, profile, server logout | `/company/settings` | `GET /api/me`, `POST /api/auth/logout` | Authenticated user | Partial: no server revoke |
| Settings icon | Shell | Opens settings view | Persist profile, organization, locale, security, notifications | `/company/settings` | `GET/PATCH /api/settings` | User; admin for org fields | Partial |
| Methodology navigation | All | Static paragraph | Load construct definitions and configurable levels | `/methodology` | `GET /api/methodology` | Public/authenticated | Partial: static only |
| Researcher navigation | All | Opens DOCX import UI | Research console and instrument management | `/research` | `GET /api/research/summary` | RESEARCHER, SUPER_ADMIN | Partial: import UI only |
| DOCX picker | Researcher | Parses DOCX in browser | Secure upload, server validation, preview, draft creation | `/research/instruments/import` | `POST /api/instrument-versions/import` | RESEARCHER, SUPER_ADMIN | Partial: browser parse + API draft |
| Import approval | Researcher | Creates and publishes draft via API | Review warnings, explicit publish, version audit | `/research/instruments/:id` | `POST /api/instrument-versions/:id/approve` | RESEARCHER, SUPER_ADMIN | Partial |
| Research exports | Researcher | No control exists | Generate anonymized Excel, CSV, SAV, codebook | `/research/exports` | `POST /api/exports` | RESEARCHER, SUPER_ADMIN | Missing |

## Hard-coded or mock data

- Dashboard executive narrative, priority rows, owners, gaps, chart path, chart dates, completion percentage, and report date remain in `index.html`.
- Seed organization, user, development password, dimensions, instrument, and 24 seed items are created in `server.py`.
- Maturity thresholds are hard-coded in `app.js` and must become database configuration.
- Client-side DOCX parser is real processing, but it does not persist every supported table.
- The deployed public site previously served the static demo and must be redeployed from the current `main` branch.

## Current blockers

1. No PostgreSQL connection, migration system, or `DATABASE_URL` is configured.
2. SQLite on Vercel `/tmp` is ephemeral and cannot be the production research database.
3. No registration, password reset, email verification, refresh/revocation flow, or managed identity provider.
4. Current roles (`admin`, `assessor`, `researcher`) do not implement the required five-role RBAC model.
5. No consent, company setup, multi-respondent response sets, or PII/research data separation.
6. No database-driven maturity levels, scale values, item settings, diagnostic rules, recommendations, benchmarks, or roadmap entities.
7. No PDF, Excel, SPSS, codebook, history, benchmark, data-quality, or statistical analysis services.
8. No automated test suite, TypeScript check, frontend lint, or production build exists because the repository has no package manifest.

## Files inspected

`index.html`, `app.js`, `styles.css`, `import.css`, `server.py`, `api/index.py`, `vercel.json`, `README.md`, `AUDIT.md`, `.gitignore`.

## Files planned for later phases

- Modify: `index.html`, `app.js`, `styles.css`, `import.css`, `server.py`, `api/index.py`, `README.md`, `vercel.json`.
- Create: PostgreSQL migrations, database adapter, auth modules, service modules, test suite, and route-specific frontend modules.
- Phase 1 documentation created: `docs/current-ui-audit.md`, `docs/architecture.md`, `docs/database-schema.md`, `docs/api-specification.md`.
