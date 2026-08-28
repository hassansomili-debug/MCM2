"""Vercel entry point.

Vercel loads BaseHTTPRequestHandler subclasses exported as `handler`. SQLite
remains available locally. Production verifies the migrated Supabase PostgreSQL
schema here without running DDL during every serverless cold start.

Importing the platform can legitimately fail: `mcm.config` refuses an unsafe
production configuration, and `init_db()` refuses an unmigrated or unreachable
database. Left unguarded, either raises during module import, which Vercel
reports only as an opaque FUNCTION_INVOCATION_FAILED on every route. Capture the
failure instead and answer each request with the reason, so a misconfigured
deployment is diagnosable without access to the runtime logs.

`handler` must stay a module-level definition: Vercel detects the Serverless
Function by scanning for it, and a definition nested inside a conditional makes
the build fail with "doesn't match any Serverless Functions". Only the base
class is chosen dynamically.
"""

import json
import re
import traceback
from http.server import BaseHTTPRequestHandler

_CREDENTIAL = re.compile(r"(?<=://)[^/\s@]+:[^/\s@]+(?=@)")

_STARTUP_ERROR = None


def _redact(text: str) -> str:
    """Strip inline connection-string credentials before returning a message."""
    return _CREDENTIAL.sub("***:***", text)


class _StartupFailureHandler(BaseHTTPRequestHandler):
    """Answers every request with the captured startup failure."""

    def _respond(self):
        error = _STARTUP_ERROR or {"type": "UnknownError", "message": ""}
        body = json.dumps(
            {
                "status": "startup_failed",
                "error": error["type"],
                "message": _redact(error["message"]),
                "hint": (
                    "The serverless function could not initialize. Check the "
                    "MCM_ENV, MCM_DATABASE_URL and MCM_ADMIN_PASSWORD "
                    "environment variables, and confirm migration 4 has been "
                    "applied to the configured database."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        self.send_response(503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    do_GET = _respond
    do_POST = _respond
    do_PATCH = _respond
    do_PUT = _respond
    do_DELETE = _respond
    do_HEAD = _respond
    do_OPTIONS = _respond

    def log_message(self, *args):
        return


try:
    from server import API as _Base, init_db

    init_db()
except Exception as exc:  # noqa: BLE001 - reported to the operator above
    _STARTUP_ERROR = {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
    _Base = _StartupFailureHandler


class handler(_Base):
    pass
