-- The Netrunner `games` row, which `python -m ingest load netrunner` requires. Databases loaded before versioning already have a
-- placeholder row from the previous migration; this replaces its name and source.
INSERT INTO games (id, name, source)
VALUES ('netrunner', 'Android: Netrunner', 'https://github.com/Null-Signal-Games/netrunner-cards-json')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, source = EXCLUDED.source;
