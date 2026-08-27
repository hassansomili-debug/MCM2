from server import API, init_db

# Vercel loads BaseHTTPRequestHandler subclasses exported as `handler`.
# SQLite is suitable for local development only; production must use an external database.
init_db()
handler = API
