"""Turn an unpacked upstream web build into what nginx serves."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

# A release zip that contains these was packaged from a Cargo target folder (LightCraft 0.2.1 ships
# ~100 MB of build scripts and object files next to the app). Drop the Cargo leftovers.
CARGO_MARKERS = (".fingerprint", ".cargo-lock")
CARGO_LEFTOVERS = (
    ".fingerprint",
    ".cargo-lock",
    ".cargo-build-lock",
    ".cargo-artifact-lock",
    "build",
    "deps",
    "examples",
    "incremental",
)
# Header samples for Netlify/Cloudflare and Apache; nginx/default.conf does their job.
HOST_SAMPLES = ("_headers", ".htaccess")
# Upstream precompressed copies; precompress() regenerates gzip for everything uniformly.
UPSTREAM_COMPRESSED = (".gz", ".br")

COMPRESSIBLE = (".wasm", ".js", ".mjs", ".css", ".html", ".svg", ".json", ".webmanifest", ".md", ".txt")
# nginx's `index` directive needs the real file on disk, so index pages stay uncompressed.
KEEP_UNCOMPRESSED = frozenset({"index.html"})
MIN_COMPRESS_BYTES = 1024


class BundleError(RuntimeError):
    """An unpacked app does not look like a servable web build."""


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def prune(app_dir: Path) -> list[str]:
    """Delete files nginx should not serve; return their paths relative to `app_dir`."""
    doomed = [app_dir / name for name in HOST_SAMPLES]
    if any((app_dir / marker).exists() for marker in CARGO_MARKERS):
        doomed += [app_dir / name for name in CARGO_LEFTOVERS]
    doomed += [p for p in app_dir.rglob("*") if p.is_file() and p.suffix in UPSTREAM_COMPRESSED]
    removed = []
    for path in doomed:
        if path.exists() or path.is_symlink():
            removed.append(path.relative_to(app_dir).as_posix())
            _remove(path)
    return sorted(removed)


def validate(app_dir: Path) -> None:
    if not (app_dir / "index.html").is_file():
        raise BundleError(f"{app_dir.name}: no index.html at the top level")
    if not any(app_dir.rglob("*.wasm")):
        raise BundleError(f"{app_dir.name}: no .wasm module")


def precompress(root: Path, min_bytes: int = MIN_COMPRESS_BYTES) -> list[Path]:
    """Replace every large compressible file below `root` with a gzip copy (`name.gz`).

    nginx serves these with `gzip_static always` and decompresses on the fly (`gunzip on`) for
    clients without gzip support, so the originals are not needed and the image stays small.
    """
    compressed = []
    candidates = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    for path in candidates:
        if path.suffix not in COMPRESSIBLE or path.name in KEEP_UNCOMPRESSED:
            continue
        if path.stat().st_size < min_bytes:
            continue
        target = path.with_name(path.name + ".gz")
        # mtime=0 keeps the output byte-for-byte reproducible.
        target.write_bytes(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))
        path.unlink()
        compressed.append(target)
    return compressed
