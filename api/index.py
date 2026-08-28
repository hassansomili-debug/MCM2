from server import API, init_db

# Vercel loads BaseHTTPRequestHandler subclasses exported as `handler`.
# SQLite remains available locally. Production verifies the migrated Supabase
# PostgreSQL schema here without running DDL during every serverless cold start.
init_db()


class handler(API):
	pass
