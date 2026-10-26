-- Schema for versioned card datasets.
--
-- `cards` already exists in databases loaded by data/netrunner/load_data.py, so it is created only if missing and its
-- existing rows are adopted: each game found in it gets a `games` row and a `legacy` dataset, and every card is backfilled
-- before the constraints are added. Nothing is dropped.

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    game TEXT,
    title TEXT,
    card JSONB
);

-- One row per game. `active_dataset_id` points at the dataset the current `cards` rows came from.
CREATE TABLE games (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    active_dataset_id INTEGER
);

-- One row per load that changed something. `source_ref` is the upstream version (commit SHA, ETag, API version).
CREATE TABLE datasets (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    game_id TEXT NOT NULL REFERENCES games (id),
    source_ref TEXT,
    fetched_at TIMESTAMPTZ,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    snapshot_path TEXT,
    content_hash TEXT,
    card_count INTEGER NOT NULL,
    added INTEGER NOT NULL DEFAULT 0,
    changed INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE games ADD FOREIGN KEY (active_dataset_id) REFERENCES datasets (id);

-- Adopt existing rows.
INSERT INTO games (id, name, source)
SELECT DISTINCT game, game, 'legacy' FROM cards WHERE game IS NOT NULL;

INSERT INTO datasets (game_id, source_ref, card_count)
SELECT game, 'legacy', count(*) FROM cards WHERE game IS NOT NULL GROUP BY game;

UPDATE games SET active_dataset_id = d.id FROM datasets d WHERE d.game_id = games.id AND d.source_ref = 'legacy';

ALTER TABLE cards
    ADD COLUMN source_id TEXT,
    ADD COLUMN added_in INTEGER REFERENCES datasets (id),
    ADD COLUMN changed_in INTEGER REFERENCES datasets (id);

-- `code` is the upstream id for Netrunner; fall back to the row id when it is missing or not unique within the game.
WITH ids AS (
    SELECT id, CASE WHEN count(*) OVER (PARTITION BY game, card ->> 'code') = 1 THEN card ->> 'code' END AS code FROM cards
)
UPDATE cards SET
    source_id = coalesce(ids.code, cards.id::text),
    added_in = g.active_dataset_id,
    changed_in = g.active_dataset_id
FROM ids, games g
WHERE ids.id = cards.id AND g.id = cards.game;

ALTER TABLE cards
    ALTER COLUMN game SET NOT NULL,
    ALTER COLUMN title SET NOT NULL,
    ALTER COLUMN card SET NOT NULL,
    ALTER COLUMN source_id SET NOT NULL,
    ALTER COLUMN added_in SET NOT NULL,
    ALTER COLUMN changed_in SET NOT NULL,
    ADD FOREIGN KEY (game) REFERENCES games (id),
    ADD UNIQUE (game, source_id);

-- Superseded or removed versions of a card; unchanged cards are never copied here.
CREATE TABLE card_revisions (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    game TEXT NOT NULL REFERENCES games (id),
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    card JSONB NOT NULL,
    valid_from INTEGER NOT NULL REFERENCES datasets (id),
    replaced_in INTEGER NOT NULL REFERENCES datasets (id),
    removed BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX card_revisions_card_idx ON card_revisions (game, source_id);
