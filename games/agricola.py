import re

MAX_FIELD_NAME = 256
MAX_FIELD_VALUE = 1024
NO_TEXT = "*No English text for this card in the source.*"

# Icon tokens in card text: (singular, plural). Mass nouns have no plural.
TOKENS = {
    "FOOD": ("food", "food"),
    "WOOD": ("wood", "wood"),
    "CLAY": ("clay", "clay"),
    "REED": ("reed", "reed"),
    "STONE": ("stone", "stone"),
    "STOEN": ("stone", "stone"),
    "GRAIN": ("grain", "grain"),
    "VEGETABLE": ("vegetable", "vegetables"),
    "SHEEP": ("sheep", "sheep"),
    "PIG": ("wild boar", "wild boar"),
    "CATTLE": ("cattle", "cattle"),
    "HORSE": ("horse", "horses"),
    "FUEL": ("fuel", "fuel"),
    "SCORE": ("VP", "VP"),
    "BEGGING": ("begging card", "begging cards"),
    "STABLE": ("stable", "stables"),
    "FENCE": ("fence", "fences"),
    "FIELD": ("field", "fields"),
    "FOREST": ("forest", "forests"),
    "BAKE": ("baking", "baking"),
    "GRAIN_VEG_STACK": ("grain or vegetable", "grain or vegetables"),
    "ARROW": ("→", "→"),
    "ARROW-1X": ("→ (once)", "→ (once)"),
    "ARROW-2X": ("→ (up to twice)", "→ (up to twice)"),
}
TOKEN = re.compile(r"(?:(\d+) ?)?<([A-Z0-9_-]+)>")
# Between two conversions on one line ("<VEGETABLE> <ARROW> 2<FOOD> <PIG> <ARROW> 2<FOOD>"), upstream has only a space.
NEXT_CONVERSION = re.compile(r"(<[A-Z0-9_-]+>) *(?=\d*<(?!ARROW)[A-Z0-9_-]+> *<ARROW)")


def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def replace_token(match):
    count, name = match.group(1), match.group(2)
    singular, plural = TOKENS.get(name, (name.lower(), name.lower()))
    if count is None:
        return singular
    return count + " " + (singular if count == "1" else plural)


def text_line(line):
    """One line of card text as Discord markdown: icon tokens as words, `__x__` bold, `[x]` headings italic."""
    line = line.replace("*", "\\*")
    line = NEXT_CONVERSION.sub(r"\1, ", line)
    line = TOKEN.sub(replace_token, line)
    line = re.sub(r"__(.+?)__", r"**\1**", line)
    return re.sub(r"\[(.+?)\]", r"*\1*", line)


def card_text(card):
    lines = [text_line(line) for line in card.get("desc") or [] if line and line.strip()]
    return "\n".join(lines)


def resources(cost):
    """`{"wood": 1, "clay": 2}` as "1 wood, 2 clay"."""
    if not isinstance(cost, dict):
        return ""
    return ", ".join(str(n) + " " + resource for resource, n in cost.items() if n)


def cost_string(card):
    """The cost line; `costs` lists alternatives, `fee` is paid on top of any of them. Empty when the card is free."""
    options = [r for r in (resources(c) for c in card.get("costs") or []) if r]
    cost = " or ".join(options)
    if card.get("fee") and resources(card["fee"]):
        cost += " plus " + resources(card["fee"])
    if card.get("costText"):
        cost = (card["costText"] + " " + cost).strip()
    if card.get("conditionalCost") and resources(card["conditionalCost"]):
        cost += " (conditionally " + resources(card["conditionalCost"]) + ")"
    return cost


def points_string(card):
    vp = card.get("vp") or 0
    points = str(vp) + " VP" if vp else ""
    if card.get("extraVp"):
        points = points + " + bonus VP" if points else "Bonus VP"
    return points


def header(card):
    parts = [type_string(card.get("type"))]
    cost = cost_string(card)
    if cost:
        parts.append("Cost: " + cost)
    points = points_string(card)
    if points:
        parts.append(points)
    if card.get("prerequisite"):
        parts.append("Requires: " + card["prerequisite"])
    if card.get("players"):
        parts.append("Players: " + card["players"])
    if card.get("passing"):
        parts.append("Passing")
    return truncate(" • ".join(parts), MAX_FIELD_NAME)


def footer_string(card):
    numbering = card.get("numbering") or ""
    return deck_string(card.get("deck")) + (" • " + numbering if numbering else "")


def embed(card):
    embed = {}
    embed["title"] = card["name"]

    if card.get("image_url"):
        embed["thumbnail"] = card["image_url"]

    # Discord rejects an empty field value, so a card without text says so
    embed["fields"] = [{"name": header(card), "value": truncate(card_text(card) or NO_TEXT, MAX_FIELD_VALUE)}]
    embed["footer"] = {"text": footer_string(card)}
    embed["color"] = type_color(card.get("type"))

    return embed


def type_string(code):
    match code:
        case "minor":
            return "Minor Improvement"
        case "major":
            return "Major Improvement"
        case "occupation":
            return "Occupation"
        case None:
            return "Card"
        case s:
            return s


def type_color(code):
    match code:
        case "minor":
            return 0xD39926
        case "major":
            return 0x93433C
        case "occupation":
            return 0xDAD13B
        case _:
            return 0x404040


def deck_string(code):
    match code:
        case None:
            return "Base Game"
        case "M":
            return "Farmers of the Moor"
        case s:
            return "Deck " + s
