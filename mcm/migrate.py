from __future__ import annotations

import json

from .database import migrate_postgres


def main() -> None:
    result = migrate_postgres()
    print(json.dumps({"status": "ok", **result}, separators=(",", ":")))


if __name__ == "__main__":
    main()
