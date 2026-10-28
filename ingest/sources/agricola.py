"""Agricola (revised edition) cards from klingeling's agricola-card-gallery, which were taken from Board Game Arena.

Upstream records are kept as they are. `id` is BGA's stable id (`C143_StoneBuyer`). Different cards that share a name keep
their own rows; of identical copies (the two Fireplaces, Cooking Hearths, ...) only the first is kept. There are no
card images.
"""

import json
from pathlib import Path

import httpx
import polars as pl

REPO = "klingeling/agricola-card-gallery"
SOURCE = {
    "url": f"https://github.com/{REPO}",
    "license": "none given; the card data comes from Board Game Arena's implementation and belongs to Lookout Games / BGA",
    "images": "none",
}
# Fields that differ between otherwise identical copies of a card.
COPY_FIELDS = ("id", "numbering")


def latest_ref() -> str:
    """The commit SHA of the repository's default branch."""
    response = httpx.get(f"https://api.github.com/repos/{REPO}/commits/HEAD", headers={"Accept": "application/vnd.github+json"}, timeout=30)
    response.raise_for_status()
    return response.json()["sha"]


def fetch(raw_dir: Path) -> str:
    """Downloads `cards.json` at the latest commit into `raw_dir`. The repository's tarball is mostly fonts, so it is skipped."""
    ref = latest_ref()
    response = httpx.get(f"https://raw.githubusercontent.com/{REPO}/{ref}/cards.json", follow_redirects=True, timeout=120)
    response.raise_for_status()
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "cards.json").write_bytes(response.content)
    return ref


def transform(raw_dir: Path) -> pl.DataFrame:
    cards, seen = [], set()
    for card in json.loads((raw_dir / "cards.json").read_text()).values():
        key = json.dumps({k: v for k, v in card.items() if k not in COPY_FIELDS}, sort_keys=True)
        if key not in seen:
            seen.add(key)
            cards.append(card)
    return pl.DataFrame(
        {
            "source_id": [c["id"] for c in cards],
            "title": [c["name"] for c in cards],
            "card": [json.dumps(c, ensure_ascii=False) for c in cards],
        },
        schema={"source_id": pl.String, "title": pl.String, "card": pl.String},
    )
