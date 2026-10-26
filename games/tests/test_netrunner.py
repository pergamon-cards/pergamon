import json
import re

import pytest

from conftest import REPO_DIR, load_game

netrunner = load_game("netrunner")


# Discord's embed limits, mirroring the constants in src/py.rs.
MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FOOTER = 2048
MAX_TOTAL = 6000

FACTIONS = {
    "anarch": ("Anarch", 0xFF4500),
    "criminal": ("Criminal", 0x4169E1),
    "shaper": ("Shaper", 0x32CD32),
    "nbn": ("NBN", 0xFF8C00),
    "neutral-corp": ("Neutral (Corp)", 0x808080),
    "neutral-runner": ("Neutral (Runner)", 0x808080),
    "jinteki": ("Jinteki", 0xDC143C),
    "weyland-consortium": ("Weyland Consortium", 0x006400),
    "haas-bioroid": ("Haas-Bioroid", 0x8A2BE2),
}

TYPES = {
    code: code.capitalize()
    for code in ["agenda", "asset", "event", "hardware", "ice", "identity", "operation", "program", "resource", "upgrade"]
}


# Helpers


@pytest.mark.parametrize("n", range(6))
def test_influence_string(n):
    assert netrunner.influence_string(n) == "●" * n


@pytest.mark.parametrize("code,expected", [(c, v[0]) for c, v in FACTIONS.items()])
def test_faction_string(code, expected):
    assert netrunner.faction_string(code) == expected


@pytest.mark.parametrize("code,expected", [(c, v[1]) for c, v in FACTIONS.items()])
def test_faction_color(code, expected):
    assert netrunner.faction_color(code) == expected


def test_unknown_faction():
    assert netrunner.faction_string("mystery") == "mystery"
    assert netrunner.faction_color("mystery") == 0x404040


@pytest.mark.parametrize("code,expected", TYPES.items())
def test_type_string(code, expected):
    assert netrunner.type_string(code) == expected


def test_unknown_type():
    assert netrunner.type_string("mystery") == "mystery"


def test_pack_string():
    assert netrunner.pack_string("core") == "Core Set"
    assert netrunner.pack_string("fp") == "Genesis (Future Proof)"


def test_unknown_pack():
    assert netrunner.pack_string("nope") == "nope"


# Header builders, on hand-written cards


def test_agenda_header():
    card = {"type_code": "agenda", "advancement_cost": 3, "agenda_points": 2}
    assert netrunner.agenda_header(card) == "Agenda • 3/2"
    assert netrunner.agenda_header({**card, "keywords": "Security"}) == "Agenda: Security • 3/2"


def test_ice_header():
    card = {"type_code": "ice", "cost": 4, "strength": 3, "faction_cost": 0}
    assert netrunner.ice_header(card) == "Ice • Rez: 4 • Strength: 3"
    assert netrunner.ice_header({**card, "keywords": "Barrier"}) == "Ice: Barrier • Rez: 4 • Strength: 3"
    assert netrunner.ice_header({**card, "trash_cost": 2}).endswith(" • Trash: 2")
    assert netrunner.ice_header({**card, "faction_cost": 2}).endswith(" • Influence: ●●")


def test_ice_header_null_strength():
    card = {"type_code": "ice", "cost": 4, "strength": None, "faction_cost": 0}
    assert netrunner.ice_header(card) == "Ice • Rez: 4 • Strength: X"


def test_identity_header():
    card = {"type_code": "identity", "minimum_deck_size": 45, "influence_limit": 15}
    assert netrunner.identity_header(card) == "Identity • 45/15"
    assert netrunner.identity_header({**card, "base_link": 2}) == "Identity • 45/15 • Link: 2"
    assert netrunner.identity_header({**card, "keywords": "Megacorp"}).startswith("Identity: Megacorp")


def test_identity_header_null_influence_limit():
    card = {"type_code": "identity", "minimum_deck_size": 45, "influence_limit": None}
    assert netrunner.identity_header(card) == "Identity • 45/\u221e"


def test_card_header():
    card = {"type_code": "event", "cost": 2, "faction_cost": 0}
    assert netrunner.card_header(card) == "Event • Cost: 2"
    assert netrunner.card_header({**card, "faction_cost": 3}) == "Event • Cost: 2 • Influence: ●●●"
    assert netrunner.card_header({**card, "trash_cost": 1}) == "Event • Cost: 2 • Trash: 1"


def test_card_header_x_cost():
    card = {"type_code": "operation", "cost": None, "faction_cost": 0}
    assert netrunner.card_header(card) == "Operation \u2022 Cost: X"


