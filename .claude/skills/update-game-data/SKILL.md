---
name: update-game-data
description: Update a game's card data in the database from its source (new expansions, corrections). Use when the user asks to refresh, update or reload a game's cards, or to check whether the data is current. Shows the difference and asks before loading.
---

# Update game data

Updates are light: new sets and corrections. The loader writes only what changed, and keeps superseded versions in `card_revisions`, so an update never duplicates unchanged cards. Commands are in CLAUDE.md (Ingest). The schema must exist first (the bot has run once).

## Steps

1. **Status:** `python -m ingest status <game>`. It shows the active dataset, the newest local snapshot and whether it differs from the database, and the upstream ref when the adapter has `latest_ref()`.
   - If a local snapshot already differs from the database, skip to step 3 with it (`--snapshot`) instead of fetching again, unless the user wants fresh data.
   - If the upstream ref equals the one already loaded, say the data is current and stop.
2. **Fetch:** `python -m ingest fetch <game>`. "upstream unchanged" means the cards are identical to the newest snapshot: say so and stop. Raw data is zipped to `raw.zip` after use; pass `--keep-raw` only when debugging an adapter.
3. **Dry run:** `python -m ingest load <game> --dry-run`. Show the counts (added, changed, removed, unchanged) and the sample of changed cards with their changed keys.
   - A large unexpected number of changes or removals usually means the source changed shape. Do not load; go to "If the source changed shape".
4. **Ask** before loading, summarising what changes. Then `python -m ingest load <game>` and `python -m ingest status <game>` to confirm the new dataset is active. Loading is one transaction, and a load that changes nothing writes nothing.
5. **Embeds:** if the changes include new fields or card types, run `python -m pytest games`. Cards that the embed script cannot render show up in its corpus test; hand off to the `add-embed-script` skill to fix the script.

## If the source changed shape

- **Fetch fails in the transform or validation:** the failed attempt leaves no snapshot behind. Fix `ingest/sources/<game>.py` (and its test), then fetch again.
- **A snapshot exists but its cards are wrong** (a bug noticed later): fix the adapter, then `python -m ingest transform <game> --snapshot <dir>` re-runs the transform from the archived `raw.zip` without downloading and rewrites `cards.parquet`. Dry-run and load as above.
- Run `python -m pytest ingest games` after any adapter change.
- An adapter fix is a code change: follow the `issue` skill for it.

## Notes

- Never change loaded data by hand in the database; every change goes through a snapshot so it is recorded in `datasets`.
- Snapshots are local and gitignored. If one is missing, fetch again; the database keeps the provenance (`datasets.source_ref`, `content_hash`).
- Rollback to an older dataset has no command yet; the history is in `card_revisions`.
