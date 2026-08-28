# Deployment

## Durable single-host Beta

Run one Python 3.12 process behind HTTPS with `MCM_HOST=0.0.0.0` and `MCM_DB_PATH` on an encrypted persistent volume. Set `MCM_ENV=production`, `MCM_ADMIN_NAME`, `MCM_ADMIN_EMAIL`, a private `MCM_ADMIN_PASSWORD`, `MCM_ALLOW_REGISTRATION` deliberately, and `MCM_EXPOSE_DEV_RESET_TOKEN=0`. Back up SQLite using its online backup mechanism and test restore.

## Vercel demo

`api/index.py` is a supported `BaseHTTPRequestHandler` entry point. `vercel.json` routes API paths, applies security headers and excludes test/document files from the function bundle. `.python-version` pins Python 3.12.

Vercel Function local storage is `/tmp`; it is not a durable database and may differ between instances. The deployed site therefore disables public registration, labels itself `ephemeral-demo`, exposes no credentials, and warns direct participants not to enter sensitive or real operational data. The configured manager account is read from deployment secrets. A durable production deployment requires a PostgreSQL adapter and external object storage or a persistent host.

Environment-variable changes apply only to new Vercel deployments. After push/deploy, verify `/api/health`, `/api/public-config`, login, autosave, submission and the response security/cache headers.

## PostgreSQL path

`migrations/001_postgresql.sql` documents the target durable schema. The running SQL layer still uses SQLite placeholders and transaction behavior, so do not set `DATABASE_URL` and assume compatibility. Implement and parity-test a database adapter first.
