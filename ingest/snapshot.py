"""Date-stamped snapshots under `data/<game>/snapshots/`: `cards.parquet`, `meta.json`, and the raw download as `raw/` or `raw.zip`."""

import hashlib
import json
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

REPO_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_DIR / "data"


def snapshots_dir(game: str, data_dir: Path = DATA_DIR) -> Path:
    return data_dir / game / "snapshots"


def list_snapshots(game: str, data_dir: Path = DATA_DIR) -> list[Path]:
    """Existing snapshot folders, oldest first (`2026-10-26` < `2026-10-26-2` < `2026-10-27`)."""
    root = snapshots_dir(game, data_dir)
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if (p / "meta.json").is_file()), key=lambda p: _sort_key(p.name))


def _sort_key(name: str) -> tuple[str, int]:
    day, n = name[:10], name[11:]
    return day, int(n) if n else 1


def new_snapshot_dir(game: str, data_dir: Path = DATA_DIR, today: date | None = None) -> Path:
    """Creates `<today>`, or `<today>-2`, `<today>-3`, ... when that folder exists (even an unfinished one)."""
    root = snapshots_dir(game, data_dir)
    root.mkdir(parents=True, exist_ok=True)
    day = (today or date.today()).isoformat()
    path, n = root / day, 1
    while path.exists():
        n += 1
        path = root / f"{day}-{n}"
    path.mkdir()
    return path


def content_hash(df: pl.DataFrame) -> str:
    """Hashes the cards, not the parquet bytes: rows sorted by `source_id`, each as canonical JSON."""
    lines = []
    for source_id, title, card in df.sort("source_id").iter_rows():
        row = {"source_id": source_id, "title": title, "card": json.loads(card)}
        lines.append(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def read_meta(snapshot: Path) -> dict:
    return json.loads((snapshot / "meta.json").read_text())


def write_meta(snapshot: Path, meta: dict) -> None:
    (snapshot / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def archive_raw(snapshot: Path) -> Path:
    """Zips `raw/` into `raw.zip` (paths relative to `raw/`) and deletes the folder."""
    raw = snapshot / "raw"
    target = snapshot / "raw.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(raw.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(raw).as_posix())
    shutil.rmtree(raw)
    return target


@contextmanager
def raw_dir(snapshot: Path):
    """The snapshot's raw data as a folder: `raw/` itself, or `raw.zip` extracted to a temporary folder."""
    raw = snapshot / "raw"
    if raw.is_dir():
        yield raw
        return
    archive = snapshot / "raw.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"{snapshot} has neither raw/ nor raw.zip")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(archive) as z:
            z.extractall(Path(tmp) / "raw")
        yield Path(tmp) / "raw"
