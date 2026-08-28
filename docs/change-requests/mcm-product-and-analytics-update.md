# Change impact — product, terminology, consultation and analytics update

Phase 0 audit. No production behaviour has been changed by this document.

Audit date: 2026-08-29. Repository `hassansomili-debug/MCM2`, branch `main`, commit `2c0b8fa`.

---

## 0. Premise corrections

The request assumes a stack this repository does not have. The work is all
deliverable, but six instructions must be restated against the real codebase
before implementation, otherwise they cannot be followed literally.

| Request assumes | Repository actually is | Consequence |
| --- | --- | --- |
| Next.js, Server Actions, `/app` routes | Zero-dependency Python `BaseHTTPRequestHandler` (`mcm/api.py`) serving a static vanilla-JS SPA (`app.js`, 893 lines) | Every "route" below is a **hash route** in the SPA plus a JSON endpoint in the Python router |
| TypeScript type checking | No TypeScript anywhere; no `tsconfig.json` | Type check is **not applicable**; the equivalent gate is `python3 -m compileall` |
| ESLint / linting | No linter configured | Lint is **not applicable** |
| Production build | No build step; static files are served verbatim | Build is **not applicable**; the equivalent gate is a successful Vercel deployment |
| `uuid` primary keys | All primary keys are `bigint` (verified on the live Supabase schema) | `consultation_leads.id` and its foreign keys must be `bigint`, not `uuid`, or they cannot reference `assessments.id` |
| Supabase RLS policies enforce per-user access | RLS is enabled on all 44 tables, but **no policies exist**. Access control is enforced entirely in `mcm/api.py`. The database is reached through one privileged server-side role; the browser never holds a database credential | "Enforce through Supabase RLS" cannot work as described. See §11 |

Two further corrections of fact:

- **The level 1 label to be replaced does not exist.** The request names
  `تفاعلي / عشوائي` or `تفاعلي وعشوائي`. The actual stored and displayed label
  is `عشوائي` (verified in source and in the live database). The change is
  therefore `عشوائي` → `ردّة فعل / عشوائي`.
- **The stable code is not `LEVEL_1`.** It is `REACTIVE_AD_HOC`. The request
  says to keep the identifying code stable, so it must be left as is. Renaming
  it to `LEVEL_1` would break `mcm/ai_plans.py:54` and every historical
  `assessment_scores.maturity_level_id` join.

---

## 1. Current state

### 1.1 Framework and routing

Single Python process. `server.py` locally, `api/index.py` on Vercel. One
handler class dispatches by string matching in `mcm/api.py:274`.

The SPA is a hash router (`app.js:157`). There are **no** `/results` or
`/dashboard` URL paths; the existing routes are `#results/:id`, `#overview`,
`#roadmap`, `#admin`, and 27 others. `#results` already exists and is already
labelled `النتائج`.

Static assets and API share one origin. `vercel.json` rewrites `/api/:path*`
to the function and applies CSP, `X-Frame-Options` and no-store headers.

### 1.2 Supabase schema

44 tables, schema version 4, applied by `python3 -m mcm.migrate`. All ids are
`bigint`. RLS is enabled on all 44 tables with zero policies; `anon` and
`authenticated` hold zero grants. `instrument_versions` has columns
`id, instrument_id, version, status, notes, metadata_json, created_by,
created_at, published_at, archived_at`. There is no `consultation` table.

### 1.3 Maturity levels

Defined in `mcm/instrument_v02.py:1392` and seeded into `maturity_levels`.
Live values:

| order | code | `label_ar` | `label_en` | band |
| --- | --- | --- | --- | --- |
| 1 | `REACTIVE_AD_HOC` | عشوائي | Reactive / Ad hoc | [0, 20) |
| 2 | `RESPONSIVE_EMERGING` | ناشئ | Responsive / Emerging | [20, 40) |
| 3 | `MANAGED_INTEGRATED` | متكامل | Managed & Integrated | [40, 60) |
| 4 | `PROACTIVE_ADAPTIVE` | استباقي ومتكيف | Proactive & Adaptive | [60, 80) |
| 5 | `INSTITUTIONALISED_INTELLIGENT` | مؤسسي وذكي | Institutionalised & Intelligent | [80, 100.01) |

