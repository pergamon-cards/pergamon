import argparse
import sys
from pathlib import Path

import psycopg

from . import db
from . import fetch as commands
from . import load as loading
from . import snapshot
from .validate import ValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest", description="Bring card data for a game into pergamon.")
    sub = parser.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="download and transform a game's data into a new snapshot")
    f.add_argument("game")
    f.add_argument("--keep-raw", action="store_true", help="leave the raw download as a folder instead of zipping it")
    f.add_argument("--skip-image-check", action="store_true", help="don't send HEAD requests for a sample of image_urls")

    t = sub.add_parser("transform", help="re-run a game's transform on an existing snapshot's raw data")
    t.add_argument("game")
    t.add_argument("--snapshot", required=True, type=Path, help="snapshot folder, e.g. data/<game>/snapshots/2026-10-26")
    t.add_argument("--check-images", action="store_true", help="send HEAD requests for a sample of image_urls")

    l = sub.add_parser("load", help="apply a snapshot to the database, writing only what changed")
    l.add_argument("game")
    l.add_argument("--snapshot", type=Path, help="snapshot folder (default: the newest for the game)")
    l.add_argument("--dry-run", action="store_true", help="print what would change without writing")

    st = sub.add_parser("status", help="show the loaded dataset, the newest snapshot and upstream for each game")
    st.add_argument("game", nargs="?")

    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            commands.fetch(args.game, keep_raw=args.keep_raw, check_images=not args.skip_image_check)
        elif args.command == "load":
            directory = args.snapshot or (snapshot.list_snapshots(args.game) or [None])[-1]
            if directory is None:
                raise loading.LoadError(f"no snapshots for '{args.game}': run `python -m ingest fetch {args.game}` first")
            with db.connect() as conn:
                print(loading.format_result(args.game, loading.load(conn, args.game, directory, args.dry_run), args.dry_run))
        elif args.command == "status":
            with db.connect() as conn:
                print("\n".join(loading.status(conn, args.game)))
        else:
            commands.transform(args.game, args.snapshot, check_images=args.check_images)
    except (ValidationError, loading.LoadError) as e:
        print(e, file=sys.stderr)
        return 1
    except psycopg.errors.UndefinedTable as e:
        print(f"{e.diag.message_primary}: start the bot once so its migrations create the schema", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
