"""Database connection settings, read the way `src/settings.rs` reads them."""

import os
import tomllib
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

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
    keys = {"host": "host", "port": "port", "dbname": "database", "user": "username", "password": "password"}
    return make_conninfo(**{k: database[v] for k, v in keys.items() if v in database})


def connect(database: dict | None = None, schema: str | None = None) -> psycopg.Connection:
    """Opens a connection with the settings from `load_settings()`; `schema` sets the search path (the tests use a throwaway one)."""
    options = f"-csearch_path={schema}" if schema else None
    return psycopg.connect(conninfo(database or load_settings()), options=options)
