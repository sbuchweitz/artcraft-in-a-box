from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from artbox.manifest import ManifestError, dump_manifest, load_manifest, parse_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_parses_valid_entry(app_entry):
    manifest = parse_manifest({"apps": [app_entry]})
    app = manifest.apps[0]
    assert app.id == "photocraft"
    assert app.note == ""
    assert app.download_url == (
        "https://github.com/storytold/photocraft/releases/download/v0.3.0/photocraft-web-0.3.0.zip"
    )
    assert app.source_url == "https://github.com/storytold/photocraft"


def test_repository_manifest_is_valid():
    manifest = load_manifest(REPO_ROOT / "apps.json")
    assert len(manifest.apps) >= 1
    for app in manifest.apps:
        assert (REPO_ROOT / "site" / app.icon).is_file(), app.icon


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", "Photo Craft"),
        ("id", "../etc"),
        ("id", "assets"),
        ("id", "healthz"),
        ("sha256", "abc"),
        ("sha256", "A" * 64),
        ("repo", "storytold"),
        ("asset", "photocraft.tar.gz"),
        ("accent", "blue"),
        ("tag", "v1/../../x"),
        ("icon", "/etc/passwd"),
        ("icon", "assets/../../secret"),
        ("name", ""),
        ("name", 42),
        ("note", 1),
    ],
)
def test_rejects_invalid_values(app_entry, key, value):
    with pytest.raises(ManifestError):
        parse_manifest({"apps": [{**app_entry, key: value}]})


def test_rejects_missing_key(app_entry):
    del app_entry["sha256"]
    with pytest.raises(ManifestError, match="sha256"):
        parse_manifest({"apps": [app_entry]})


def test_rejects_unknown_key(app_entry):
    with pytest.raises(ManifestError, match="unknown keys"):
        parse_manifest({"apps": [{**app_entry, "shasum": "x"}]})


def test_rejects_duplicate_ids(app_entry):
    with pytest.raises(ManifestError, match="duplicate"):
        parse_manifest({"apps": [app_entry, app_entry]})


@pytest.mark.parametrize("data", [[], {}, {"apps": []}, {"apps": {}}, {"apps": [], "x": 1}, {"apps": ["x"]}])
def test_rejects_bad_structure(data):
    with pytest.raises(ManifestError):
        parse_manifest(data)


def test_load_reports_invalid_json(tmp_path):
    path = tmp_path / "apps.json"
    path.write_text("{nope")
    with pytest.raises(ManifestError, match="invalid JSON"):
        load_manifest(path)


def test_dump_round_trips_and_omits_empty_note(app_entry):
    noted = {**app_entry, "id": "lightcraft", "note": "Back up your library."}
    manifest = parse_manifest({"apps": [app_entry, noted]})
    text = dump_manifest(manifest)
    assert text.endswith("\n")
    data = json.loads(text)
    assert "note" not in data["apps"][0]
    assert data["apps"][1]["note"] == "Back up your library."
    assert parse_manifest(data) == manifest


def test_with_app_returns_new_manifest(app_entry):
    manifest = parse_manifest({"apps": [app_entry]})
    bumped = replace(manifest.apps[0], version="9.9.9")
    updated = manifest.with_app(bumped)
    assert updated.apps[0].version == "9.9.9"
    assert manifest.apps[0].version == "0.3.0"
