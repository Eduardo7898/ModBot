from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path.home() / ".modbot"
DATA_DIR.mkdir(parents=True, exist_ok=True)
if os.name == "posix":
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass

DEFAULT_DB_PATH = DATA_DIR / "modbot.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite://{DEFAULT_DB_PATH}")

TORTOISE_ORM = {
    "connections": {"default": DATABASE_URL},
    "apps": {
        "models": {
            "models": ["modbot.database.models"],
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "UTC",
}
