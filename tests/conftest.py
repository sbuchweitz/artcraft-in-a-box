from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def app_entry() -> dict:
    return {
        "id": "photocraft",
        "name": "PhotoCraft",
        "category": "Image editor",
        "description": "The open-source image editor you already know how to use.",
        "status": "Early alpha",
        "repo": "storytold/photocraft",
        "tag": "v0.3.0",
        "version": "0.3.0",
        "asset": "photocraft-web-0.3.0.zip",
        "sha256": "a" * 64,
        "icon": "assets/icons/photocraft.webp",
        "accent": "#2f7bf5",
    }


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def write_zip(path: Path, files: dict[str, bytes]) -> str:
    """Write a zip with `files` to `path`; return its SHA-256."""
    data = zip_bytes(files)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


WEB_BUILD = {
    "index.html": b"<!doctype html><script type=module src=./app-0123456789abcdef.js></script>",
    "app-0123456789abcdef.js": b"export default 1;\n" * 200,
    "app-0123456789abcdef_bg.wasm": b"\0asm\1\0\0\0" + b"\0" * 4096,
    "LICENSE-MIT": b"MIT",
    "_headers": b"/*\n  X-Content-Type-Options: nosniff\n",
    ".htaccess": b"AddType application/wasm .wasm\n",
}


def web_build(prefix: str, extra: dict[str, bytes] | None = None) -> dict[str, bytes]:
    files = {**WEB_BUILD, **(extra or {})}
    return {f"{prefix}/{name}": data for name, data in files.items()}
