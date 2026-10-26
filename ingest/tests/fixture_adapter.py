"""A fake game adapter for the tests. Tests change `CARDS` to simulate upstream changes."""

import json
from pathlib import Path

import polars as pl

SOURCE = {"url": "https://example.invalid/cards.json", "license": "test data"}

CARDS = [
    {"code": "001", "name": "Alpha", "text": "First card"},
    {"code": "002", "name": "Beta", "text": "Second card", "image_url": "https://example.invalid/002.jpg"},
]
REF = "v1"


def fetch(raw_dir: Path) -> str:
    (raw_dir / "nested").mkdir()
    (raw_dir / "nested" / "cards.json").write_text(json.dumps(CARDS))
    return REF


def transform(raw_dir: Path) -> pl.DataFrame:
    cards = json.loads((raw_dir / "nested" / "cards.json").read_text())
    return pl.DataFrame(
        {
            "source_id": [c["code"] for c in cards],
            "title": [c["name"] for c in cards],
            "card": [json.dumps(c) for c in cards],
        }
    )
