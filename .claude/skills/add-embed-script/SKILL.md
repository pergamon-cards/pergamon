---
name: add-embed-script
description: Write or change a game's embed script (games/<id>.py) and its tests, so cards render in Discord. Use after add-game loads a game's data, when the user wants cards of a game displayed differently, or when a card fails to render.
---

# Add embed script

`games/<id>.py` defines `embed(card: dict) -> dict`, run by the bot through embedded CPython on every lookup (script edits take effect without recompiling). `card` is the `card` JSON from the database: the adapter's transformed record, including `image_url`. See CLAUDE.md, "Game script contract".

## Steps

1. **Know the cards.** Open the newest snapshot (`data/<id>/snapshots/*/cards.parquet`, via polars) and look at the field names across card types, which fields are sometimes missing or null, and the longest texts. Read `games/netrunner.py` as the example (and its `KNOWN_BAD` list in `games/tests/test_netrunner.py` for the kinds of bugs to avoid: a null cost printed as `None`, a missing `text`).
2. **Check what the Rust side accepts.** Only fields declared on `PergamonEmbed` in `src/py.rs` reach Discord: `color`, `description`, `fields`, `footer`, `image`, `thumbnail`, `title`, `url`. If the design needs something else (for example `author`), **stop**: tell the user, and propose the `src/py.rs` change as its own issue or sub-issue (it applies to every game). Don't set keys the Rust side drops.
3. **Settle the design with the user** if it is not obvious: what goes in the title, description and footer, the colour scheme, how rich text and symbols are rendered.
4. **Write `games/<id>.py`.**
   - Use `.get()` for fields that can be missing, and never let `None` reach a string.
   - Set `thumbnail` from `card["image_url"]` only when present.
   - Respect Discord's limits (title 256, description 4096, footer 2048, 6000 in total, the constants in `src/py.rs`); truncate with `…` rather than fail.
   - No `print`s, no network or file access: the script runs in the bot's process.
5. **Write `games/tests/test_<id>.py`**, following `games/tests/test_netrunner.py`:
   - load the script with `load_game("<id>")` (add a session fixture to `games/tests/conftest.py` if the other tests use that pattern);
   - unit tests for each helper, and golden embeds for a few real cards of each type (trim the card to the fields the script reads);
   - a corpus test over the newest snapshot that renders every card and checks the keys, the types and the length limits. It skips when there is no snapshot. Cards that fail because of script bugs go in a `KNOWN_BAD` dict as strict `xfail` with a reason, so fixing one makes pytest fail until it is removed from the list. Fix bugs rather than list them when you can;
   - a test that the keys returned are accepted by the Rust side (read the struct as `test_netrunner.py` does).
6. **Check:** `python -m pytest games` (and `cargo test` if `src/py.rs` changed, with `cargo fmt` and `cargo clippy --all-targets`). Break the script on purpose once to confirm a test fails.
7. **Report** with a rendered example (the dict for one card of each type) and say plainly that the user needs to look at it in Discord (`[[card name]]` in a channel with the bot, or `/lookup`), since the tests cannot show how it looks.
