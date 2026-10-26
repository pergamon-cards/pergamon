"""The `fetch` and `transform` commands."""

import shutil
from pathlib import Path

import polars as pl

from . import snapshot
from .sources import load_adapter
from .validate import validate


def write_cards(directory: Path, df: pl.DataFrame) -> str:
    df.write_parquet(directory / "cards.parquet")
    return snapshot.content_hash(df)


def fetch(game: str, keep_raw: bool = False, check_images: bool = True, data_dir: Path = snapshot.DATA_DIR) -> Path | None:
    """Downloads, transforms and validates a game's data into a new snapshot folder, which it returns.

    Returns None, leaving no new folder, when the data is identical to the newest existing snapshot.
    """
    adapter = load_adapter(game)
    previous = snapshot.list_snapshots(game, data_dir)
    directory = snapshot.new_snapshot_dir(game, data_dir)
    try:
        raw = directory / "raw"
        raw.mkdir()
        source_ref = adapter.fetch(raw)
        fetched_at = snapshot.now()
        df = adapter.transform(raw)
        validate(df, check_images=check_images)
        digest = write_cards(directory, df)
        if previous and snapshot.read_meta(previous[-1])["content_hash"] == digest:
            shutil.rmtree(directory)
            print(f"upstream unchanged: {game} matches {previous[-1].name} ({df.height} cards)")
            return None
        snapshot.write_meta(
            directory,
            {
                "game": game,
                "source": adapter.SOURCE,
                "source_ref": source_ref,
                "fetched_at": fetched_at,
                "content_hash": digest,
                "card_count": df.height,
                "raw": "raw" if keep_raw else "raw.zip",
            },
        )
        if not keep_raw:
            snapshot.archive_raw(directory)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    print(f"wrote {directory} ({df.height} cards, ref {source_ref})")
    return directory


def transform(game: str, directory: Path, check_images: bool = False) -> None:
    """Re-runs the adapter's transform on a snapshot's raw data (after fixing the adapter) and rewrites its cards and meta."""
    adapter = load_adapter(game)
    meta = snapshot.read_meta(directory)
    with snapshot.raw_dir(directory) as raw:
        df = adapter.transform(raw)
    validate(df, check_images=check_images)
    meta["content_hash"] = write_cards(directory, df)
    meta["card_count"] = df.height
    meta["transformed_at"] = snapshot.now()
    snapshot.write_meta(directory, meta)
    print(f"rewrote {directory / 'cards.parquet'} ({df.height} cards)")
