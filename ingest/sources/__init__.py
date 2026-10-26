"""One module per game, named by the game's id (`ingest/sources/<game>.py`).

An adapter module defines:

- `SOURCE`: a dict describing where the data comes from (`url`, `license`, ...), copied into each snapshot's `meta.json`.
- `fetch(raw_dir: Path) -> str`: downloads the upstream data into `raw_dir` and returns the upstream version
  (a commit SHA, an ETag, an API version).
- `transform(raw_dir: Path) -> polars.DataFrame`: builds the snapshot from the files in `raw_dir`, with the columns
  `source_id`, `title` and `card` (see `ingest/validate.py`).
- `latest_ref() -> str` (optional): the current upstream version, without downloading the data.

Image URLs belong in the card JSON as `image_url`; images themselves are never stored.
"""

import importlib
import types


def load_adapter(game: str) -> types.ModuleType:
    try:
        adapter = importlib.import_module(f"{__name__}.{game}")
    except ModuleNotFoundError as e:
        if e.name != f"{__name__}.{game}":
            raise
        raise SystemExit(f"no adapter for game '{game}': create ingest/sources/{game}.py") from None
    for name in ("SOURCE", "fetch", "transform"):
        if not hasattr(adapter, name):
            raise SystemExit(f"adapter ingest/sources/{game}.py is missing `{name}`")
    return adapter
