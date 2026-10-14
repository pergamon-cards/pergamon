# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Pergamon is a Discord bot (Rust, serenity + poise) that looks up trading/board game cards and posts them as embeds. Card data lives in Postgres; how a card is rendered is defined per game by a Python script in `games/` that the Rust binary runs through embedded CPython (pyo3).

## Commands

```bash
cargo build
cargo run                 # needs Postgres running and config/<env>.toml present
cargo fmt                 # rustfmt.toml: max_width 140, edition 2024
cargo clippy
```

There are no tests yet.

Loading card data (Netrunner): clone https://github.com/Null-Signal-Games/netrunner-cards-json into `data/netrunner/netrunner-cards-json`, then run the loader **from `data/netrunner/`** (it resolves the JSON dir from cwd; needs `psycopg`):

```bash
cd data/netrunner && python load_data.py
```

It creates the `cards` table if missing and replaces all rows for that game. DB connection values are hard-coded at the top of the script.

Note: README.md is stale — it mentions a sqlite DB and a `DISCORD_TOKEN` env var; the bot now uses Postgres and the settings system below.

## Configuration

`src/settings.rs` loads `config/{PERGAMON_RUN_ENV}.toml` (default `dev`), then overlays env vars prefixed `PERGAMON_` (e.g. `PERGAMON_TOKEN`). Keys: `token` (Discord bot token) and a `[database]` table (`host`, `port`, `username`, `password`, `database`, `max_connections`). Settings live in a global `OnceCell`; call `Settings::global()` only after `Settings::new_global()` in `main`.

`config/` contains secrets and is not currently gitignored — don't commit it.

Logging uses `tracing` with `RUST_LOG`-style filtering (default `pergamon=debug`).

## Architecture

Request flow:
1. A lookup is triggered either by the `/lookup <title>` slash/prefix command, or inline by any message containing `[[card name]]` (handled in `event_handler` in `src/main.rs` → `commands::lookup_inline`). Slash commands must be registered once via the `register` prefix command.
2. `src/commands/lookup.rs::run` queries `cards` with `title LIKE '<query>%'`. If multiple distinct titles match, it posts buttons and waits (3 min) for a component interaction to disambiguate.
3. The row's `game` column selects `games/{game}.py`; `src/py.rs::get_embed` reads the file **on every lookup** (so script edits take effect without recompiling), executes it with pyo3, and calls its `embed(card)` function with the card's JSONB converted to a Python dict.
4. The returned dict is depythonized into `PergamonEmbed` and converted to a serenity `CreateEmbed`.

**Game script contract** (`games/<game>.py`): define `embed(card: dict) -> dict` returning any of `title`, `description`, `url`, `thumbnail`, `image`, `color` (int), `footer` (`{"text": ..., "icon_url": ...}`). Only fields declared on `PergamonEmbed` in `src/py.rs` reach Discord — e.g. `games/netrunner.py` sets a `field` tuple that is currently silently dropped. To support a new embed property, add it to `PergamonEmbed` and its `From` impl.

**DB schema** (created by the loader): `cards(id identity PK, game TEXT, title TEXT, card JSONB)`. `card` is the raw upstream JSON for the card, so game scripts depend on the source dataset's field names (e.g. Netrunner's `type_code`, `faction_code`, `pack_code`).

## Legacy / in-transition code

The project recently migrated card scripts from Rune to Python and moved off Shuttle hosting:
- `src/scripting/` (Rune runtime + a `Regex` module exposed to Rune) and `games/*.rn` are unused; the Rune path in `lookup.rs` is commented out. The `rune` dependencies are still in Cargo.toml.
- `Shuttle.toml`, `.shuttle/`, and `Secrets.toml` are leftovers from Shuttle deployment; the Shuttle crates have been removed and `main` is a plain `#[tokio::main]`.
