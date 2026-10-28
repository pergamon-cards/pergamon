import json
import re

import pytest

from conftest import REPO_DIR, load_game

agricola = load_game("agricola")


# Discord's embed limits, mirroring the constants in src/py.rs.
MAX_TITLE = 256
MAX_FOOTER = 2048
MAX_FIELD_NAME = 256
MAX_FIELD_VALUE = 1024
MAX_TOTAL = 6000


# Helpers


@pytest.mark.parametrize(
    "line,expected",
    [
        ("you can buy exactly 2 <STONE> for 1 <FOOD>.", "you can buy exactly 2 stone for 1 food."),
        ("<GRAIN> <ARROW> 2<FOOD>", "grain → 2 food"),
        ("<VEGETABLE> <ARROW> 2<FOOD> <PIG> <ARROW> 2<FOOD>", "vegetable → 2 food, wild boar → 2 food"),
        ("<SHEEP> <ARROW> 2<FOOD><CATTLE> <ARROW> 3<FOOD>", "sheep → 2 food, cattle → 3 food"),
        ("2 <FOOD> <ARROW> 1 <GRAIN>; 4 <FOOD> <ARROW> 1 <VEGETABLE>", "2 food → 1 grain; 4 food → 1 vegetable"),
        ("1 <VEGETABLE> <ARROW> 2 <PIG>", "1 vegetable → 2 wild boar"),
        ("remove exactly 3 <STABLE>", "remove exactly 3 stables"),
        ("1<FUEL> <ARROW-1X> 2<SCORE>", "1 fuel → (once) 2 VP"),
        ("<GRAIN> <ARROW-2X> 4<FOOD>", "grain → (up to twice) 4 food"),
        ("<SCORE> per <FOREST>", "VP per forest"),
        ("1 <STOEN>", "1 stone"),
        ("1 <NEWTHING>", "1 newthing"),
        ("[Anytime]", "*Anytime*"),
        ("[__Bake Bread__ action:]", "***Bake Bread** action:*"),
        ("(*Occupations and Improvements)", "(\\*Occupations and Improvements)"),
    ],
)
def test_text_line(line, expected):
    assert agricola.text_line(line) == expected


def test_card_text_skips_empty_lines():
    assert agricola.card_text({"desc": ["[Anytime]", "", "<GRAIN> <ARROW> 2<FOOD>"]}) == "*Anytime*\ngrain → 2 food"
    assert agricola.card_text({"desc": [""]}) == ""
    assert agricola.card_text({}) == ""


@pytest.mark.parametrize(
    "fields,expected",
    [
        ({"costs": [[]]}, ""),
        ({"costs": [{"clay": 2}]}, "2 clay"),
        ({"costs": [{"clay": 3, "stone": 1}]}, "3 clay, 1 stone"),
        ({"costs": [{"clay": 2}, {"wood": 2}], "fee": {"reed": 1}}, "2 clay or 2 wood plus 1 reed"),
        ({"costs": [{"clay": 4}], "costText": "Return Fireplace or"}, "Return Fireplace or 4 clay"),
        ({"costs": [[]], "costText": "Return Fireplace"}, "Return Fireplace"),
        ({"costs": [{"grain": 1}], "conditionalCost": {"food": 1}}, "1 grain (conditionally 1 food)"),
        ({"costs": [[]], "fee": ""}, ""),
        ({}, ""),
    ],
)
def test_cost_string(fields, expected):
    assert agricola.cost_string(fields) == expected


@pytest.mark.parametrize(
    "fields,expected",
    [({"vp": 0}, ""), ({"vp": 2}, "2 VP"), ({"vp": -1}, "-1 VP"), ({"vp": 0, "extraVp": True}, "Bonus VP"), ({"vp": 5, "extraVp": True}, "5 VP + bonus VP")],
)
def test_points_string(fields, expected):
    assert agricola.points_string(fields) == expected


@pytest.mark.parametrize(
    "code,expected",
    [("minor", ("Minor Improvement", 0xD39926)), ("major", ("Major Improvement", 0x93433C)), ("occupation", ("Occupation", 0xDAD13B))],
)
def test_types(code, expected):
    assert (agricola.type_string(code), agricola.type_color(code)) == expected


