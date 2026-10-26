"""Checks that a transformed snapshot follows the contract before it is written."""

import json
import random
from collections.abc import Callable

import httpx
import polars as pl

COLUMNS = ["source_id", "title", "card"]
IMAGE_SAMPLE = 5


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        shown = errors[:10]
        more = f"\n... and {len(errors) - len(shown)} more" if len(errors) > len(shown) else ""
        super().__init__("snapshot is invalid:\n" + "\n".join(f"- {e}" for e in shown) + more)


def head_ok(url: str) -> bool:
    try:
        return httpx.head(url, follow_redirects=True, timeout=15).status_code == 200
    except httpx.HTTPError:
        return False


def validate(df: pl.DataFrame, check_images: bool = True, head: Callable[[str], bool] = head_ok) -> None:
    """Raises `ValidationError` listing every problem found."""
    if df.columns != COLUMNS or any(dtype != pl.String for dtype in df.dtypes):
        raise ValidationError([f"columns must be exactly {COLUMNS} as strings, got {dict(zip(df.columns, df.dtypes))}"])

    errors = []
    if df.is_empty():
        errors.append("no cards")
    for column in COLUMNS:
        if df[column].null_count():
            errors.append(f"{column} has null values")

    dupes = df.filter(df["source_id"].is_duplicated())["source_id"].unique().sort().to_list()
    if dupes:
        errors.append(f"source_id is not unique: {dupes[:5]}")

    empty = df.filter(df["title"].str.strip_chars() == "")["source_id"].to_list()
    if empty:
        errors.append(f"empty title for source_id {empty[:5]}")

    urls = []
    for source_id, card in zip(df["source_id"], df["card"]):
        if card is None:
            continue
        try:
            parsed = json.loads(card)
        except json.JSONDecodeError as e:
            errors.append(f"card for {source_id} is not valid JSON: {e}")
            continue
        if not isinstance(parsed, dict):
            errors.append(f"card for {source_id} is not a JSON object")
        elif parsed.get("image_url"):
            urls.append((source_id, parsed["image_url"]))

    if check_images and urls:
        for source_id, url in random.Random(0).sample(urls, min(IMAGE_SAMPLE, len(urls))):
            if not head(url):
                errors.append(f"image_url for {source_id} does not answer 200: {url}")

    if errors:
        raise ValidationError(errors)
