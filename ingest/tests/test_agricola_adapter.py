import json

from ingest.sources import agricola, load_adapter


def card(id, name, numbering, **fields):
    return {"id": id, "name": name, "numbering": numbering, "deck": None, "type": "minor", "desc": [], "costs": [[]], **fields}


CARDS = {
    "Major_Fireplace1": card("Major_Fireplace1", "Fireplace", "001", type="major", costs=[{"clay": 2}]),
    "Major_Fireplace2": card("Major_Fireplace2", "Fireplace", "002", type="major", costs=[{"clay": 3}]),
    "M3_Cookhouse1": card("M3_Cookhouse1", "Cookhouse", "M003", deck="M", type="major"),
    "M4_Cookhouse2": card("M4_Cookhouse2", "Cookhouse", "M004", deck="M", type="major"),
    "B8_MarketStall": card("B8_MarketStall", "Market Stall", "B8", deck="B", desc=["You immediately get 1 <VEGETABLE>."]),
    "C54_MarketStall": card("C54_MarketStall", "Market Stall", "C54", deck="C", desc=["After the field phase ..."]),
    "M61_HayWagon": card("M61_HayWagon", "Hay Wagon", "M61", deck="M", desc=[""]),
}


def transformed(tmp_path):
    (tmp_path / "cards.json").write_text(json.dumps(CARDS))
    return agricola.transform(tmp_path)


def test_the_adapter_follows_the_interface():
    adapter = load_adapter("agricola")
    assert adapter.SOURCE["url"].endswith("agricola-card-gallery") and callable(adapter.latest_ref)


def test_transform_keeps_records_and_drops_identical_copies(tmp_path):
    df = transformed(tmp_path)
    assert df["source_id"].to_list() == [
        "Major_Fireplace1",
        "Major_Fireplace2",
        "M3_Cookhouse1",
        "B8_MarketStall",
        "C54_MarketStall",
        "M61_HayWagon",
    ]
    assert df["title"].to_list() == ["Fireplace", "Fireplace", "Cookhouse", "Market Stall", "Market Stall", "Hay Wagon"]
    assert [json.loads(c) for c in df["card"]] == [v for k, v in CARDS.items() if k != "M4_Cookhouse2"]


def test_transform_adds_no_image_url(tmp_path):
    assert all("image_url" not in json.loads(c) for c in transformed(tmp_path)["card"])


def test_fetch_downloads_cards_json_at_the_latest_commit(tmp_path, monkeypatch):
    urls = []

    class Response:
        content = b"{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {"sha": "abc123"}

    monkeypatch.setattr(agricola.httpx, "get", lambda url, **kwargs: urls.append(url) or Response())
    assert agricola.fetch(tmp_path / "raw") == "abc123"
    assert urls == [
        "https://api.github.com/repos/klingeling/agricola-card-gallery/commits/HEAD",
        "https://raw.githubusercontent.com/klingeling/agricola-card-gallery/abc123/cards.json",
    ]
    assert (tmp_path / "raw" / "cards.json").read_bytes() == b"{}"
