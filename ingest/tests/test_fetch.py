import json

import polars as pl
import pytest

from ingest import fetch as commands
from ingest import snapshot
from ingest.__main__ import main
from ingest.validate import ValidationError


def fetch(tmp_path, **kwargs):
    return commands.fetch("fixture", data_dir=tmp_path, check_images=False, **kwargs)


def test_fetch_writes_parquet_meta_and_zips_raw(tmp_path, adapter):
    directory = fetch(tmp_path)
    assert sorted(p.name for p in directory.iterdir()) == ["cards.parquet", "meta.json", "raw.zip"]
    df = pl.read_parquet(directory / "cards.parquet")
    assert df.columns == ["source_id", "title", "card"]
    assert df["title"].to_list() == ["Alpha", "Beta"]
    meta = snapshot.read_meta(directory)
    assert meta["game"] == "fixture" and meta["source_ref"] == "v1" and meta["card_count"] == 2
    assert meta["source"] == adapter.SOURCE and meta["raw"] == "raw.zip"
    assert meta["content_hash"] == snapshot.content_hash(df)


def test_keep_raw_leaves_the_folder(tmp_path, adapter):
    directory = fetch(tmp_path, keep_raw=True)
    assert sorted(p.name for p in directory.iterdir()) == ["cards.parquet", "meta.json", "raw"]
    assert (directory / "raw" / "nested" / "cards.json").is_file()
    assert snapshot.read_meta(directory)["raw"] == "raw"


def test_unchanged_upstream_leaves_no_new_folder(tmp_path, adapter, capsys):
    fetch(tmp_path)
    assert fetch(tmp_path) is None
    assert len(snapshot.list_snapshots("fixture", tmp_path)) == 1
    assert [p.name for p in (tmp_path / "fixture" / "snapshots").iterdir()] == [snapshot.list_snapshots("fixture", tmp_path)[0].name]
    assert "upstream unchanged" in capsys.readouterr().out


def test_changed_upstream_on_the_same_day_gets_a_suffix(tmp_path, adapter):
    first = fetch(tmp_path)
    adapter.CARDS[0]["text"] = "Corrected"
    adapter.REF = "v2"
    second = fetch(tmp_path)
    assert second.name == first.name + "-2"
    assert snapshot.read_meta(second)["source_ref"] == "v2"
    assert snapshot.read_meta(second)["content_hash"] != snapshot.read_meta(first)["content_hash"]


def test_a_new_ref_with_identical_cards_is_unchanged(tmp_path, adapter):
    fetch(tmp_path)
    adapter.REF = "v2"
    assert fetch(tmp_path) is None


def test_invalid_data_leaves_nothing_behind(tmp_path, adapter):
    adapter.CARDS.append({"code": "001", "name": "Duplicate"})
    with pytest.raises(ValidationError):
        fetch(tmp_path)
    assert list((tmp_path / "fixture" / "snapshots").iterdir()) == []


def test_adapter_failure_leaves_nothing_behind(tmp_path, adapter, monkeypatch):
    def boom(raw_dir):
        raise RuntimeError("network down")

    monkeypatch.setattr(adapter, "fetch", boom)
    with pytest.raises(RuntimeError):
        fetch(tmp_path)
    assert list((tmp_path / "fixture" / "snapshots").iterdir()) == []


def test_transform_reruns_from_the_zip_after_an_adapter_fix(tmp_path, adapter, monkeypatch):
    directory = fetch(tmp_path)
    before = snapshot.read_meta(directory)

    original = adapter.transform

    def fixed(raw_dir):
        df = original(raw_dir)
        return df.with_columns(pl.col("title").str.to_uppercase())

    monkeypatch.setattr(adapter, "transform", fixed)
    commands.transform("fixture", directory)
    assert pl.read_parquet(directory / "cards.parquet")["title"].to_list() == ["ALPHA", "BETA"]
    after = snapshot.read_meta(directory)
    assert after["content_hash"] != before["content_hash"] and after["fetched_at"] == before["fetched_at"]
    assert (directory / "raw.zip").is_file() and not (directory / "raw").exists()


def test_unknown_game_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit, match="no adapter for game 'nope'"):
        commands.fetch("nope", data_dir=tmp_path)


def test_cli_reports_validation_errors(monkeypatch, capsys):
    monkeypatch.setattr(commands, "fetch", lambda *a, **k: (_ for _ in ()).throw(ValidationError(["bad"])))
    assert main(["fetch", "fixture", "--skip-image-check"]) == 1
    assert "snapshot is invalid" in capsys.readouterr().err
