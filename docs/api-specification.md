# API Specification

This document defines the target API contract and records the currently implemented prototype endpoints. All endpoints are JSON unless a file download is explicitly stated.

## Conventions

- Authentication: managed auth session in production; current prototype accepts `Authorization: Bearer <token>`.
- Every organization-scoped endpoint checks membership and role server-side.
- Errors use stable codes and user-safe messages; raw database errors are never returned.
- Scores are written only by the server scoring service.
- `MCM` and `SMCE` are separate `construct_type` values in every score response.

## Public/authentication

| Method | Endpoint | Purpose | Permission |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register` | Create user and organization, pending verification | Public |
| `POST` | `/api/auth/login` | Start session | Public |
| `POST` | `/api/auth/logout` | Revoke current session | Authenticated |
| `POST` | `/api/auth/forgot-password` | Send reset message without revealing account existence | Public |
| `POST` | `/api/auth/reset-password` | Consume reset token | Public with token |
| `GET` | `/api/me` | Current user, organizations, role | Authenticated |

## Company and organization

| Method | Endpoint | Purpose | Permission |
| --- | --- | --- | --- |
| `GET` | `/api/organizations` | List memberships | Authenticated |
| `POST` | `/api/organizations` | Create organization | Authenticated |
| `POST` | `/api/session/organization` | Switch active organization | Organization member |
| `GET/PATCH` | `/api/company/profile` | Read/update setup profile | COMPANY_ADMIN; read member |
| `GET/POST/PATCH` | `/api/company/team` | Manage members and roles | COMPANY_ADMIN |
| `GET/POST` | `/api/invitations` | List/create participant invitations | COMPANY_ADMIN, CONSULTANT |
| `POST` | `/api/invitations/:token/accept` | Accept secure invitation | Invitation holder |
| `GET/PATCH` | `/api/settings` | Account, locale, notifications | Authenticated; org fields admin |
| `GET/PATCH` | `/api/notifications` | List/read notifications | Authenticated |

## Instruments and import

| Method | Endpoint | Purpose | Permission |
| --- | --- | --- | --- |
| `GET` | `/api/instruments` | List versions and lifecycle state | RESEARCHER, SUPER_ADMIN |
| `GET` | `/api/instruments/:id` | Version details and item counts | RESEARCHER, SUPER_ADMIN |
| `POST` | `/api/instrument-versions/import` | Upload/validate DOCX and create draft | RESEARCHER, SUPER_ADMIN |
| `POST` | `/api/instrument-versions/:id/approve` | Explicitly publish reviewed draft | RESEARCHER, SUPER_ADMIN |
| `POST` | `/api/instrument-versions/:id/archive` | Archive version without deleting history | RESEARCHER, SUPER_ADMIN |
| `GET` | `/api/instruments/:id/items` | Versioned item bank | RESEARCHER, SUPER_ADMIN |

Validation errors must distinguish blocking errors from warnings. A draft cannot publish with duplicate item/dimension codes, unknown dimensions/scales, invalid response types, invalid reverse-coding metadata, or missing required Arabic wording.

## Assessment lifecycle

| Method | Endpoint | Purpose | Permission |
| --- | --- | --- | --- |
| `POST` | `/api/assessments` | Create FULL or REASSESSMENT against current published version | COMPANY_ADMIN, CONSULTANT |
| `GET` | `/api/assessments` | List organization assessments | Organization member |
| `GET` | `/api/assessments/:id` | Load instrument items and saved responses | Assigned participant/member |
| `POST` | `/api/assessments/:id/answers` | Idempotent autosave batch | Assigned participant |
| `GET` | `/api/assessments/:id/review` | Completion/missing-required summary | Assigned participant, admin |
| `POST` | `/api/assessments/:id/submit` | Validate and lock response set, then score | Assigned participant, admin |
| `POST` | `/api/assessments/:id/repeat` | Create reassessment preserving prior version reference | COMPANY_ADMIN, CONSULTANT |

Responses support `LIKERT`, `BOOLEAN`, `NUMERIC`, `TEXT`, and `MULTIPLE_CHOICE`, with explicit missing states. Autosave must validate item ownership, scale values, assessment status, and participant access.

## Results and improvement

| Method | Endpoint | Purpose | Permission |
| --- | --- | --- | --- |
| `GET` | `/api/results/:id` | MCM total, maturity, dimensions, strengths | Organization member |
| `GET` | `/api/results/:id/dimensions/:code` | Dimension diagnostic detail | Organization member; no unauthorized raw responses |
| `GET` | `/api/results/:id/smce` | Independent SMCE result | Organization member |
| `GET` | `/api/diagnostics/:id` | Rule-generated diagnosis | Organization member |
| `GET` | `/api/gaps/:id` | Cross-dimension gap analysis | Organization member |
| `GET` | `/api/priorities/:id` | Configurable priority ranking | Organization member |
| `GET/PATCH` | `/api/roadmap/:id` | 30/90/180 roadmap and status updates | Read member; COMPANY_ADMIN updates |
| `GET` | `/api/history` | Historical scores by range | Organization member |
| `GET` | `/api/benchmark/:id` | Cohort comparison with minimum-N protection | Organization member |

## Reports and research

| Method | Endpoint | Purpose | Permission |
| --- | --- | --- | --- |
| `GET/POST` | `/api/reports` | List/generate report jobs | COMPANY_ADMIN, CONSULTANT |
| `GET` | `/api/reports/:id/download` | Download real generated PDF | Report owner/member |
| `GET` | `/api/research/summary` | Research case counts without fabricated empty statistics | RESEARCHER, SUPER_ADMIN |
| `GET` | `/api/research/dataset` | Anonymized filtered cases | RESEARCHER, SUPER_ADMIN |
| `GET` | `/api/research/statistics` | Descriptive statistics only when observations exist | RESEARCHER, SUPER_ADMIN |
| `POST` | `/api/research/exports` | Excel/SAV/CSV/codebook export job | RESEARCHER, SUPER_ADMIN |
| `GET` | `/api/research/exports/:id/download` | Download export artifact | Export actor |
| `GET` | `/api/research/audit` | Research/admin audit log | RESEARCHER, SUPER_ADMIN |

## Current prototype implementation

Implemented today in `server.py`: `POST /api/auth/login`, `GET /api/me`, `GET /api/organizations`, `GET/POST /api/assessments`, `GET /api/assessments/:id`, `POST /api/assessments/:id/answers`, `POST /api/assessments/:id/submit`, `GET/POST /api/invitations`, `GET/POST /api/notifications`, `GET/POST /api/settings`, `GET /api/instruments`, and `POST /api/instrument-versions/import` plus approval.

Current gaps: no registration/reset/logout, no review endpoint, no consent endpoint, no report/export/history/benchmark/diagnostic services, and no PostgreSQL adapter. These are explicitly deferred to later phases.

## Scoring response contract

```json
{
  "assessment_id": "uuid",
  "instrument_version_id": "uuid",
  "scores": {
    "MCM": {
      "total": 0,
      "maturity_level": null,
      "dimensions": []
    },
    "SMCE": {
      "total": 0,
      "dimensions": []
    }
  },
  "classification_notice": "Research Beta — Provisional maturity classification"
}
```

No client-provided score is trusted. A score payload is generated after deterministic normalization, missing-data handling, dimension aggregation, and maturity lookup on the server.
