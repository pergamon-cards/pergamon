-- The Agricola `games` row, which `python -m ingest load agricola` requires. A database that held Agricola cards before
-- versioning already has a placeholder row from the versioning migration; this replaces its name and source.
INSERT INTO games (id, name, source)
VALUES ('agricola', 'Agricola', 'https://github.com/klingeling/agricola-card-gallery')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, source = EXCLUDED.source;
