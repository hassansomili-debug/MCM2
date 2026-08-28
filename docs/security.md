# Security controls

Implemented controls include PBKDF2-SHA256 password hashing (310,000 iterations), hashed bearer-session storage and expiry, one-time reset tokens, same-origin CORS, strict static-file allowlisting, body/DOCX limits, archive/XML safety checks, per-IP local rate limits, tenant checks, role checks, participant assignment checks, immutable submission, audit logs, private/no-store downloads, CSP, clickjacking and MIME protections.

Company administrators cannot grant researcher or super-admin roles. Research access is global only for `RESEARCHER` and `SUPER_ADMIN`. Participant sessions are assessment-scoped, become read-only after submission and cannot be recreated by accepting an already accepted invitation.

Production requirements not supplied by this repository are HTTPS termination, managed/shared rate limiting for multiple instances, SMTP or another reset-delivery provider, centralized logs/alerts, secret rotation, encrypted backups and tested restore, durable PostgreSQL or a single persistent encrypted volume, and periodic access review.

`MCM_ENV=production` refuses a default/short super-admin secret, an exposed development reset token, or a database path under `/tmp`. Vercel is published only as an explicitly labelled ephemeral demo until a durable external data adapter exists.
