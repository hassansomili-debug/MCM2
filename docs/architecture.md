# Architecture

## Current state

The application is a static Arabic RTL single-page interface backed by a small Python standard-library HTTP service. The browser renders hash-based views and calls JSON endpoints. The service currently uses SQLite and is exposed locally through `python3 server.py`; Vercel loads `api/index.py` as a Python Function.

Current flow:

```text
Browser HTML/CSS/JS
        |
        | JSON + Bearer token
        v
Python API handler
        |
        v
SQLite (local or ephemeral /tmp on Vercel)
```

This is an implementation baseline, not a production architecture. SQLite and seeded credentials must not be used for durable production data.

## Target architecture

```text
Browser / responsive RTL-LTR client
        |
        v
Vercel frontend and route handlers
        |
        +--> Supabase Auth / managed identity
        |
        +--> Python scoring and research service
        |          |
        |          +--> deterministic scoring engine
        |          +--> diagnostics and recommendations
        |          +--> report/export workers
        |
        v
PostgreSQL (Supabase)
        |
        +--> organizations and PII boundary
        +--> immutable instrument versions
        +--> responses and assessment snapshots
        +--> scores, diagnostics, roadmap, reports
        +--> anonymized research views
```

## Architectural invariants

- MCM and SMCE are separate constructs. `MCM_TOTAL` only aggregates MCM dimensions; `SMCE_TOTAL` only aggregates SMCE dimensions.
- Questionnaire content and scoring parameters are loaded from an immutable instrument version, never hard-coded in frontend components.
- Final scores, maturity levels, missing-data handling, diagnostic rules, and priorities execute server-side.
- AI may narrate deterministic results but cannot create or change scores, maturity, validation status, significance, or research inclusion.
- Published instrument versions are immutable. A change creates a new version.
- Company PII is separated from anonymized researcher identifiers and exports.
- Every organization-scoped query is authorized server-side using membership and role.
- Real, synthetic, demo, and test data have explicit origins and are never silently mixed.

## Bounded contexts

1. Identity and organization: users, sessions, organizations, memberships, roles, consents, profile.
2. Scientific instrument: instruments, versions, dimensions, scales, items, options, lifecycle and import validation.
3. Assessment: assessment lifecycle, participants, responses, autosave, review, submission and version snapshot.
4. Scoring and evidence: normalized item scores, dimension scores, MCM/SMCE totals, maturity configuration.
5. Diagnosis and improvement: rules, gaps, priorities, recommendations, roadmap actions.
6. Research: anonymized cases, benchmarks, data quality, descriptive statistics and exports.
7. Reporting and operations: reports, notifications, audit logs, configuration and health.

## Deployment boundary

The Vercel Function is acceptable for a prototype API but should not own long-running workers or durable local files. Production deployment should use:

- Vercel for the frontend and short request/response endpoints.
- Supabase Auth and PostgreSQL for identity and durable data.
- A separately deployed FastAPI service for scoring, DOCX processing, PDF/export generation, and queued work when execution exceeds Function limits.
- Environment variables for all URLs, keys, salts, and service credentials.

## Phase 1 decision

No later-phase implementation is started by this document. Phase 2 must first establish PostgreSQL migrations, external auth configuration, and a database adapter behind the current API contract.