def test_unknown_type():
    assert agricola.type_string("mystery") == "mystery"
    assert agricola.type_color("mystery") == 0x404040


@pytest.mark.parametrize("code,expected", [(None, "Base Game"), ("M", "Farmers of the Moor"), ("C", "Deck C")])
def test_deck_string(code, expected):
    assert agricola.deck_string(code) == expected


# Golden embeds, on real cards trimmed to the fields the script reads

CARDS = {
    "Major_Fireplace1": {"id": "Major_Fireplace1", "name": "Fireplace", "deck": None, "players": None, "desc": ["[Anytime]", "<VEGETABLE> <ARROW> 2<FOOD> <PIG> <ARROW> 2<FOOD>", "<SHEEP> <ARROW> 2<FOOD> <CATTLE> <ARROW> 3<FOOD>", "[__Bake Bread__ action:]", "<GRAIN> <ARROW> 2<FOOD>"], "vp": 1, "extraVp": False, "prerequisite": "", "costs": [{"clay": 2}], "conditionalCost": None, "costText": "", "fee": None, "type": "major", "numbering": "001"},
    "A31_DebtSecurity": {"id": "A31_DebtSecurity", "name": "Debt Security", "deck": "A", "players": None, "desc": ["During scoring, you get 1 bonus <SCORE> for each major improvement you have, up to the number of your unused farmyard spaces."], "vp": 0, "extraVp": True, "prerequisite": "", "costs": [{"food": 2}], "conditionalCost": None, "costText": "", "fee": None, "type": "minor", "numbering": "A031", "passing": False},
    "C143_StoneBuyer": {"id": "C143_StoneBuyer", "name": "Stone Buyer", "deck": "C", "players": "3+", "desc": ["When you play this card, you can immediately buy exactly 2 <STONE> for 1 <FOOD>. From the next round on, once per round, you can buy 1 <STONE> for 2 <FOOD>."], "vp": 0, "extraVp": False, "prerequisite": "", "costs": [[]], "conditionalCost": None, "costText": "", "fee": None, "type": "occupation", "numbering": "C143"},
    "C44_ChickenCoop": {"id": "C44_ChickenCoop", "name": "Chicken Coop", "deck": "C", "players": None, "desc": ["Place 1 <FOOD> on each of the next 8 round spaces. At the start of these rounds, you get the <FOOD>."], "vp": 1, "extraVp": False, "prerequisite": "", "costs": [{"clay": 2}, {"wood": 2}], "conditionalCost": None, "costText": "", "fee": {"reed": 1}, "type": "minor", "numbering": "C044", "passing": False},
    "M61_HayWagon": {"id": "M61_HayWagon", "name": "Hay Wagon", "deck": "M", "players": None, "desc": [""], "vp": 1, "extraVp": False, "prerequisite": "2 Horses", "costs": [{"wood": 2}], "conditionalCost": None, "costText": "", "fee": None, "type": "minor", "numbering": "M061"},
}  # fmt: skip

GOLDEN = {
    "Major_Fireplace1": (
        "Major Improvement • Cost: 2 clay • 1 VP",
        "*Anytime*\nvegetable → 2 food, wild boar → 2 food\nsheep → 2 food, cattle → 3 food\n***Bake Bread** action:*\ngrain → 2 food",
        "Base Game • 001",
        0x93433C,
    ),
    "A31_DebtSecurity": (
        "Minor Improvement • Cost: 2 food • Bonus VP",
        "During scoring, you get 1 bonus VP for each major improvement you have, up to the number of your unused farmyard spaces.",
        "Deck A • A031",
        0xD39926,
    ),
    "C143_StoneBuyer": (
        "Occupation • Players: 3+",
        "When you play this card, you can immediately buy exactly 2 stone for 1 food. From the next round on, once per round, you can buy 1 stone for 2 food.",
        "Deck C • C143",
        0xDAD13B,
    ),
    "C44_ChickenCoop": (
        "Minor Improvement • Cost: 2 clay or 2 wood plus 1 reed • 1 VP",
        "Place 1 food on each of the next 8 round spaces. At the start of these rounds, you get the food.",
        "Deck C • C044",
        0xD39926,
    ),
    "M61_HayWagon": (
        "Minor Improvement • Cost: 2 wood • 1 VP • Requires: 2 Horses",
        agricola.NO_TEXT,
        "Farmers of the Moor • M061",
        0xD39926,
    ),
}


