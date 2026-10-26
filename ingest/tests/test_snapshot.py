import json
import zipfile
from datetime import date

import polars as pl

from ingest import snapshot


def frame(cards):
    return pl.DataFrame({"source_id": [c[0] for c in cards], "title": [c[1] for c in cards], "card": [c[2] for c in cards]})


def test_content_hash_ignores_row_order_and_key_order():
    a = frame([("1", "One", '{"a":1,"b":2}'), ("2", "Two", "{}")])
    b = frame([("2", "Two", "{}"), ("1", "One", '{ "b": 2, "a": 1 }')])
    assert snapshot.content_hash(a) == snapshot.content_hash(b)


def test_content_hash_changes_with_any_field():
    base = frame([("1", "One", '{"a":1}')])
    for other in (
        frame([("1", "One", '{"a":2}')]),
        frame([("1", "Uno", '{"a":1}')]),
        frame([("9", "One", '{"a":1}')]),
        frame([("1", "One", '{"a":1}'), ("2", "Two", "{}")]),
    ):
        assert snapshot.content_hash(base) != snapshot.content_hash(other)


def test_same_day_snapshots_get_numeric_suffixes(tmp_path):
    day = date(2026, 10, 26)
    names = [snapshot.new_snapshot_dir("g", tmp_path, today=day).name for _ in range(3)]
    assert names == ["2026-10-26", "2026-10-26-2", "2026-10-26-3"]


def test_snapshots_sort_by_date_then_number(tmp_path):
    for name in ["2026-10-26-10", "2026-10-27", "2026-10-26", "2026-10-26-2"]:
        path = tmp_path / "g" / "snapshots" / name
        path.mkdir(parents=True)
        (path / "meta.json").write_text("{}")
    assert [p.name for p in snapshot.list_snapshots("g", tmp_path)] == ["2026-10-26", "2026-10-26-2", "2026-10-26-10", "2026-10-27"]


def test_folders_without_meta_are_not_snapshots(tmp_path):
    (tmp_path / "g" / "snapshots" / "2026-10-26").mkdir(parents=True)
    assert snapshot.list_snapshots("g", tmp_path) == []


def test_archive_raw_zips_and_removes_the_folder(tmp_path):
    (tmp_path / "raw" / "sub").mkdir(parents=True)
    (tmp_path / "raw" / "a.txt").write_text("a")
    (tmp_path / "raw" / "sub" / "b.txt").write_text("b")
    snapshot.archive_raw(tmp_path)
    assert not (tmp_path / "raw").exists()
    assert sorted(zipfile.ZipFile(tmp_path / "raw.zip").namelist()) == ["a.txt", "sub/b.txt"]
    with snapshot.raw_dir(tmp_path) as raw:
        assert (raw / "sub" / "b.txt").read_text() == "b"


def test_raw_dir_prefers_the_folder(tmp_path):
    (tmp_path / "raw").mkdir()
    with snapshot.raw_dir(tmp_path) as raw:
        assert raw == tmp_path / "raw"
