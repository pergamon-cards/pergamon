import io
import json
import tarfile

import pytest

from ingest.sources import load_adapter, netrunner


def tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


CORE = [
    {"code": "01001", "title": "Noise: Hacker Extraordinaire", "type_code": "identity", "text": "Whenever you install a virus program"},
    {"code": "01002", "title": "Déjà Vu", "type_code": "event"},
]
REPRINT = [{"code": "20001", "title": "Déjà Vu", "type_code": "event"}]
FILES = {
    "repo-abc/pack/core.json": json.dumps(CORE),
    "repo-abc/pack/sc19.json": json.dumps(REPRINT),
    "repo-abc/cycles.json": "[]",
    "repo-abc/pack/notes.txt": "ignored",
    "repo-abc/nested/pack/x.json": "[]",
    "repo-abc/pack/../../escape.json": "[]",
}


def test_the_adapter_follows_the_interface():
    adapter = load_adapter("netrunner")
    assert adapter.SOURCE["url"].endswith("netrunner-cards-json") and callable(adapter.latest_ref)


def test_extract_keeps_only_pack_json(tmp_path):
    netrunner.extract_packs(tarball(FILES), tmp_path)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == ["pack/core.json", "pack/sc19.json"]
    assert not (tmp_path.parent / "escape.json").exists()


def test_transform_adds_image_urls_and_keeps_reprints(tmp_path):
    netrunner.extract_packs(tarball(FILES), tmp_path)
    df = netrunner.transform(tmp_path)
    assert df["source_id"].to_list() == ["01001", "01002", "20001"]
    assert df["title"].to_list() == ["Noise: Hacker Extraordinaire", "Déjà Vu", "Déjà Vu"]
    first = json.loads(df["card"][0])
    assert first["image_url"] == "https://card-images.netrunnerdb.com/v2/large/01001.jpg"
    assert {k: v for k, v in first.items() if k != "image_url"} == CORE[0]


def test_fetch_downloads_the_tarball_for_the_latest_commit(tmp_path, monkeypatch):
    urls = []

    class Response:
        content = tarball(FILES)

        def raise_for_status(self):
            pass

        def json(self):
            return {"sha": "abc123"}

    monkeypatch.setattr(netrunner.httpx, "get", lambda url, **kwargs: urls.append(url) or Response())
    assert netrunner.fetch(tmp_path) == "abc123"
    assert urls == [
        "https://api.github.com/repos/Null-Signal-Games/netrunner-cards-json/commits/HEAD",
        "https://codeload.github.com/Null-Signal-Games/netrunner-cards-json/tar.gz/abc123",
    ]
    assert (tmp_path / "pack" / "core.json").is_file()
