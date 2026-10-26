import importlib
import sys
import uuid
from pathlib import Path

import pytest

from ingest import db


@pytest.fixture
def adapter(monkeypatch):
    """The fixture adapter, registered as the game `fixture`, with its data reset after each test."""
    module = importlib.import_module("ingest.tests.fixture_adapter")
    monkeypatch.setitem(sys.modules, "ingest.sources.fixture", module)
    monkeypatch.setattr(module, "CARDS", [dict(c) for c in module.CARDS])
    monkeypatch.setattr(module, "REF", module.REF)
    return module


MIGRATIONS = sorted((Path(__file__).resolve().parents[2] / "migrations").glob("*.sql"))


@pytest.fixture
def conn():
    """A connection whose search path is a throwaway schema with the migrations applied; skips when no database is reachable."""
    try:
        admin = db.connect()
    except Exception as e:
        pytest.skip(f"no database reachable: {e}")
    schema = f"ingest_test_{uuid.uuid4().hex[:12]}"
    admin.autocommit = True
    admin.execute(f"CREATE SCHEMA {schema}")
    connection = db.connect(schema=schema)
    try:
        for path in MIGRATIONS:
            connection.execute(path.read_text())
        connection.execute("INSERT INTO games (id, name, source) VALUES ('fixture', 'Fixture', 'test')")
        connection.commit()
        yield connection
    finally:
        connection.close()
        admin.execute(f"DROP SCHEMA {schema} CASCADE")
        admin.close()
