# Security controls

Implemented controls include PBKDF2-SHA256 password hashing (310,000 iterations), hashed bearer-session storage and expiry, one-time reset tokens, same-origin CORS, strict static-file allowlisting, body/DOCX limits, archive/XML safety checks, per-IP local rate limits, tenant checks, role checks, participant assignment checks, immutable submission, audit logs, private/no-store downloads, CSP, clickjacking and MIME protections.

Company administrators cannot grant researcher or super-admin roles. Research access is global only for `RESEARCHER` and `SUPER_ADMIN`. Participant sessions are assessment-scoped and become read-only after submission. There is no invitation flow, so no invitation token can be replayed.

Production requirements not supplied by this repository are HTTPS termination, managed/shared rate limiting for multiple instances, SMTP or another reset-delivery provider, centralized logs/alerts, secret rotation, encrypted backups and tested restore, a provisioned durable database, and periodic access review.

`MCM_ENV=production` refuses a default/short super-admin secret, an exposed development reset token, or a database path under `/tmp`.

The production adapter supports Supabase PostgreSQL with short-lived serverless connections, disabled prepared statements for transaction pooling, and TLS required by default unless the connection URL explicitly selects a stricter mode. Migration version 9 enables row-level security on all 47 application tables and removes table, sequence and future-default access from Supabase `anon` and `authenticated` roles. The backend must connect with a private server-side database role; no database credential is exposed to the browser. Vercel remains labelled `ephemeral-demo` until `MCM_DATABASE_URL` is configured and the migration/seed has been applied.