def test_agenda_header_null_advancement_cost():
    card = {"type_code": "agenda", "advancement_cost": None, "agenda_points": 1}
    assert netrunner.agenda_header(card) == "Agenda \u2022 X/1"


def test_headers_without_faction_cost():
    assert netrunner.ice_header({"type_code": "ice", "cost": 1, "strength": 1}) == "Ice \u2022 Rez: 1 \u2022 Strength: 1"
    assert netrunner.card_header({"type_code": "event", "cost": 1}) == "Event \u2022 Cost: 1"


@pytest.mark.parametrize("text", [{}, {"text": None}, {"text": ""}])
def test_card_without_text_has_no_field(text):
    card = {**{k: v for k, v in CARDS["01050"].items() if k != "text"}, **text}
    out = netrunner.embed(card)
    assert "fields" not in out
    assert out["title"] == "Sure Gamble"


# embed(), compared with real cards trimmed to the fields the script reads

CARDS = {
    "01001": {"code": "01001", "title": "Noise: Hacker Extraordinaire", "type_code": "identity", "faction_code": "anarch", "pack_code": "core", "position": 1, "text": "Whenever you install a <strong>virus</strong> program, the Corp trashes the top card of R&D.", "keywords": "G-mod", "minimum_deck_size": 45, "influence_limit": 15, "base_link": 0},
    "01003": {"code": "01003", "title": "Demolition Run", "type_code": "event", "faction_code": "anarch", "pack_code": "core", "position": 3, "text": "Run HQ or R&D.\nAccess → <strong>0[credit]:</strong> Trash the card you are accessing.", "keywords": "Run - Sabotage", "cost": 2, "faction_cost": 2},
    "01007": {"code": "01007", "title": "Corroder", "type_code": "program", "faction_code": "anarch", "pack_code": "core", "position": 7, "text": "Interface → <strong>1[credit]:</strong> Break 1 <strong>barrier</strong> subroutine.\n<strong>1[credit]:</strong> +1 strength.", "keywords": "Icebreaker - Fracter", "cost": 2, "strength": 2, "faction_cost": 2},
    "01016": {"code": "01016", "title": "Wyldside", "type_code": "resource", "faction_code": "anarch", "pack_code": "core", "position": 16, "text": "When your turn begins, draw 2 cards and lose [click].", "keywords": "Location - Seedy", "cost": 3, "faction_cost": 3},
    "01050": {"code": "01050", "title": "Sure Gamble", "type_code": "event", "faction_code": "neutral-runner", "pack_code": "core", "position": 50, "text": "Gain 9[credit].", "cost": 5, "faction_cost": 0},
    "01080": {"code": "01080", "title": "NBN: Making News", "type_code": "identity", "faction_code": "nbn", "pack_code": "core", "position": 80, "text": "2[recurring-credit]\nUse these credits during trace attempts.", "keywords": "Megacorp", "minimum_deck_size": 45, "influence_limit": 15},
    "01101": {"code": "01101", "title": "Archer", "type_code": "ice", "faction_code": "weyland-consortium", "pack_code": "core", "position": 101, "text": "As an additional cost to rez this ice, forfeit 1 agenda.\n[subroutine] Gain 2[credit].\n[subroutine] Trash 1 installed program.\n[subroutine] Trash 1 installed program.\n[subroutine] End the run.", "keywords": "Sentry - Destroyer", "cost": 4, "strength": 6, "faction_cost": 2},
    "01082": {"code": "01082", "title": "Breaking News", "type_code": "agenda", "faction_code": "nbn", "pack_code": "core", "position": 82, "text": "When you score this agenda, give the Runner 2 tags.\nWhen a discard phase ends, if you scored this agenda this turn, the Runner removes 2 tags.", "advancement_cost": 2, "agenda_points": 1},
    "01092": {"code": "01092", "title": "SanSan City Grid", "type_code": "upgrade", "faction_code": "nbn", "pack_code": "core", "position": 92, "text": "Each agenda in the root of this server gets −1 advancement requirement.\nLimit 1 <strong>region</strong> per server.", "keywords": "Region", "cost": 6, "trash_cost": 5, "faction_cost": 3},
}  # fmt: skip

for _code, _card in CARDS.items():
    _card["image_url"] = f"https://card-images.netrunnerdb.com/v2/large/{_code}.jpg"

