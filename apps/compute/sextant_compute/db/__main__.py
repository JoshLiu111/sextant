"""Apply pending migrations: ``uv run python -m sextant_compute.db``."""

import os

from sextant_compute.db import migrate

url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("Set DATABASE_URL (or DATABASE_URL_UNPOOLED) first")
names = migrate(url)
print("Applied:", ", ".join(names) if names else "nothing (up to date)")
