# Architecture

## Runtime topology

The repository is a zero-dependency Python application. A static Arabic RTL SPA calls a same-origin JSON API served by one `ThreadingHTTPServer` handler. All business rules execute on the server; the client displays returned state and never calculates a scientific score.

```text
Browser (index.html + CSS + app.js)
       |  same-origin JSON / files
       v
mcm.api.API
       +-- identity, tenant guards and RBAC
       +-- assessment lifecycle
       +-- deterministic scoring and diagnostics
       +-- DOCX validation
       +-- PDF / XLSX / SPSS generation
       v
SQLite database on a persistent path
```

`server.py` is the local entry point and `api/index.py` is the legacy Vercel adapter. SQLite is durable only when `MCM_DB_PATH` points to a persistent disk. Vercel `/tmp` is explicitly treated as ephemeral and must not receive real production data.

## Bounded contexts

1. Identity and organization: users, sessions, memberships, roles, consents, company profile and settings.
2. Scientific instrument: instruments, immutable versions, dimensions, scales, items, thresholds, rules and recommendations.
3. Assessment: participants, invitations, autosaved responses, review, submission and reassessment lineage.
4. Scoring: item normalization, reverse coding, dimension aggregation, separate MCM/SMCE totals and append-only score runs.
5. Improvement: diagnostics, gaps, priorities, recommendations and 30/90/180-day roadmap.
6. Research: anonymized cases, consent/origin filters, data quality, descriptive statistics, benchmarks and exports.
7. Operations: reports, notifications, configuration, audit logs and health.

## Invariants

- MCM and SMCE remain separate constructs. `MCM_TOTAL` includes only the seven MCM dimensions; `SMCE_TOTAL` includes only the five SMCE dimensions.
- Every assessment freezes its `instrument_version_id`; submitted answers and score-run snapshots are append-only.
- Missing values are not converted to zero. Denominators are based on answered, eligible items.
- Maturity boundaries, rule thresholds and priority weights are version/configuration data, not browser constants.
- A published version cannot be changed. Duplicate and archive operations preserve historical assessments.
- Organization-scoped access is checked on every API request; UI route guards are convenience only.
- Research rows use `research_id`, omit PII by default, and apply both `data_origin` and research-consent policy.
- AI, if added later, may narrate deterministic output only; it cannot manufacture scores, validation or statistical significance.

## Scientific status

The bundled instrument is `PILOT` and visibly labelled Research Beta. It exists to exercise the product workflow. It is not represented as psychometrically validated. A real item bank must pass the documented DOCX import, expert review, pilot and validation process before any version is marked `VALIDATED`.

## Production evolution

The current single-process architecture is intentionally deployable on a persistent Python host. Higher-volume production should retain the API contract while replacing the storage adapter with PostgreSQL, moving authentication to a managed identity provider, and moving large report/export tasks to a queue. The target DDL is recorded in `migrations/001_postgresql.sql`; application SQL still targets SQLite and must not be pointed at PostgreSQL until an adapter is implemented and parity-tested.
