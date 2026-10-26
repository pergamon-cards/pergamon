import argparse
import sys
from pathlib import Path

from . import fetch as commands
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

    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            commands.fetch(args.game, keep_raw=args.keep_raw, check_images=not args.skip_image_check)
        else:
            commands.transform(args.game, args.snapshot, check_images=args.check_images)
    except ValidationError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
