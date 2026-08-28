"""Local and serverless entry point for the Nudj MCM platform."""

from http.server import ThreadingHTTPServer

from mcm.api import API
from mcm.config import HOST, PORT
from mcm.database import init_db

__all__ = ["API", "init_db"]


if __name__ == "__main__":
    init_db()
    print(f"NUDJ MCM listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), API).serve_forever()
