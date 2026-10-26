"""Netrunner cards from Null Signal Games' netrunner-cards-json repository.

Upstream records are kept as they are, plus `image_url` (NetrunnerDB's card image CDN). `code` is the stable id; reprints have
their own codes and so their own rows.
"""

import io
import json
import posixpath
import tarfile
from pathlib import Path

import httpx
import polars as pl

REPO = "Null-Signal-Games/netrunner-cards-json"
SOURCE = {
    "url": f"https://github.com/{REPO}",
    "license": "see COPYRIGHT.md in the repository (card data and images belong to Null Signal Games / Fantasy Flight Games)",
    "images": "https://card-images.netrunnerdb.com/v2/large/<code>.jpg",
}
IMAGE_URL = "https://card-images.netrunnerdb.com/v2/large/{code}.jpg"


def latest_ref() -> str:
    """The commit SHA of the repository's default branch."""
    response = httpx.get(f"https://api.github.com/repos/{REPO}/commits/HEAD", headers={"Accept": "application/vnd.github+json"}, timeout=30)
    response.raise_for_status()
    return response.json()["sha"]


def fetch(raw_dir: Path) -> str:
    """Downloads the tarball for the latest commit and keeps `pack/*.json` under `raw_dir/pack/`."""
    ref = latest_ref()
    response = httpx.get(f"https://codeload.github.com/{REPO}/tar.gz/{ref}", follow_redirects=True, timeout=120)
    response.raise_for_status()
    extract_packs(response.content, raw_dir)
    return ref


def extract_packs(tarball: bytes, raw_dir: Path) -> None:
    """Writes each `<top folder>/pack/<name>.json` of the tarball to `raw_dir/pack/<name>.json`, and nothing else."""
    (raw_dir / "pack").mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        for member in tar:
            parts = posixpath.normpath(member.name).split("/")
            if member.isfile() and len(parts) == 3 and parts[1] == "pack" and parts[2].endswith(".json") and ".." not in parts:
                (raw_dir / "pack" / parts[2]).write_bytes(tar.extractfile(member).read())


def transform(raw_dir: Path) -> pl.DataFrame:
    cards = []
    for path in sorted((raw_dir / "pack").glob("*.json")):
        cards += json.loads(path.read_text())
    cards = [{**card, "image_url": IMAGE_URL.format(code=card["code"])} for card in cards]
    return pl.DataFrame(
        {
            "source_id": [c["code"] for c in cards],
            "title": [c["title"] for c in cards],
            "card": [json.dumps(c, ensure_ascii=False) for c in cards],
        },
        schema={"source_id": pl.String, "title": pl.String, "card": pl.String},
    )
