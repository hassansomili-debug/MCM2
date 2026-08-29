# Deployment

## Durable single-host Beta

Run one Python 3.12 process behind HTTPS with `MCM_HOST=0.0.0.0` and `MCM_DB_PATH` on an encrypted persistent volume. Set `MCM_ENV=production`, `MCM_ADMIN_NAME`, `MCM_ADMIN_EMAIL`, a private `MCM_ADMIN_PASSWORD`, `MCM_ALLOW_REGISTRATION` deliberately, and `MCM_EXPOSE_DEV_RESET_TOKEN=0`. Back up SQLite using its online backup mechanism and test restore.

## Vercel with Supabase

`api/index.py` is a supported `BaseHTTPRequestHandler` entry point. `vercel.json` routes API paths, applies security headers and excludes test/document files from the function bundle. `.python-version` pins Python 3.12.

Vercel Function local storage is `/tmp`; it is not a durable database and may differ between instances. Production therefore uses Supabase Postgres through `MCM_DATABASE_URL`. Without that secret the site remains explicitly labelled `ephemeral-demo` and must not receive real data.

Environment-variable changes apply only to new Vercel deployments. After push/deploy, verify `/api/health`, `/api/public-config`, login, autosave, submission and the response security/cache headers.

## Supabase connection and migration

Use the Supavisor transaction pooler URL on port `6543` for `MCM_DATABASE_URL`; serverless runtime connections disable prepared statements with `prepare_threshold=None`. Use a direct connection or the session pooler on port `5432` for `MCM_DATABASE_MIGRATION_URL`. Include `sslmode=require` at minimum and URL-encode special characters in the database password.

Install `requirements.txt`, configure the administrator secrets locally for the initial seed, and run `python3 -m mcm.migrate` once. The migration:

- acquires a PostgreSQL advisory lock;
- creates the 47-table application schema;
- seeds instrument `0.4.0`, its 67 items, 20 dimensions and the manager account;
- records schema version `9`;
- enables RLS and revokes table/sequence access from Supabase `anon` and `authenticated` roles.

The auditable SQL snapshot is `supabase/migrations/202608280001_mcm_platform.sql`; do not apply it separately because the Python migration keeps schema creation, seed validation and version marking in one transaction. Vercel startup never applies DDL; it only checks schema version and seed integrity.

Use a clean Supabase project for the first production cutover. The migrator is idempotent at the current schema version and upgrades a version 4, 5 or 6 database in place, but deliberately refuses any older application schema instead of marking a partial `CREATE TABLE IF NOT EXISTS` upgrade as successful. Back up and migrate any pre-v4 PostgreSQL database with an explicit, reviewed upgrade before cutover.

Set at least these Vercel Production secrets before redeploying:

```dotenv
MCM_ENV=production
MCM_DATABASE_URL=postgresql://...
MCM_ADMIN_NAME=...
MCM_ADMIN_EMAIL=...
MCM_ADMIN_PASSWORD=...
MCM_ALLOW_REGISTRATION=0
MCM_EXPOSE_DEV_RESET_TOKEN=0
```

Keep `MCM_DATABASE_MIGRATION_URL` outside Vercel unless an approved migration workflow needs it. After deployment, create a test assessment, redeploy, and verify the assessment persists across a cold start.
