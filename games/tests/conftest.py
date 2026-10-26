import importlib.util
from pathlib import Path

import pytest

GAMES_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = GAMES_DIR.parent


def load_game(name):
    """Imports `games/<name>.py` by path, the way the bot loads it (it is not a package)."""
    spec = importlib.util.spec_from_file_location(name, GAMES_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def netrunner():
    return load_game("netrunner")
