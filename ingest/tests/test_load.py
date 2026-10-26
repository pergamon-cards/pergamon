import pytest

from ingest import fetch as commands
from ingest import load as loading


def snap(tmp_path, **kwargs):
    return commands.fetch("fixture", data_dir=tmp_path, check_images=False, **kwargs)


def rows(conn, sql):
    return conn.execute(sql).fetchall()


def test_first_load_adds_everything(conn, tmp_path, adapter):
    result = loading.load(conn, "fixture", snap(tmp_path))
    assert (result["added"], result["changed"], result["removed"], result["unchanged"]) == (2, 0, 0, 0)
    ds = result["dataset_id"]
    assert rows(conn, "SELECT source_id, title, added_in, changed_in FROM cards ORDER BY source_id") == [
        ("001", "Alpha", ds, ds),
        ("002", "Beta", ds, ds),
    ]
    assert rows(conn, "SELECT source_ref, card_count, added, changed, removed, snapshot_path IS NOT NULL FROM datasets") == [
        ("v1", 2, 2, 0, 0, True)
    ]
    assert rows(conn, "SELECT active_dataset_id FROM games WHERE id = 'fixture'") == [(ds,)]
    assert rows(conn, "SELECT count(*) FROM card_revisions") == [(0,)]


def test_reloading_the_same_snapshot_is_up_to_date(conn, tmp_path, adapter):
    directory = snap(tmp_path)
    loading.load(conn, "fixture", directory)
    result = loading.load(conn, "fixture", directory)
    assert result["dataset_id"] is None and result["unchanged"] == 2
    assert "already up to date" in loading.format_result("fixture", result, False)
    assert rows(conn, "SELECT count(*) FROM datasets") == [(1,)]


def test_changed_card_keeps_one_revision(conn, tmp_path, adapter):
    first = loading.load(conn, "fixture", snap(tmp_path))["dataset_id"]
    adapter.CARDS[0]["text"] = "Corrected"
    adapter.REF = "v2"
    result = loading.load(conn, "fixture", snap(tmp_path))
    second = result["dataset_id"]
    assert (result["added"], result["changed"], result["removed"], result["unchanged"]) == (0, 1, 0, 1)
    assert result["samples"] == [{"source_id": "001", "title": "Alpha", "changed": ["text"]}]
    assert rows(conn, "SELECT source_id, card ->> 'text', added_in, changed_in FROM cards ORDER BY source_id") == [
        ("001", "Corrected", first, second),
        ("002", "Second card", first, first),
    ]
    assert rows(conn, "SELECT source_id, card ->> 'text', valid_from, replaced_in, removed FROM card_revisions") == [
        ("001", "First card", first, second, False)
    ]


def test_removed_card_moves_to_revisions(conn, tmp_path, adapter):
    first = loading.load(conn, "fixture", snap(tmp_path))["dataset_id"]
    del adapter.CARDS[1]
    adapter.REF = "v2"
    result = loading.load(conn, "fixture", snap(tmp_path))
    assert (result["added"], result["changed"], result["removed"]) == (0, 0, 1)
    assert rows(conn, "SELECT source_id FROM cards") == [("001",)]
    assert rows(conn, "SELECT source_id, valid_from, replaced_in, removed FROM card_revisions") == [("002", first, result["dataset_id"], True)]


def test_added_card(conn, tmp_path, adapter):
    loading.load(conn, "fixture", snap(tmp_path))
    adapter.CARDS.append({"code": "003", "name": "Gamma", "text": "New"})
    adapter.REF = "v2"
    result = loading.load(conn, "fixture", snap(tmp_path))
    assert (result["added"], result["changed"], result["removed"], result["unchanged"]) == (1, 0, 0, 2)
    assert rows(conn, "SELECT added_in = %s, changed_in = %s FROM cards WHERE source_id = '003'" % ((result["dataset_id"],) * 2)) == [(True, True)]
    assert rows(conn, "SELECT count(*) FROM card_revisions") == [(0,)]


