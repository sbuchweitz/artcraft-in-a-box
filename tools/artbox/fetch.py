"""Download release archives into a checksum-addressed cache and unpack them safely."""

from __future__ import annotations

import hashlib
import shutil
import stat
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

USER_AGENT = "artcraft-in-a-box-build"
_CHUNK = 1 << 20


class ChecksumError(RuntimeError):
    """A download does not match its pinned SHA-256."""


class UnsafeArchiveError(RuntimeError):
    """An archive entry would land outside the target folder or is not a regular file."""


Opener = Callable[[str], object]


def _default_opener(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=120)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, opener: Opener) -> None:
    with opener(url) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out, _CHUNK)


def fetch(
    url: str,
    sha256: str,
    cache_dir: Path,
    opener: Opener = _default_opener,
    attempts: int = 3,
    backoff: float = 2.0,
) -> Path:
    """Return a local copy of `url` whose SHA-256 is `sha256`, downloading it if not cached."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{sha256}.zip"
    if cached.is_file() and sha256_file(cached) == sha256:
        return cached
    partial = cache_dir / f"{sha256}.part"
    for attempt in range(1, attempts + 1):
        try:
            _download(url, partial, opener)
            break
        except OSError:
            partial.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            time.sleep(backoff * attempt)
    actual = sha256_file(partial)
    if actual != sha256:
        partial.unlink()
        raise ChecksumError(f"{url}: expected sha256 {sha256}, got {actual}")
    partial.replace(cached)
    return cached


def _member_path(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts:
        raise UnsafeArchiveError(f"refusing archive entry {name!r}")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise UnsafeArchiveError(f"refusing symlink {name!r}")
    return path


def _common_root(paths: list[PurePosixPath]) -> PurePosixPath | None:
    """The single top-level folder every entry lives in, if there is one."""
    tops = {p.parts[0] for p in paths}
    if len(tops) == 1 and all(len(p.parts) > 1 for p in paths):
        return PurePosixPath(tops.pop())
    return None


def extract_zip(archive: Path, dest: Path) -> None:
    """Unpack `archive` into `dest`, dropping the archive's single top-level folder if present."""
    with zipfile.ZipFile(archive) as zf:
        members = [(info, _member_path(info)) for info in zf.infolist() if not info.is_dir()]
        root = _common_root([path for _, path in members])
        for info, path in members:
            relative = path.relative_to(root) if root else path
            target = dest.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)
