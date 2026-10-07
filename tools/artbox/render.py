"""Render the landing page, its per-app accent colours and versions.json from the manifest."""

from __future__ import annotations

import json
from html import escape
from string import Template

from .manifest import App, Manifest


def _tile(app: App) -> str:
    note = f'\n      <p class="note">{escape(app.note)}</p>' if app.note else ""
    return f"""\
  <li>
    <a class="tile" href="{escape(app.id)}/" data-app="{escape(app.id)}">
      <img class="icon" src="{escape(app.icon)}" alt="" width="88" height="88">
      <span class="category">{escape(app.category)}</span>
      <h2 class="name">{escape(app.name)}</h2>
      <p class="description">{escape(app.description)}</p>{note}
      <span class="meta">
        <span class="version">v{escape(app.version)}</span>
        <span class="status">{escape(app.status)}</span>
      </span>
    </a>
  </li>"""


def _source_link(app: App) -> str:
    return f'<a href="{escape(app.source_url)}">{escape(app.name)}</a>'


def render_index(manifest: Manifest, template: str) -> str:
    """Fill the `$tiles` and `$sources` placeholders of the landing page template."""
    return Template(template).substitute(
        tiles="\n".join(_tile(app) for app in manifest.apps),
        sources=" · ".join(_source_link(app) for app in manifest.apps),
    )


def render_accents(manifest: Manifest) -> str:
    """CSS giving each tile its app's colour (kept out of the HTML so the page needs no inline styles)."""
    rules = (f'.tile[data-app="{app.id}"] {{ --accent: {app.accent}; }}' for app in manifest.apps)
    return "\n".join(rules) + "\n"


def render_versions(manifest: Manifest) -> str:
    """Machine-readable list of what this image serves, published as /versions.json."""
    apps = [
        {"id": a.id, "name": a.name, "version": a.version, "source": a.source_url, "sha256": a.sha256}
        for a in manifest.apps
    ]
    return json.dumps({"apps": apps}, indent=2) + "\n"
