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

Tests:

```bash
cargo test                                    # Rust unit tests (#[cfg(test)] modules in py.rs, lookup.rs, settings.rs)
pip install -r games/requirements-dev.txt     # once, ideally in a venv
python -m pytest games                        # game script tests in games/tests/
pip install -r ingest/requirements.txt        # once, for the ingest package
python -m pytest ingest                       # ingest tests in ingest/tests/ (no database or network needed)
```

The pytest suite also renders every card in `data/netrunner/netrunner-cards-json` (skipped if it is not cloned). Cards that fail today because of bugs in `games/netrunner.py` are listed in `KNOWN_BAD` as strict `xfail`; when you fix one, pytest fails until you remove it from the list. `render_embed` registers each script in `sys.modules` by name, so Rust tests that call it use a distinct module name each.

Loading card data (Netrunner): clone https://github.com/Null-Signal-Games/netrunner-cards-json into `data/netrunner/netrunner-cards-json`, then run the loader **from `data/netrunner/`** (it resolves the JSON dir from cwd; needs `psycopg`):

```bash
cd data/netrunner && python load_data.py
```

It replaces all rows for that game and does not create tables: run the bot once first so the migrations have created them. DB connection values are hard-coded at the top of the script.

Ingest (card data pipeline, in progress under tracking issue #42): `python -m ingest fetch <game> [--keep-raw] [--skip-image-check]` runs the adapter `ingest/sources/<game>.py`, validates the result and writes `data/<game>/snapshots/<YYYY-MM-DD>/{cards.parquet,meta.json,raw.zip}` (a second snapshot the same day gets a `-2` suffix; `data/` is gitignored, so snapshots stay local). The raw download is zipped after use unless `--keep-raw` is given. A fetch whose content hash equals the newest snapshot's is discarded as "upstream unchanged". `python -m ingest transform <game> --snapshot <dir>` re-runs the transform from the archived raw data after an adapter fix. The snapshot's columns are `source_id`, `title` and `card` (a JSON object string that includes `image_url`; images are never stored); `ingest/validate.py` enforces this. `ingest/db.py` reads the DB settings from `config/<env>.toml` for the upcoming `load` command. No game has an adapter yet.

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

**DB schema** (owned by `migrations/`, applied by `sqlx::migrate!()` in `src/lib.rs` at startup; see the `add-migration` skill):
- `games(id PK, name, source, active_dataset_id)`: one row per game; `id` is the short id used in `cards.game` and `games/<id>.py`.
- `datasets(id, game_id, source_ref, fetched_at, loaded_at, snapshot_path, content_hash, card_count, added, changed, removed)`: one row per load that changed something. Rows adopted from before versioning belong to a `legacy` dataset.
- `cards(id, game, source_id, title, card JSONB, added_in, changed_in)`: the current version of each card only, `UNIQUE(game, source_id)`. `card` is the upstream JSON for the card (for Netrunner, the raw record), so game scripts depend on the source dataset's field names (e.g. Netrunner's `type_code`, `faction_code`, `pack_code`).
- `card_revisions(id, game, source_id, title, card, valid_from, replaced_in, removed)`: superseded or removed versions only, so unchanged cards are never copied. Nothing writes to it until the ingest `load` step lands.

The Netrunner loader (`data/netrunner/load_data.py`) predates this schema and will fail against it (it does not set `source_id`, `added_in` or `changed_in`); it is replaced by the ingest pipeline (tracking issue #42), so don't use it to reload data until then.

## Legacy / in-transition code

The project recently migrated card scripts from Rune to Python:
- `src/scripting/` (Rune runtime + a `Regex` module exposed to Rune) and `games/*.rn` are unused; the Rune path in `lookup.rs` is commented out. The `rune` dependencies are still in Cargo.toml.

## Conventions and workflow

- Project skills live in `.claude/skills/`:
  - `add-migration`: adds a sqlx migration for a schema change and tests it on a throwaway database
  - `commit`: runs checks and commits in the repo's message style
  - `issue`: plans a single (non-tracking) issue for approval, then implements it on its own branch and draft PR, addresses feedback with fixup commits, and on approval squashes them and marks the PR ready
  - `tracking-issue`: drafts a tracking issue for approval when none exists, plans it into sub-issues, then works through them one at a time on one branch and PR (draft, plan, step, approve, fixups, before merging)
- Work that splits into two or more logically related issues always goes through `tracking-issue`, never several standalone `issue` flows. If no tracking issue exists yet, draft one with its Draft mode; this applies when Claude is the one proposing the split too.
- Before committing, run `cargo fmt`, `cargo clippy --all-targets` and `cargo test` for Rust changes. For changes to `games/*.py`, also run `python -m pytest games`, and `python -m pytest ingest` for changes to `ingest/`. Fix every clippy warning or error, and ask the user about any that need a decision, and `deno task build`, `deno task lint`, `deno task test` and `deno task fmt:check` for frontend changes. Don't run the `#[ignore]`d live tests.
- Rust modules with submodules use the `mod.rs` layout: `foo/mod.rs` plus `foo/bar.rs`, never `foo.rs` next to a `foo/` directory. A module without submodules stays a single `foo.rs`; when it gains its first submodule, move it to `foo/mod.rs` (with `git mv`).
- Commit messages are one lowercase line, past tense, no prefix, ending with the number of the issue the commit works on in parentheses (for example "added user timeline endpoint and frontend types (#42)"). In a tracking issue's flow that is the sub-issue, not the tracking issue or the PR. Merge commits are exempt. If no issue is known, ask the user for one; never omit it or use the PR number. The attribution trailer stays last in the body.
- `.env` and `*.db` are gitignored. `Cargo.lock` and `deno.lock` are committed.
