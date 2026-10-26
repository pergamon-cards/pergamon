"""The `load` and `status` commands: applies a snapshot to the database as a versioned dataset.

Only what differs from the current `cards` rows is written. A changed card's old version moves to `card_revisions`, a
removed card moves there with `removed`, and a load that changes nothing writes nothing (no dataset row either).
SQL is parameterized throughout.
"""

from pathlib import Path

import polars as pl
import psycopg

from . import snapshot
from .sources import load_adapter

SAMPLE = 10

# Staged rows that differ from, or are missing in, the current cards of the game (%s = game).
CHANGED = """
    FROM staged s JOIN cards c ON c.game = %s AND c.source_id = s.source_id
    WHERE s.title IS DISTINCT FROM c.title OR s.card IS DISTINCT FROM c.card
"""
ADDED = "FROM staged s WHERE NOT EXISTS (SELECT 1 FROM cards c WHERE c.game = %s AND c.source_id = s.source_id)"
REMOVED = "FROM cards c WHERE c.game = %s AND NOT EXISTS (SELECT 1 FROM staged s WHERE s.source_id = c.source_id)"


class LoadError(Exception):
    pass


def _stage(cur: psycopg.Cursor, df: pl.DataFrame) -> None:
    cur.execute("CREATE TEMP TABLE staged (source_id TEXT PRIMARY KEY, title TEXT NOT NULL, card JSONB NOT NULL) ON COMMIT DROP")
    with cur.copy("COPY staged (source_id, title, card) FROM STDIN") as copy:
        for row in df.iter_rows():
            copy.write_row(row)


def _count(cur: psycopg.Cursor, tail: str, game: str) -> int:
    cur.execute(f"SELECT count(*) {tail}", (game,))
    return cur.fetchone()[0]


def _changed_keys(old: dict, new: dict) -> list[str]:
    return sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))


def _samples(cur: psycopg.Cursor, game: str) -> list[dict]:
    cur.execute(
        f"SELECT s.source_id, c.title, s.title, c.card, s.card {CHANGED} ORDER BY s.source_id LIMIT {SAMPLE}",
        (game,),
    )
    return [
        {
            "source_id": source_id,
            "title": new_title,
            "changed": (["title"] if old_title != new_title else []) + _changed_keys(old_card, new_card),
        }
        for source_id, old_title, new_title, old_card, new_card in cur.fetchall()
    ]


def load(conn: psycopg.Connection, game: str, directory: Path, dry_run: bool = False) -> dict:
    """Applies the snapshot in `directory` to the database in one transaction.

    Returns the counts (`added`, `changed`, `removed`, `unchanged`), a sample of changed cards, and the new `dataset_id`
    (None for a dry run or when nothing differs). Nothing is written in those two cases.
    """
    meta = snapshot.read_meta(directory)
    df = pl.read_parquet(directory / "cards.parquet")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM games WHERE id = %s FOR UPDATE", (game,))
            if cur.fetchone() is None:
                raise LoadError(f"game '{game}' has no row in `games`: add a migration that inserts it (see the add-migration skill)")
            _stage(cur, df)
            added, changed, removed = (_count(cur, tail, game) for tail in (ADDED, CHANGED, REMOVED))
            result = {
                "added": added,
                "changed": changed,
                "removed": removed,
                "unchanged": df.height - added - changed,
                "samples": _samples(cur, game) if changed else [],
                "dataset_id": None,
            }
            if dry_run or not (added or changed or removed):
                conn.rollback()
                return result

            cur.execute(
                "INSERT INTO datasets (game_id, source_ref, fetched_at, snapshot_path, content_hash, card_count, added, changed, removed)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (game, meta["source_ref"], meta["fetched_at"], _relative(directory), meta["content_hash"], df.height, added, changed, removed),
            )
            dataset = cur.fetchone()[0]

            revision = (
                "INSERT INTO card_revisions (game, source_id, title, card, valid_from, replaced_in, removed)"
                " SELECT c.game, c.source_id, c.title, c.card, c.changed_in, %s, {removed}"
            )
            cur.execute(revision.format(removed="false") + CHANGED, (dataset, game))
            cur.execute(
                "UPDATE cards c SET title = s.title, card = s.card, changed_in = %s FROM staged s"
                " WHERE c.game = %s AND c.source_id = s.source_id AND (s.title IS DISTINCT FROM c.title OR s.card IS DISTINCT FROM c.card)",
                (dataset, game),
            )
            cur.execute(revision.format(removed="true") + " " + REMOVED, (dataset, game))
            cur.execute(
                "DELETE FROM cards c WHERE c.game = %s AND NOT EXISTS (SELECT 1 FROM staged s WHERE s.source_id = c.source_id)", (game,)
            )
            cur.execute(
                "INSERT INTO cards (game, source_id, title, card, added_in, changed_in)"
                " SELECT %s, s.source_id, s.title, s.card, %s, %s " + ADDED,
                (game, dataset, dataset, game),
            )
            cur.execute("UPDATE games SET active_dataset_id = %s WHERE id = %s", (dataset, game))
        conn.commit()
        result["dataset_id"] = dataset
        return result
    except BaseException:
        conn.rollback()
        raise