The request supplies new Arabic titles for **all five** levels, not only
level 1 — levels 2–5 currently read `ناشئ`, `متكامل`, `استباقي ومتكيف`,
`مؤسسي وذكي` against requested `منظم أوليًا / مستجيب`, `مدار / متكامل`,
`استباقي / متكيّف`, `مستدام / ذكي / قابل للتوسع`. §2 of the request lists these
as homepage card titles. **Whether they also replace the stored labels is
unresolved and must be confirmed before Phase 1.**

`mcm/instruments.py:35` holds `CANONICAL_MATURITY_LABELS_AR`, a tuple used to
validate imported DOCX instruments. Changing labels without updating this
tuple will make DOCX import reject conforming files.

### 1.4 Public "Pilot" / "Research Beta" occurrences

| Location | Text |
| --- | --- |
| `index.html:65` | `Research Beta 1.0` in the sidebar footer |
| `app.js:28` | `PILOT: 'نسخة تجريبية'` status label |
| `app.js:126` | `researchNotice()` — renders `Research Beta` plus "قيد التحقق التجريبي" |
| `app.js:613` | Methodology page — "موسومة Provisional حتى التحقق الكمي" |
| `app.js:619` | Researcher dashboard — calls `researchNotice()` |
| `app.js:632`, `app.js:799` | Instrument admin — "نشر Pilot", `PILOT` badge |
| `mcm/scoring.py:452` | `classification_notice` — "نموذج بحثي قيد التحقق الكمي" |
| `mcm/exports.py` | PDF/SPSS carry `instrument_status` |
| `README.md`, `docs/*` | Internal, not participant-facing |

`app.js:632` and `app.js:799` are **super-admin instrument lifecycle controls**,
not participant-facing. The request says not to delete internal lifecycle data;
these two should keep `PILOT` as an internal product status.

### 1.5 Participant "Dashboard" occurrences

Only one is participant-facing text: `app.js:253`, the landing headline
"داشبورد تنفيذي، وليس مجرد درجة."

Everything else (`dashboardArray`, `dashboardScore`, `dashboardName`,
`normalizeRoadmap(dashboard, …)`, `.dashboard-bars`, `.dashboard-empty`) is
**internal identifiers and CSS classes**, plus the server payload key
`score_payload()["dashboard"]` (`mcm/scoring.py:399`). The request says not to
rename internal variables where it risks breakage. These stay.

The navigation label is already `النتائج` (`app.js:157` label map). There is no
`لوحة التحكم` string anywhere.

### 1.6 Post-submission behaviour

`confirmSubmission()` (`app.js:714`) opens a confirmation dialog; the
`confirm-submit` action then calls the API and re-routes. Participants already
land on their result. There is no `/dashboard` path to redirect, so
acceptance criterion 9 is satisfied by construction — nothing to build.

### 1.7 Roles

`COMPANY_ADMIN`, `COMPANY_RESPONDENT`, `CONSULTANT`, `RESEARCHER`,
`SUPER_ADMIN`. There is **no `PLATFORM_ADMIN` role**; the request names it in
§10. `SUPER_ADMIN` is the equivalent and should be used, or a new role added
with migration and RBAC changes.

### 1.8 Admin endpoints

`GET /api/admin`, `GET /api/admin/organizations`, `GET|POST /api/admin/users`,
`PATCH /api/admin/configuration`. SPA route `#admin`, gated to `SUPER_ADMIN`
in `app.js:157` and again server-side.

---

## 2. Files to modify

### Phase 1 — terminology and public copy
`mcm/instrument_v02.py` (level labels) · `mcm/instruments.py:35` (canonical
label tuple) · `mcm/ai_plans.py:54` (level map) · `app.js:201` (landing
stages) · `app.js:613` (methodology stages) · `app.js:126` (research notice) ·
`app.js:28` (status labels) · `index.html:65` · `mcm/scoring.py:452`
(classification notice) · **new** `renderLanding()` maturity section ·
`platform.css` (cards, drawer)