def test_a_title_change_alone_is_a_change(conn, tmp_path, adapter):
    loading.load(conn, "fixture", snap(tmp_path))
    adapter.CARDS[0]["name"] = "Alpha Prime"
    adapter.REF = "v2"
    result = loading.load(conn, "fixture", snap(tmp_path))
    assert result["samples"][0]["changed"] == ["title", "name"]
    assert rows(conn, "SELECT title FROM cards WHERE source_id = '001'") == [("Alpha Prime",)]


def test_dry_run_writes_nothing(conn, tmp_path, adapter):
    directory = snap(tmp_path)
    result = loading.load(conn, "fixture", directory, dry_run=True)
    assert result["added"] == 2 and result["dataset_id"] is None
    assert "would load" in loading.format_result("fixture", result, True)
    for table in ("cards", "datasets", "card_revisions"):
        assert rows(conn, f"SELECT count(*) FROM {table}") == [(0,)]
    assert rows(conn, "SELECT active_dataset_id FROM games WHERE id = 'fixture'") == [(None,)]


def test_dry_run_of_changes_writes_nothing(conn, tmp_path, adapter):
    loading.load(conn, "fixture", snap(tmp_path))
    adapter.CARDS[0]["text"] = "Corrected"
    adapter.REF = "v2"
    result = loading.load(conn, "fixture", snap(tmp_path), dry_run=True)
    assert result["changed"] == 1
    assert rows(conn, "SELECT card ->> 'text' FROM cards WHERE source_id = '001'") == [("First card",)]
    assert rows(conn, "SELECT count(*) FROM datasets") == [(1,)] and rows(conn, "SELECT count(*) FROM card_revisions") == [(0,)]


def test_adopted_legacy_rows_get_a_revision_from_the_legacy_dataset(conn, tmp_path, adapter):
    (legacy,) = conn.execute(
        "INSERT INTO datasets (game_id, source_ref, card_count) VALUES ('fixture', 'legacy', 1) RETURNING id"
    ).fetchone()
    conn.execute(
        "INSERT INTO cards (game, source_id, title, card, added_in, changed_in)"
        " VALUES ('fixture', '001', 'Alpha', '{\"code\": \"001\", \"name\": \"Alpha\", \"text\": \"Old text\"}', %s, %s)",
        (legacy, legacy),
    )
    conn.commit()
    result = loading.load(conn, "fixture", snap(tmp_path))
    assert (result["added"], result["changed"]) == (1, 1)
    assert rows(conn, "SELECT card ->> 'text', valid_from, replaced_in FROM card_revisions") == [("Old text", legacy, result["dataset_id"])]


def test_a_failed_load_changes_nothing(conn, tmp_path, adapter, monkeypatch):
    directory = snap(tmp_path)
    monkeypatch.setattr(loading, "_relative", lambda d: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        loading.load(conn, "fixture", directory)
    for table in ("cards", "datasets", "card_revisions"):
        assert rows(conn, f"SELECT count(*) FROM {table}") == [(0,)]


def test_unknown_game_is_an_error(conn, tmp_path, adapter):
    with pytest.raises(loading.LoadError, match="no row in `games`"):
        loading.load(conn, "nope", snap(tmp_path))


def test_status_before_and_after_loading(conn, tmp_path, adapter):
    directory = snap(tmp_path)
    before = "\n".join(loading.status(conn, "fixture", tmp_path))
    assert "active dataset: none" in before and "differs from the database" in before and "no adapter" not in before
    loading.load(conn, "fixture", directory)
    after = "\n".join(loading.status(conn, "fixture", tmp_path))
    assert "ref v1, 2 cards" in after and "matches the database" in after


def test_status_reports_upstream_when_the_adapter_knows_it(conn, tmp_path, adapter, monkeypatch):
    loading.load(conn, "fixture", snap(tmp_path))
    monkeypatch.setattr(adapter, "latest_ref", lambda: "v1", raising=False)
    assert "v1, already fetched" in "\n".join(loading.status(conn, "fixture", tmp_path))
    monkeypatch.setattr(adapter, "latest_ref", lambda: "v9", raising=False)
    assert "v9, newer than the newest snapshot" in "\n".join(loading.status(conn, "fixture", tmp_path))


def test_status_for_an_unknown_game(conn, tmp_path):
    assert loading.status(conn, "nope", tmp_path) == ["nope: no row in `games`"]
