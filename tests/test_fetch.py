from __future__ import annotations

import hashlib
import io
import stat
import zipfile

import pytest

from artbox.fetch import ChecksumError, UnsafeArchiveError, extract_zip, fetch, sha256_file
from conftest import write_zip, zip_bytes


class FakeOpener:
    """Serves fixed bytes; optionally fails the first `failures` calls."""

    def __init__(self, payload: bytes, failures: int = 0) -> None:
        self.payload = payload
        self.failures = failures
        self.calls = 0

    def __call__(self, url: str):
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError("connection reset")
        return io.BytesIO(self.payload)


def test_sha256_file(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"hello")
    assert sha256_file(path) == hashlib.sha256(b"hello").hexdigest()


def test_fetch_downloads_and_caches(tmp_path):
    payload = zip_bytes({"a/index.html": b"x"})
    digest = hashlib.sha256(payload).hexdigest()
    opener = FakeOpener(payload)
    first = fetch("https://example.test/a.zip", digest, tmp_path, opener=opener)
    second = fetch("https://example.test/a.zip", digest, tmp_path, opener=opener)
    assert first == second == tmp_path / f"{digest}.zip"
    assert first.read_bytes() == payload
    assert opener.calls == 1


def test_fetch_replaces_corrupt_cache_entry(tmp_path):
    payload = b"good"
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / f"{digest}.zip").write_bytes(b"bad")
    opener = FakeOpener(payload)
    assert fetch("u", digest, tmp_path, opener=opener).read_bytes() == payload
    assert opener.calls == 1


def test_fetch_rejects_checksum_mismatch(tmp_path):
    with pytest.raises(ChecksumError):
        fetch("u", "0" * 64, tmp_path, opener=FakeOpener(b"tampered"))
    assert list(tmp_path.iterdir()) == []


def test_fetch_retries_transient_errors(tmp_path):
    payload = b"data"
    opener = FakeOpener(payload, failures=2)
    path = fetch("u", hashlib.sha256(payload).hexdigest(), tmp_path, opener=opener, backoff=0)
    assert path.read_bytes() == payload
    assert opener.calls == 3


def test_fetch_gives_up_after_attempts(tmp_path):
    opener = FakeOpener(b"x", failures=5)
    with pytest.raises(OSError):
        fetch("u", "0" * 64, tmp_path, opener=opener, attempts=2, backoff=0)
    assert opener.calls == 2
    assert list(tmp_path.iterdir()) == []


def test_extract_strips_single_top_level_folder(tmp_path):
    archive = tmp_path / "a.zip"
    write_zip(archive, {"app-1.0/index.html": b"i", "app-1.0/sub/x.js": b"j"})
    extract_zip(archive, tmp_path / "out")
    assert (tmp_path / "out" / "index.html").read_bytes() == b"i"
    assert (tmp_path / "out" / "sub" / "x.js").read_bytes() == b"j"


def test_extract_keeps_flat_layout(tmp_path):
    archive = tmp_path / "a.zip"
    write_zip(archive, {"index.html": b"i", "sub/x.js": b"j"})
    extract_zip(archive, tmp_path / "out")
    assert (tmp_path / "out" / "index.html").is_file()
    assert (tmp_path / "out" / "sub" / "x.js").is_file()


@pytest.mark.parametrize("name", ["../evil", "app/../../evil", "/abs/evil", "app\\..\\evil"])
def test_extract_rejects_path_traversal(tmp_path, name):
    archive = tmp_path / "a.zip"
    write_zip(archive, {name: b"x", "app/index.html": b"i"})
    with pytest.raises(UnsafeArchiveError):
        extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "evil").exists()


def test_extract_rejects_symlinks(tmp_path):
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        link = zipfile.ZipInfo("app/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "/etc/passwd")
    with pytest.raises(UnsafeArchiveError, match="symlink"):
        extract_zip(archive, tmp_path / "out")