@pytest.mark.parametrize("code", GOLDEN)
def test_embed_golden(code):
    card = CARDS[code]
    header, text, footer, color = GOLDEN[code]

    assert agricola.embed(card) == {
        "title": card["name"],
        "fields": [{"name": header, "value": text}],
        "footer": {"text": footer},
        "color": color,
    }


def test_passing_card_says_so():
    assert agricola.header({**CARDS["C44_ChickenCoop"], "passing": True}).endswith(" • Passing")


def test_long_card_text_is_truncated_to_the_field_limit():
    card = {**CARDS["C143_StoneBuyer"], "desc": ["x" * 2000]}
    value = agricola.embed(card)["fields"][0]["value"]
    assert len(value) == MAX_FIELD_VALUE
    assert value.endswith("…")


def test_card_with_an_image_url_has_a_thumbnail():
    card = {**CARDS["C143_StoneBuyer"], "image_url": "https://example.com/c143.jpg"}
    assert agricola.embed(card)["thumbnail"] == "https://example.com/c143.jpg"


# The keys the Rust side accepts, read from `PergamonEmbed` in src/py.rs


def rust_embed_keys():
    source = (REPO_DIR / "src/py.rs").read_text()
    body = re.search(r"pub struct PergamonEmbed \{(.*?)\n\}", source, re.S).group(1)
    return set(re.findall(r"^\s*pub (\w+):", body, re.M))


@pytest.mark.parametrize("code", GOLDEN)
def test_embed_keys_are_accepted_by_rust(code):
    assert set(agricola.embed(CARDS[code])) <= rust_embed_keys()


# Every card in the newest ingest snapshot (skipped when there is none)


def newest_snapshot_cards():
    """The cards of the newest `python -m ingest fetch agricola` snapshot, or [] when there is none (or polars is missing)."""
    try:
        import polars as pl

        from ingest import snapshot
    except ImportError:
        return []
    snapshots = snapshot.list_snapshots("agricola", REPO_DIR / "data")
    if not snapshots:
        return []
    return [json.loads(card) for card in pl.read_parquet(snapshots[-1] / "cards.parquet")["card"]]


DATASET = newest_snapshot_cards()

# Cards that fail today because of bugs in games/agricola.py (none at the moment). Listed so the suite stays green;
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
    marks = [pytest.mark.xfail(strict=True, reason=KNOWN_BAD[card["id"]])] if card["id"] in KNOWN_BAD else []
    return pytest.param(card, id=card["id"], marks=marks)


@pytest.mark.skipif(not DATASET, reason="no snapshot: run `python -m ingest fetch agricola`")
@pytest.mark.parametrize("card", [dataset_param(c) for c in DATASET])
def test_dataset_card_renders(card):
    out = agricola.embed(card)

    assert set(out) <= rust_embed_keys()
    assert isinstance(out["title"], str) and out["title"]
    assert isinstance(out["color"], int) and 0 <= out["color"] <= 0xFFFFFF
    assert isinstance(out["footer"]["text"], str) and out["footer"]["text"]
    assert not [s for s in strings(out) if re.search(r"\bNone\b|<[A-Z0-9_-]+>|__", s)]

    [field] = out["fields"]
    assert field["name"] and len(field["name"]) <= MAX_FIELD_NAME
    assert field["value"] and len(field["value"]) <= MAX_FIELD_VALUE

    title = len(out["title"])
    footer = len(out["footer"]["text"])
    assert title <= MAX_TITLE
    assert footer <= MAX_FOOTER
    assert title + footer + len(field["name"]) + len(field["value"]) <= MAX_TOTAL


def test_known_bad_cards_exist():
    if DATASET:
        assert set(KNOWN_BAD) <= {c["id"] for c in DATASET}
