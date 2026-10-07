"""Bump apps.json to the latest upstream releases.

    python -m artbox.update [--manifest apps.json] [--check]

For each app, looks up the repository's latest (non-prerelease) GitHub release, picks the
`<id>-web-<version>.zip` asset and pins its SHA-256. The checksum comes from GitHub's own asset
digest and, when the release has one, its SHA256SUMS.txt; the two must agree.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from .fetch import USER_AGENT
from .manifest import App, Manifest, dump_manifest, load_manifest

API = "https://api.github.com"
SUMS_ASSET = "SHA256SUMS.txt"

log = logging.getLogger("artbox.update")


class UpdateError(RuntimeError):
    """A release cannot be pinned safely."""


class Client(Protocol):
    def get_json(self, url: str) -> dict: ...
    def get_text(self, url: str) -> str: ...


class GitHubClient:
    """Minimal GitHub client; uses $GITHUB_TOKEN when set (raises the API rate limit)."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    def _get(self, url: str, accept: str) -> bytes:
        headers = {"User-Agent": USER_AGENT, "Accept": accept}
        if self._token and url.startswith(API):
            headers["Authorization"] = f"Bearer {self._token}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
            return resp.read()

    def get_json(self, url: str) -> dict:
        return json.loads(self._get(url, "application/vnd.github+json"))

    def get_text(self, url: str) -> str:
        return self._get(url, "application/octet-stream").decode("utf-8")


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse `sha256sum` output (`<hex>  <name>` or `<hex> *<name>`) into {name: hex}."""
    sums = {}
    for line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64}) [ *](.+)$", line.strip())
        if match:
            sums[match.group(2).strip()] = match.group(1).lower()
    return sums


def pick_web_asset(release: dict, app_id: str) -> tuple[dict, str] | None:
    """The release's `<app_id>-web-<version>.zip` asset and its version, if it has one."""
    pattern = re.compile(rf"^{re.escape(app_id)}-web-(?P<version>[0-9][A-Za-z0-9.+-]*)\.zip$")
    for asset in release.get("assets", []):
        match = pattern.match(asset.get("name", ""))
        if match:
            return asset, match.group("version")
    return None


def resolve_sha256(asset: dict, sums: dict[str, str]) -> str:
    digest = asset.get("digest") or ""
    from_api = digest.removeprefix("sha256:").lower() if digest.startswith("sha256:") else None
    from_sums = sums.get(asset["name"])
    if from_api and from_sums and from_api != from_sums:
        raise UpdateError(f"{asset['name']}: GitHub digest {from_api} != SHA256SUMS {from_sums}")
    checksum = from_api or from_sums
    if not checksum:
        raise UpdateError(f"{asset['name']}: no checksum (no GitHub digest, not in {SUMS_ASSET})")
    return checksum


def _release_sums(release: dict, client: Client) -> dict[str, str]:
    for asset in release.get("assets", []):
        if asset.get("name") == SUMS_ASSET:
            return parse_sha256sums(client.get_text(asset["browser_download_url"]))
    return {}


def latest_app(app: App, client: Client) -> App:
    """`app` pinned to its repository's latest release (unchanged if that has no web build)."""
    release = client.get_json(f"{API}/repos/{app.repo}/releases/latest")
    picked = pick_web_asset(release, app.id)
    if picked is None:
        log.warning("%s %s: no web build, keeping %s", app.repo, release.get("tag_name"), app.version)
        return app
    asset, version = picked
    if asset["name"] == app.asset and release["tag_name"] == app.tag:
        return app
    sha256 = resolve_sha256(asset, _release_sums(release, client))
    return replace(app, tag=release["tag_name"], version=version, asset=asset["name"], sha256=sha256)


def update_manifest(manifest: Manifest, client: Client) -> tuple[Manifest, list[str]]:
    """Return the bumped manifest and one `id old -> new` line per changed app."""
    updated, changes = manifest, []
    for app in manifest.apps:
        latest = latest_app(app, client)
        if latest != app:
            updated = updated.with_app(latest)
            changes.append(f"{app.id} {app.version} -> {latest.version}")
    return updated, changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=Path("apps.json"))
    parser.add_argument("--check", action="store_true", help="only report; exit 1 if updates exist")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    manifest = load_manifest(args.manifest)
    try:
        updated, changes = update_manifest(manifest, GitHubClient(os.environ.get("GITHUB_TOKEN")))
    except (urllib.error.URLError, UpdateError) as exc:
        log.error("%s", exc)
        return 2
    for line in changes:
        print(line)
    if args.check:
        return 1 if changes else 0
    if changes:
        args.manifest.write_text(dump_manifest(updated), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