### Phase 2 — model status
`mcm/database.py` (schema + migration 5) · `mcm/api.py` (status endpoint,
RBAC, audit) · `mcm/config.py` · `app.js` (admin controls)

### Phase 3 — results navigation
`app.js` only. Minimal: `app.js:253` headline. No routing work needed.

### Phase 4–6 — consultation
`mcm/database.py` (two tables, indexes) · `mcm/api.py` (submit, list, assign,
status, consent withdrawal, idempotency) · `app.js` (CTA, form, admin screen) ·
`platform.css` · **new** `#privacy` route and copy

### Phase 7 — analytics
`mcm/database.py` (views) · **new** `mcm/analytics.py` · `mcm/api.py`
(six endpoints) · `app.js` (scatter, quadrants, rankings, benchmarks,
heatmap — hand-rolled SVG, since no chart library may be loaded under the CSP)

### Phase 8 — reports
`mcm/exports.py` (PDF label, consultation section, terminology)

---

## 3. Database migrations

Schema version 4 → 5, applied through `mcm/database.py` and
`python3 -m mcm.migrate`. No manual production edits.

1. **Maturity labels.** `UPDATE maturity_levels SET label_ar=…` keyed on
   `code`. `assessment_scores.maturity_level_id` is a foreign key to a row that
   is updated in place, so **no historical score is rewritten** and every past
   assessment keeps its classification. Note that a past PDF already exported
   carries the old wording; that is a frozen artifact and is left alone.
2. **Status fields.** Add `instrument_versions.product_status` and
   `scientific_status`. Backfill: current `status='PILOT'` →
   `product_status='ACTIVE'`, `scientific_status='EVIDENCE_INFORMED'`.
   Keep `status` for internal lifecycle; do not drop it.
3. **`consultation_leads`** — `bigint` ids, not `uuid`.
4. **`consultation_lead_events`**.
5. **Analytics views** — five views per §9 of the request.
6. **Indexes** — see §5 below.
7. Audit integration via the existing `audit_logs` table and `audit()` helper.

Rollback: each step is additive except step 1, which is reversible by the
inverse `UPDATE`. No `DROP`, no data destruction.

---

## 4. Affected translation keys

There is **no translation catalogue**. The interface is Arabic-only by
deliberate decision (`docs/current-ui-audit.md`) and strings are inline in
`app.js` and the Python modules. "Translation keys" therefore map to the
literal strings listed in §1.4, §1.5 and §2. Introducing a catalogue is a
larger refactor and is out of scope unless requested.

---

## 5. Indexes

Requested index targets checked against real column names:

| Requested | Reality |
| --- | --- |
| `assessment_scores.MCM_TOTAL` / `.SMCE_TOTAL` | **No such columns.** The table is `(assessment_id, construct, total_score, …)`; MCM and SMCE are *rows*, not columns. Correct index: `(construct, total_score)` |
| `assessments.organization_id/status/completed_at/instrument_version_id/data_origin` | `organization_id`, `status`, `completed_at`, `data_origin` exist. The column is **`version_id`**, not `instrument_version_id` |
| `assessment_scores.assessment_id` | Exists |
| existing | `idx_assessments_org_status`, `idx_dimension_scores_assessment`, `idx_score_runs_assessment` already cover part of this |

---

## 6. Affected tests

`tests/test_platform.py`, 11 tests, currently passing. Affected:
`test_complete_company_journey_and_exports` (labels in PDF/XLSX),
`test_scoring_formula_and_reverse_coding` (level boundaries),
`test_direct_participant_flow_demographics_admin_and_no_sara_demo`,
`test_instrument_specification_is_not_misrepresented_as_item_bank`
(canonical label tuple).

New tests required per §16 of the request: terminology, homepage, model status,
results navigation, consultation (12 assertions), analytics (12), access
control (6). Estimated 25–30 new tests.

**The access-control tests cannot be written as "RLS tests"** — see §11.

---

