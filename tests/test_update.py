from __future__ import annotations

import json

import pytest

from artbox import update
from artbox.manifest import load_manifest, parse_manifest
from artbox.update import (
    UpdateError,
    latest_app,
    parse_sha256sums,
    pick_web_asset,
    resolve_sha256,
    update_manifest,
)

NEW_SHA = "b" * 64
SUMS_URL = "https://github.com/storytold/photocraft/releases/download/v0.4.0/SHA256SUMS.txt"


def release(tag="v0.4.0", digest=f"sha256:{NEW_SHA}", sums=True, web=True):
    version = tag.removeprefix("v")
    assets = [{"name": f"photocraft-{version}-linux-x86_64.tar.gz", "digest": "sha256:" + "c" * 64}]
    if web:
        assets.append({"name": f"photocraft-web-{version}.zip", "digest": digest})
    if sums:
        assets.append({"name": "SHA256SUMS.txt", "browser_download_url": SUMS_URL})
    return {"tag_name": tag, "assets": assets}


class FakeClient:
    def __init__(self, releases: dict, sums_text: str = f"{NEW_SHA}  photocraft-web-0.4.0.zip\n") -> None:
        self.releases = releases
        self.sums_text = sums_text
        self.urls: list[str] = []

    def get_json(self, url: str) -> dict:
        self.urls.append(url)
        return self.releases[url.split("/repos/")[1].removesuffix("/releases/latest")]

    def get_text(self, url: str) -> str:
        self.urls.append(url)
        return self.sums_text


def test_parse_sha256sums_handles_text_and_binary_markers():
    text = f"{'A' * 64}  one.zip\n{'b' * 64} *two.zip\ngarbage line\n\n"
    assert parse_sha256sums(text) == {"one.zip": "a" * 64, "two.zip": "b" * 64}


def test_pick_web_asset_matches_only_this_apps_web_zip():
    rel = {"assets": [{"name": "vectorcraft-web-1.0.zip"}, {"name": "photocraft-web-0.4.0-rc.1.zip"}]}
    asset, version = pick_web_asset(rel, "photocraft")
    assert asset["name"] == "photocraft-web-0.4.0-rc.1.zip"
    assert version == "0.4.0-rc.1"
    assert pick_web_asset({"assets": [{"name": "photocraft-0.4.0.dmg"}]}, "photocraft") is None


def test_resolve_sha256_prefers_agreeing_sources():
    asset = {"name": "a.zip", "digest": f"sha256:{NEW_SHA}"}
    assert resolve_sha256(asset, {"a.zip": NEW_SHA}) == NEW_SHA
    assert resolve_sha256(asset, {}) == NEW_SHA
    assert resolve_sha256({"name": "a.zip", "digest": None}, {"a.zip": NEW_SHA}) == NEW_SHA


def test_resolve_sha256_rejects_disagreement_and_absence():
    with pytest.raises(UpdateError, match="!="):
        resolve_sha256({"name": "a.zip", "digest": f"sha256:{NEW_SHA}"}, {"a.zip": "d" * 64})
    with pytest.raises(UpdateError, match="no checksum"):
        resolve_sha256({"name": "a.zip"}, {})


def test_latest_app_bumps_to_new_release(app_entry):
    app = parse_manifest({"apps": [app_entry]}).apps[0]
    bumped = latest_app(app, FakeClient({"storytold/photocraft": release()}))
    assert (bumped.tag, bumped.version, bumped.asset, bumped.sha256) == (
        "v0.4.0",
        "0.4.0",
        "photocraft-web-0.4.0.zip",
        NEW_SHA,
    )
    assert bumped.name == app.name


def test_latest_app_keeps_current_when_release_has_no_web_build(app_entry):
    app = parse_manifest({"apps": [app_entry]}).apps[0]
    assert latest_app(app, FakeClient({"storytold/photocraft": release(web=False)})) == app


def test_latest_app_skips_checksum_lookup_when_already_current(app_entry):
    app = parse_manifest({"apps": [app_entry]}).apps[0]
    client = FakeClient({"storytold/photocraft": release(tag="v0.3.0")})
    assert latest_app(app, client) == app
    assert SUMS_URL not in client.urls


def test_update_manifest_lists_changes(app_entry):
    manifest = parse_manifest({"apps": [app_entry]})
    updated, changes = update_manifest(manifest, FakeClient({"storytold/photocraft": release()}))
    assert changes == ["photocraft 0.3.0 -> 0.4.0"]
    assert updated.apps[0].version == "0.4.0"
    assert manifest.apps[0].version == "0.3.0"


def _write(tmp_path, app_entry):
    path = tmp_path / "apps.json"
    path.write_text(json.dumps({"apps": [app_entry]}))
    return path


def test_main_writes_bumped_manifest(tmp_path, app_entry, monkeypatch, capsys):
    path = _write(tmp_path, app_entry)
    monkeypatch.setattr(update, "GitHubClient", lambda token: FakeClient({"storytold/photocraft": release()}))
    assert update.main(["--manifest", str(path)]) == 0
    assert capsys.readouterr().out == "photocraft 0.3.0 -> 0.4.0\n"
    assert load_manifest(path).apps[0].version == "0.4.0"


def test_main_check_mode_does_not_write(tmp_path, app_entry, monkeypatch):
    path = _write(tmp_path, app_entry)
    before = path.read_text()
    monkeypatch.setattr(update, "GitHubClient", lambda token: FakeClient({"storytold/photocraft": release()}))
    assert update.main(["--manifest", str(path), "--check"]) == 1
    assert path.read_text() == before


def test_main_reports_unsafe_release(tmp_path, app_entry, monkeypatch):
    path = _write(tmp_path, app_entry)
    bad_sums = f"{'d' * 64}  photocraft-web-0.4.0.zip"
    client = FakeClient({"storytold/photocraft": release()}, sums_text=bad_sums)
    monkeypatch.setattr(update, "GitHubClient", lambda token: client)
    assert update.main(["--manifest", str(path)]) == 2