def _relative(directory: Path) -> str:
    try:
        return str(directory.resolve().relative_to(snapshot.REPO_DIR))
    except ValueError:
        return str(directory)


def format_result(game: str, result: dict, dry_run: bool) -> str:
    counts = f"{result['added']} added, {result['changed']} changed, {result['removed']} removed, {result['unchanged']} unchanged"
    if not (result["added"] or result["changed"] or result["removed"]):
        return f"{game}: already up to date ({counts})"
    lines = [f"{game}: {'would load' if dry_run else 'loaded dataset ' + str(result['dataset_id'])} ({counts})"]
    lines += [f"  changed {s['source_id']} {s['title']!r}: {', '.join(s['changed'])}" for s in result["samples"]]
    if result["changed"] > len(result["samples"]):
        lines.append(f"  ... and {result['changed'] - len(result['samples'])} more changed")
    return "\n".join(lines)


def status(conn: psycopg.Connection, game: str | None = None, data_dir: Path = snapshot.DATA_DIR) -> list[str]:
    """One block of lines per game: the active dataset, the newest snapshot against it, and the upstream ref if known."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT g.id, d.id, d.loaded_at, d.source_ref, d.card_count, d.content_hash FROM games g"
            " LEFT JOIN datasets d ON d.id = g.active_dataset_id WHERE %s::text IS NULL OR g.id = %s ORDER BY g.id",
            (game, game),
        )
        rows = cur.fetchall()
    if game and not rows:
        return [f"{game}: no row in `games`"]

    out = []
    for game_id, dataset, loaded_at, ref, count, digest in rows:
        out.append(f"{game_id}:")
        if dataset is None:
            out.append("  active dataset: none")
        else:
            out.append(f"  active dataset: #{dataset}, loaded {loaded_at:%Y-%m-%d}, ref {ref}, {count} cards")
        newest = (snapshot.list_snapshots(game_id, data_dir) or [None])[-1]
        if newest is None:
            out.append("  newest snapshot: none")
        else:
            meta = snapshot.read_meta(newest)
            state = "matches the database" if meta["content_hash"] == digest else "differs from the database: run load"
            out.append(f"  newest snapshot: {newest.name}, ref {meta['source_ref']}, {meta['card_count']} cards, {state}")
        out.append(f"  upstream: {_upstream(game_id, ref, newest)}")
    return out


def _upstream(game: str, active_ref: str | None, newest: Path | None) -> str:
    try:
        adapter = load_adapter(game)
    except SystemExit:
        return "no adapter"
    if not hasattr(adapter, "latest_ref"):
        return "unknown (adapter has no latest_ref)"
    latest = adapter.latest_ref()
    known = {active_ref, snapshot.read_meta(newest)["source_ref"] if newest else None}
    return f"{latest}, " + ("already fetched" if latest in known else "newer than the newest snapshot: run fetch")