## 7. Compatibility risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Changing labels breaks `CANONICAL_MATURITY_LABELS_AR`, so valid DOCX imports are rejected | High | Update the tuple in the same commit; covered by an existing test |
| Instrument `0.4.0` is published; the architecture states a published version cannot change (`docs/architecture.md`) | High | Label edits are not item or scoring edits, but they do desynchronise `0.4.0` from its published record. Recommend issuing `0.4.1` and migrating, rather than editing in place. **Needs a decision** |
| Removing "Pilot" from participant view while `scientific_status` is `EVIDENCE_INFORMED` | Medium | The requested label `نموذج تطبيقي قائم على الأدلة العلمية` is accurate and makes no validation claim. Safe |
| Analytics charts under a strict CSP | Medium | `vercel.json` allows `script-src 'self'` only. No chart library can be loaded. Charts must be hand-rolled SVG, as `radarChart()` already is |
| Consultation contact data leaking into research exports | High | `mcm/exports.py:113` builds sheets from explicit column lists; add a test asserting no consultation column appears |
| Six new analytics endpoints on a serverless function with a 60 s cap | Medium | Push aggregation into SQL views; never compute in the browser |
| One real assessment already exists in production (`hhgjjhh`, org 4) | Low | Migrations must be non-destructive; verified in §3 |

---

## 8. Privacy and access control — the structural blocker

The request specifies RLS policies as the enforcement mechanism for
consultation data (§6.2) and analytics (§9). **This cannot work in the current
architecture.**

The browser never holds a Supabase credential. All database access goes through
one privileged server-side role in `mcm/postgres.py`. RLS is enabled on all 44
tables precisely to deny the Supabase Data API roles (`anon`, `authenticated`),
which hold zero grants. A policy written against `auth.uid()` would never
evaluate, because there is no Supabase Auth session — sessions are the
platform's own hashed bearer tokens in the `sessions` table.

Two options:

- **(A) Enforce in the API layer**, as every existing tenant and role check
  already does (`mcm/api.py`), and keep RLS as the outer denial of Data API
  roles. Write the six required negative tests against the HTTP API. This is
  consistent, testable, and needs no re-architecture. **Recommended.**
- **(B) Move authentication to Supabase Auth** and write true RLS policies.
  This is a re-architecture of identity across all 44 tables and contradicts
  "do not rebuild the application".

**This needs your decision before Phase 4.**

---

## 9. Open decisions blocking implementation

1. **Levels 2–5 Arabic labels** — homepage card titles only, or replace the
   stored `label_ar` too? (§1.3)
2. **Instrument version** — edit `0.4.0` in place, or issue `0.4.1`? (§7)
3. **Access control** — option A or B? (§8)
4. **`PLATFORM_ADMIN`** — reuse `SUPER_ADMIN`, or add a sixth role? (§1.7)
5. **Transactional email** — §13 requires participant confirmation email. No
   SMTP provider is configured and `docs/security.md` lists this as an unmet
   production requirement. Notifications can be in-app only until one exists.

---

## 10. Rollout plan

Phases 1–3 are low risk and independently shippable. Phase 4 is blocked on
decision 3. Phase 7 is the largest single piece.

Each phase: implement → `python3 -m unittest discover -s tests` →
`python3 -m compileall` → push to `main` → verify the Vercel deployment
answers `/api/health` with 200 → report in the §19 format. No phase proceeds
past a failing test.

Database changes go out as migration 5 in one transaction with an advisory
lock, matching the existing `migrate_postgres()` pattern.

---

## 11. Phase 0 gate results

| Gate | Result |
| --- | --- |
| Existing tests | **11 passed** |
| Python compile (lint equivalent) | **clean** |
| TypeScript type check | **N/A** — no TypeScript |
| Lint | **N/A** — no linter configured |
| Production build | **N/A** — no build step |
| Production health | `/api/health` → 200, `schema_version: 4` |

---

## 12. Files proposed for Phase 1

`mcm/instrument_v02.py` · `mcm/instruments.py` · `mcm/ai_plans.py` ·
`mcm/scoring.py` · `mcm/database.py` (migration 5, labels) · `app.js` ·
`index.html` · `platform.css` · `tests/test_platform.py`

Phase 1 does not touch scoring, item content, or any historical row.
