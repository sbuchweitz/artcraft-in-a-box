from __future__ import annotations

import gzip
import os

import pytest

from artbox.bundle import BundleError, precompress, prune, validate


def make_tree(root, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def test_prune_removes_host_samples_and_upstream_compressed_copies(tmp_path):
    make_tree(
        tmp_path,
        {
            "index.html": b"i",
            "app.js": b"j",
            "app.js.gz": b"z",
            "app.js.br": b"b",
            "_headers": b"h",
            ".htaccess": b"a",
            "build/keep.txt": b"not cargo",
        },
    )
    removed = prune(tmp_path)
    assert removed == [".htaccess", "_headers", "app.js.br", "app.js.gz"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app.js", "build", "index.html"]


def test_prune_removes_cargo_leftovers_only_when_marked(tmp_path):
    make_tree(
        tmp_path,
        {
            "index.html": b"i",
            "app_bg.wasm": b"w",
            ".fingerprint/x/lib": b"f",
            ".cargo-lock": b"",
            "build/crate/build-script-build": b"\x7fELF",
            "deps/libfoo.rlib": b"r",
            "deps/libfoo.rlib.gz": b"r",
            "incremental/x": b"i",
            "examples/.keep": b"",
        },
    )
    removed = prune(tmp_path)
    assert removed == [".cargo-lock", ".fingerprint", "build", "deps", "examples", "incremental"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app_bg.wasm", "index.html"]


def test_validate_accepts_web_build(tmp_path):
    make_tree(tmp_path, {"index.html": b"i", "pkg/app_bg.wasm": b"w"})
    validate(tmp_path)


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"app_bg.wasm": b"w"}, "index.html"),
        ({"index.html": b"i"}, "wasm"),
        ({"sub/index.html": b"i"}, "index"),
    ],
)
def test_validate_rejects_incomplete_build(tmp_path, files, message):
    make_tree(tmp_path, files)
    with pytest.raises(BundleError, match=message):
        validate(tmp_path)


def test_precompress_replaces_large_compressible_files(tmp_path):
    big_js = b"console.log(1);\n" * 200
    make_tree(
        tmp_path,
        {
            "index.html": b"<p>" * 2000,
            "app/index.html": b"<p>" * 2000,
            "app/app.js": big_js,
            "app/app_bg.wasm": b"\0asm" + b"\0" * 4000,
            "app/small.js": b"x",
            "app/icon.webp": b"\0" * 4000,
            "app/LICENSE-MIT": b"M" * 4000,
        },
    )
    compressed = precompress(tmp_path)
    names = sorted(p.relative_to(tmp_path).as_posix() for p in compressed)
    assert names == ["app/app.js.gz", "app/app_bg.wasm.gz"]
    assert not (tmp_path / "app/app.js").exists()
    assert gzip.decompress((tmp_path / "app/app.js.gz").read_bytes()) == big_js
    for kept in ["index.html", "app/index.html", "app/small.js", "app/icon.webp", "app/LICENSE-MIT"]:
        assert (tmp_path / kept).is_file(), kept


def test_precompress_is_reproducible(tmp_path):
    data = b"function f(){}\n" * 500
    outputs = []
    for run in ("a", "b"):
        make_tree(tmp_path / run, {"x.js": data})
        os.utime(tmp_path / run / "x.js", (1, 1 if run == "a" else 99999))
        precompress(tmp_path / run)
        outputs.append((tmp_path / run / "x.js.gz").read_bytes())
    assert outputs[0] == outputs[1]