GOLDEN = {
    "01001": ("Identity: G-mod • 45/15 • Link: 0", "Anarch • Core Set #1", 0xFF4500),
    "01003": ("Event: Run - Sabotage • Cost: 2 • Influence: ●●", "Anarch • Core Set #3", 0xFF4500),
    "01007": ("Program: Icebreaker - Fracter • Cost: 2 • Influence: ●●", "Anarch • Core Set #7", 0xFF4500),
    "01016": ("Resource: Location - Seedy • Cost: 3 • Influence: ●●●", "Anarch • Core Set #16", 0xFF4500),
    "01050": ("Event • Cost: 5", "Neutral (Runner) • Core Set #50", 0x808080),
    "01080": ("Identity: Megacorp • 45/15", "NBN • Core Set #80", 0xFF8C00),
    "01101": ("Ice: Sentry - Destroyer • Rez: 4 • Strength: 6 • Influence: ●●", "Weyland Consortium • Core Set #101", 0x006400),
    "01082": ("Agenda • 2/1", "NBN • Core Set #82", 0xFF8C00),
    "01092": ("Upgrade: Region • Cost: 6 • Trash: 5 • Influence: ●●●", "NBN • Core Set #92", 0xFF8C00),
}  # fmt: skip


@pytest.mark.parametrize("code", GOLDEN)
def test_embed_golden(code):
    card = CARDS[code]
    header, footer, color = GOLDEN[code]

    assert netrunner.embed(card) == {
        "title": card["title"],
        "url": f"https://netrunnerdb.com/en/card/{code}",
        "thumbnail": f"https://card-images.netrunnerdb.com/v2/large/{code}.jpg",
        "fields": [{"name": header, "value": card["text"]}],
        "footer": {"text": footer},
        "color": color,
    }


def test_long_card_text_is_truncated_to_the_field_limit():
    card = {**CARDS["01050"], "text": "x" * 2000}
    value = netrunner.embed(card)["fields"][0]["value"]
    assert len(value) == 1024
    assert value.endswith("\u2026")


def test_card_without_an_image_url_has_no_thumbnail():
    card = {k: v for k, v in CARDS["01050"].items() if k != "image_url"}
    assert "thumbnail" not in netrunner.embed(card)


# The keys the Rust side accepts, read from `PergamonEmbed` in src/py.rs


def rust_embed_keys():
    source = (REPO_DIR / "src/py.rs").read_text()
    body = re.search(r"pub struct PergamonEmbed \{(.*?)\n\}", source, re.S).group(1)
    return set(re.findall(r"^\s*pub (\w+):", body, re.M))


def test_rust_embed_keys_are_read():
    assert {"title", "url", "thumbnail", "footer", "color"} <= rust_embed_keys()


@pytest.mark.parametrize("code", GOLDEN)
def test_embed_keys_are_accepted_by_rust(code):
    assert set(netrunner.embed(CARDS[code])) <= rust_embed_keys()


# Every card in the newest ingest snapshot (skipped when there is none)

def newest_snapshot_cards():
    """The cards of the newest `python -m ingest fetch netrunner` snapshot, or [] when there is none (or polars is missing)."""
    try:
        import polars as pl

        from ingest import snapshot
    except ImportError:
        return []
    snapshots = snapshot.list_snapshots("netrunner", REPO_DIR / "data")
    if not snapshots:
        return []
    return [json.loads(card) for card in pl.read_parquet(snapshots[-1] / "cards.parquet")["card"]]


DATASET = newest_snapshot_cards()

# Cards that fail today because of bugs in games/netrunner.py (none at the moment). Listed so the suite stays green;
# strict xfail turns a fixed card into a failure that reminds us to remove it from here.
KNOWN_BAD = {}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from strings(v)


def dataset_param(card):
    marks = [pytest.mark.xfail(strict=True, reason=KNOWN_BAD[card["code"]])] if card["code"] in KNOWN_BAD else []
    return pytest.param(card, id=card["code"], marks=marks)


@pytest.mark.skipif(not DATASET, reason="no snapshot: run `python -m ingest fetch netrunner`")
@pytest.mark.parametrize("card", [dataset_param(c) for c in DATASET])
def test_dataset_card_renders(card):
    out = netrunner.embed(card)

    assert isinstance(out["title"], str) and out["title"]
    assert isinstance(out["color"], int) and 0 <= out["color"] <= 0xFFFFFF
    assert isinstance(out["footer"]["text"], str) and out["footer"]["text"]
    assert not [s for s in strings(out) if re.search(r"\bNone\b", s)]

    title = len(out["title"])
    description = len(out.get("description", ""))
    footer = len(out["footer"]["text"])
    assert title <= MAX_TITLE
    assert description <= MAX_DESCRIPTION
    assert footer <= MAX_FOOTER
    assert title + description + footer <= MAX_TOTAL


def test_known_bad_cards_exist():
    if DATASET:
        assert set(KNOWN_BAD) <= {c["code"] for c in DATASET}
