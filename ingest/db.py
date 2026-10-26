"""Database connection settings, read the way `src/settings.rs` reads them."""

import os
import tomllib
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
KEYS = ["host", "port", "username", "password", "database", "max_connections"]


def load_settings(config_dir: Path = REPO_DIR / "config", env: dict[str, str] | None = None) -> dict:
    """Reads `config/{PERGAMON_RUN_ENV}.toml` (default `dev`) and returns its `[database]` table.

    `PERGAMON_DATABASE_<KEY>` environment variables override single keys (for example `PERGAMON_DATABASE_HOST`).
    """
    env = os.environ if env is None else env
    path = config_dir / f"{env.get('PERGAMON_RUN_ENV', 'dev')}.toml"
    with open(path, "rb") as f:
        database = dict(tomllib.load(f).get("database", {}))
    for key in KEYS:
        value = env.get(f"PERGAMON_DATABASE_{key.upper()}")
        if value is not None:
            database[key] = int(value) if key in ("port", "max_connections") else value
    return database


def conninfo(database: dict) -> str:
    """A libpq connection string for psycopg."""
    parts = {"host": "host", "port": "port", "dbname": "database", "user": "username", "password": "password"}
    return " ".join(f"{k}={database[v]}" for k, v in parts.items() if v in database)
