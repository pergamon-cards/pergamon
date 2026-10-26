import importlib
import sys

import pytest


@pytest.fixture
def adapter(monkeypatch):
    """The fixture adapter, registered as the game `fixture`, with its data reset after each test."""
    module = importlib.import_module("ingest.tests.fixture_adapter")
    monkeypatch.setitem(sys.modules, "ingest.sources.fixture", module)
    monkeypatch.setattr(module, "CARDS", [dict(c) for c in module.CARDS])
    monkeypatch.setattr(module, "REF", module.REF)
    return module
