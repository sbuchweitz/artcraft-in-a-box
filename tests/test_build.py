from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

import pytest

from artbox import build
from artbox.manifest import parse_manifest
from conftest import web_build, write_zip

SITE = Path(__file__).resolve().parent.parent / "site"
CARGO_JUNK = {".fingerprint/x/lib": b"f", "deps/libfoo.rlib": b"r", ".cargo-lock": b""}


@pytest.fixture
def archives(tmp_path):
    """Two fake release zips (one with Cargo leftovers) and a fetcher that serves them."""
    store = tmp_path / "archives"
    store.mkdir()
    shas = {
        "photocraft": write_zip(store / "photocraft.zip", web_build("photocraft-web-0.3.0")),
        "lightcraft": write_zip(store / "lightcraft.zip", web_build("lightcraft-web-0.2.1", CARGO_JUNK)),
    }
    by_sha = {sha: store / f"{app_id}.zip" for app_id, sha in shas.items()}

    def fetcher(url, sha256, cache_dir):
        return by_sha[sha256]

    return shas, fetcher


@pytest.fixture
def manifest(app_entry, archives):
    shas, _ = archives
    light = {**app_entry, "id": "lightcraft", "name": "LightCraft", "icon": "assets/icons/lightcraft.webp"}
    return parse_manifest(
        {"apps": [{**app_entry, "sha256": shas["photocraft"]}, {**light, "sha256": shas["lightcraft"]}]}
    )


def test_build_site_lays_out_landing_page_and_apps(tmp_path, manifest, archives):
    _, fetcher = archives
    out = tmp_path / "out"
    build.build_site(manifest, SITE, tmp_path / "cache", out, fetcher=fetcher)

    assert (out / "index.html").is_file()
    assert 'href="lightcraft/"' in (out / "index.html").read_text()
    assert (out / "assets" / "icons" / "photocraft.webp").is_file()
    assert (out / "favicon.ico").is_file()
    assert not (out / "index.html.tmpl").exists()
    assert json.loads((out / "versions.json").read_text())["apps"][1]["id"] == "lightcraft"
    for app_id in ("photocraft", "lightcraft"):
        app_dir = out / app_id
        assert (app_dir / "index.html").is_file()
        wasm = gzip.decompress((app_dir / "app-0123456789abcdef_bg.wasm.gz").read_bytes())
        assert wasm.startswith(b"\0asm")
        assert not (app_dir / "_headers").exists()
        assert not (app_dir / ".htaccess").exists()
    assert not (out / "lightcraft" / "deps").exists()
    assert not (out / "lightcraft" / ".fingerprint").exists()
    assert sorted(p.name for p in out.iterdir() if p.name.startswith("tmp")) == []


def test_build_site_refuses_non_empty_output(tmp_path, manifest, archives):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale").write_text("x")
    with pytest.raises(FileExistsError):
        build.build_site(manifest, SITE, tmp_path / "cache", out, fetcher=archives[1])


def test_build_site_reports_missing_icon(tmp_path, manifest, archives):
    site = tmp_path / "site"
    shutil.copytree(SITE, site)
    (site / "assets" / "icons" / "lightcraft.webp").unlink()
    with pytest.raises(FileNotFoundError, match="lightcraft.webp"):
        build.build_site(manifest, site, tmp_path / "cache", tmp_path / "out", fetcher=archives[1])


def test_main_parses_arguments(tmp_path, monkeypatch, app_entry):
    calls = {}

    def fake_build_site(manifest, site, cache, out):
        calls.update(manifest=manifest, site=site, cache=cache, out=out)

    manifest_path = tmp_path / "apps.json"
    manifest_path.write_text(json.dumps({"apps": [app_entry]}))
    monkeypatch.setattr(build, "build_site", fake_build_site)
    assert build.main(["--manifest", str(manifest_path), "--out", str(tmp_path / "dist")]) == 0
    assert calls["out"] == tmp_path / "dist"
    assert calls["manifest"].apps[0].id == "photocraft"
