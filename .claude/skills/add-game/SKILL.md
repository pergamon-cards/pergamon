---
name: add-game
description: Bring a new game's card data into pergamon, from finding a source to a working embed. Use when the user wants to add a game or card set ("add Agricola", "support <game>"), or asks where card data for a game could come from. Stops for the user's decisions on the source and the game id.
---

# Add game

Five steps, each ending in a **stop** where the choice is the user's: find the source, set up the game, fetch and transform, load, write the embed. The pipeline is the `ingest/` package (see CLAUDE.md); this skill is the process around it.

Adding a game is code and schema changes, so it is an `issue` flow (one commit), or a `tracking-issue` if it splits (for example a large adapter plus an embed script). Follow that skill's rules for the plan, branch, commit and PR; the steps below are the plan's content. Nothing here is committed unless that flow says so.

Never download images, and never bulk-scrape a site that forbids it: check the terms first.

## 1. Find the source

Read [references/source-research.md](references/source-research.md) and research the game with it. For each candidate source report, in a table: format, coverage (sets, languages, errata), update cadence, whether each card has a stable id, who hosts the card images, licence and terms of use, and the fetch method.

**Stop** and ask the user which source to use, with the trade-offs and your recommendation. If no candidate gives stable ids, usable terms and card text, say so and stop there instead of settling for a scrape that would break.

## 2. Set up the game

1. **Propose a short id** (3 to 5 lowercase letters, such as `agri`) and confirm it with the user. It must not clash with an existing `games.id`, a file in `games/`, or the existing `netrunner`. It becomes `games.id`, `cards.game`, `games/<id>.py` and `ingest/sources/<id>.py`.
2. **Settle with the user:**
   - `source_id`: the stable upstream id. If the source has none, say what you would derive and why it stays stable across updates;
   - duplicate titles (reprints, different versions): the default is one row per printing with its own `source_id`; lookup shows the oldest row.
3. **Migration:** use the `add-migration` skill to insert the `games` row (`id`, `name`, `source` URL), following `migrations/*_netrunner_game.sql`.
4. **Adapter** `ingest/sources/<id>.py`, to the interface in `ingest/sources/__init__.py` (`SOURCE`, `fetch`, `transform`, optionally `latest_ref`).
   - Put `image_url` in each card's JSON when an image exists; prefer a publisher or long-lived CDN URL (never store the image).
   - Keep upstream field names where they are sensible.
   - Add tests like `ingest/tests/test_netrunner_adapter.py`, using a tiny fixture and no network.

## 3. Fetch

Run `python -m ingest fetch <id>`. Show the card count, five sample rows (`source_id`, `title`, and the card JSON), and whether the image check passed. If validation fails, fix the adapter and fetch again (a failed fetch leaves no snapshot behind). **Stop** if the data looks wrong.

## 4. Load

Run `python -m ingest load <id> --dry-run` and show the counts. Loading writes to the dev database, so ask before the real `load`, then run `load` and `python -m ingest status <id>`. The schema must exist first (start the bot once so its migrations have run).

Lookup searches every game's titles together, so a new game's cards appear in every lookup until lookup is scoped per game. Tell the user.

## 5. Embed

Hand off to the `add-embed-script` skill.

## Finish

- CLAUDE.md: add anything specific to the game (for example a source quirk) only if it will matter later.
- Report what was added, what was checked, and what was not (the user checks the embed in Discord).
