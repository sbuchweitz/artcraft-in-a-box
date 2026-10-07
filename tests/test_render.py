from __future__ import annotations

import json
from pathlib import Path

import pytest

from artbox.manifest import parse_manifest
from artbox.render import render_accents, render_index, render_versions

TEMPLATE = (Path(__file__).resolve().parent.parent / "site" / "index.html.tmpl").read_text()


@pytest.fixture
def manifest(app_entry):
    second = {
        **app_entry,
        "id": "lightcraft",
        "name": "LightCraft",
        "accent": "#f3a617",
        "note": "Keeps its library in browser storage.",
    }
    return parse_manifest({"apps": [app_entry, second]})


def test_index_has_a_tile_per_app_linking_to_its_folder(manifest):
    html = render_index(manifest, TEMPLATE)
    assert html.count('class="tile"') == 2
    assert 'href="photocraft/"' in html
    assert 'href="lightcraft/"' in html
    assert 'src="assets/icons/photocraft.webp"' in html
    assert "The open-source image editor you already know how to use." in html
    assert "v0.3.0" in html
    assert 'href="https://github.com/storytold/photocraft"' in html


def test_index_renders_note_only_when_set(manifest):
    html = render_index(manifest, TEMPLATE)
    assert html.count('class="note"') == 1
    assert "Keeps its library in browser storage." in html


def test_index_uses_relative_urls_only(manifest):
    html = render_index(manifest, TEMPLATE)
    assert 'href="/' not in html
    assert 'src="/' not in html


def test_index_escapes_manifest_text(app_entry):
    hostile = {**app_entry, "name": "<script>alert(1)</script>", "description": 'a "quoted" & <b>bold</b>'}
    html = render_index(parse_manifest({"apps": [hostile]}), TEMPLATE)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;quoted&quot; &amp; &lt;b&gt;" in html


def test_accents_css(manifest):
    css = render_accents(manifest)
    assert '.tile[data-app="photocraft"] { --accent: #2f7bf5; }' in css
    assert '.tile[data-app="lightcraft"] { --accent: #f3a617; }' in css


def test_versions_json(manifest):
    data = json.loads(render_versions(manifest))
    assert [a["id"] for a in data["apps"]] == ["photocraft", "lightcraft"]
    assert data["apps"][0]["version"] == "0.3.0"
    assert data["apps"][0]["source"] == "https://github.com/storytold/photocraft"
