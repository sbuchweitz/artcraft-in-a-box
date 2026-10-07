"""apps.json: the pinned list of apps baked into the image.

Each app's `id` becomes its URL sub-folder, so ids are restricted to safe path segments and may
not collide with the landing page's own paths.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path, PurePosixPath

# Paths the landing page itself uses (names with dots, like versions.json, already fail the id pattern).
RESERVED_IDS = frozenset({"assets", "healthz"})

_PATTERNS = {
    "id": re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$"),
    "repo": re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$"),
    "tag": re.compile(r"^[A-Za-z0-9._-]+$"),
    "asset": re.compile(r"^[A-Za-z0-9._-]+\.zip$"),
    "sha256": re.compile(r"^[0-9a-f]{64}$"),
    "accent": re.compile(r"^#[0-9a-fA-F]{6}$"),
}


class ManifestError(ValueError):
    """apps.json is malformed."""


@dataclass(frozen=True)
class App:
    id: str
    name: str
    category: str
    description: str
    status: str
    repo: str
    tag: str
    version: str
    asset: str
    sha256: str
    icon: str
    accent: str
    note: str = ""

    @property
    def download_url(self) -> str:
        return f"https://github.com/{self.repo}/releases/download/{self.tag}/{self.asset}"

    @property
    def source_url(self) -> str:
        return f"https://github.com/{self.repo}"


@dataclass(frozen=True)
class Manifest:
    apps: tuple[App, ...]

    def with_app(self, app: App) -> Manifest:
        """Return a copy with the app of the same id replaced."""
        return replace(self, apps=tuple(app if a.id == app.id else a for a in self.apps))


_REQUIRED = tuple(f.name for f in fields(App) if f.name != "note")
_KNOWN = frozenset(f.name for f in fields(App))


def _parse_app(index: int, raw: object) -> App:
    where = f"apps[{index}]"
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: expected an object")
    unknown = sorted(set(raw) - _KNOWN)
    if unknown:
        raise ManifestError(f"{where}: unknown keys {unknown}")
    for key in _REQUIRED:
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ManifestError(f"{where}: '{key}' must be a non-empty string")
    if not isinstance(raw.get("note", ""), str):
        raise ManifestError(f"{where}: 'note' must be a string")
    for key, pattern in _PATTERNS.items():
        if not pattern.match(raw[key]):
            raise ManifestError(f"{where}: '{key}' has an invalid value {raw[key]!r}")
    if raw["id"] in RESERVED_IDS:
        raise ManifestError(f"{where}: id {raw['id']!r} is reserved")
    icon = PurePosixPath(raw["icon"])
    if icon.is_absolute() or ".." in icon.parts:
        raise ManifestError(f"{where}: 'icon' must be a relative path inside the site folder")
    return App(**raw)


def parse_manifest(data: object) -> Manifest:
    if not isinstance(data, dict) or set(data) != {"apps"} or not isinstance(data["apps"], list):
        raise ManifestError("top level must be an object with a single 'apps' list")
    apps = tuple(_parse_app(i, raw) for i, raw in enumerate(data["apps"]))
    if not apps:
        raise ManifestError("'apps' is empty")
    ids = [a.id for a in apps]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ManifestError(f"duplicate app ids: {duplicates}")
    return Manifest(apps=apps)


def load_manifest(path: Path) -> Manifest:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path}: invalid JSON: {exc}") from exc
    return parse_manifest(data)


def dump_manifest(manifest: Manifest) -> str:
    """Serialise in apps.json style: two-space indent, `note` only when set, trailing newline."""
    apps = []
    for app in manifest.apps:
        entry = asdict(app)
        if not entry["note"]:
            del entry["note"]
        apps.append(entry)
    return json.dumps({"apps": apps}, indent=2, ensure_ascii=False) + "\n"
