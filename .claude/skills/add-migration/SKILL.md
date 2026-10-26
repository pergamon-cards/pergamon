---
name: add-migration
description: Add a sqlx database migration to the bot. Use when the schema changes (a new table, column, index or constraint, or a games row for a new game), when the user says "add a migration", or before a change that needs the database to look different at startup.
---

# Add migration

The schema is owned by the files in `migrations/`. The bot runs them with `sqlx::migrate!()` in `src/lib.rs` right after the pool connects, so every database (dev, prod, a fresh one) reaches the same schema at startup. Nothing else creates tables: the ingest tooling and loaders never run DDL.

## Steps

1. **Name the file** `migrations/<YYYYMMDDHHMMSS>_<snake_case_summary>.sql`, with a timestamp later than every existing file (`ls migrations`). sqlx applies files in timestamp order.
2. **Write forward-only SQL.** A leading `--` comment says what the migration is for and anything unusual about it.
   - **Never edit a migration that has been applied or merged.** sqlx stores a checksum for each, and startup fails with a mismatch if one changes. Fix a mistake with a new migration.
   - **Existing data must survive.** Add columns nullable (or with a default), backfill, and only then add `NOT NULL`, foreign keys and `UNIQUE`. Never `DROP` a table that holds loaded card data.
   - Keep related statements in the one file: sqlx runs each file in a single transaction.
3. **Test it on a throwaway database**, never the dev one with real data:
   - start one: ``docker run -d --rm --name pergamon-migtest -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:17``;
   - create two databases. In the first, create the previous schema and a few rows, then apply every file in `migrations/` with `psql -v ON_ERROR_STOP=1 -f` and check that the rows are intact. Apply the files to the second, which is empty, and check the full schema;
   - stop it afterwards: `docker stop pergamon-migtest`.
4. **Check the Rust side:** `cargo fmt`, `cargo clippy --all-targets`, `cargo test`. `migrate!` embeds the folder at compile time, so a new file needs a rebuild; if cargo does not notice it, touch `src/lib.rs`.
5. **Update CLAUDE.md** if the schema description changed, in the same commit.
6. **Do not run the migration against the user's real database yourself.** The bot applies it on its next start; say so in the report.
