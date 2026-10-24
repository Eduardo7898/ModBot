import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite://db.sqlite3")

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
