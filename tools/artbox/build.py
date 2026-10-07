"""Build the static site nginx serves: landing page at the root, one app per sub-folder.

python -m artbox.build --manifest apps.json --site site --cache .cache --out dist
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from .bundle import precompress, prune, validate
from .fetch import extract_zip, fetch
from .manifest import App, Manifest, load_manifest
from .render import render_accents, render_index, render_versions

TEMPLATE_NAME = "index.html.tmpl"

log = logging.getLogger("artbox.build")


def build_app(app: App, cache_dir: Path, out_dir: Path, fetcher=fetch) -> Path:
    """Download, verify, unpack and prune one app into `out_dir/<id>`."""
    archive = fetcher(app.download_url, app.sha256, cache_dir)
    target = out_dir / app.id
    with tempfile.TemporaryDirectory(dir=out_dir) as staging:
        unpacked = Path(staging) / app.id
        extract_zip(archive, unpacked)
        removed = prune(unpacked)
        validate(unpacked)
        unpacked.rename(target)
    if removed:
        log.info("  %s: pruned %d paths: %s", app.id, len(removed), ", ".join(removed))
    return target


def _copy_site(manifest: Manifest, site_dir: Path, out_dir: Path) -> None:
    shutil.copytree(site_dir, out_dir, ignore=shutil.ignore_patterns(TEMPLATE_NAME), dirs_exist_ok=True)
    missing = [app.icon for app in manifest.apps if not (out_dir / app.icon).is_file()]
    if missing:
        raise FileNotFoundError(f"icons missing from {site_dir}: {missing}")
    template = (site_dir / TEMPLATE_NAME).read_text(encoding="utf-8")
    (out_dir / "index.html").write_text(render_index(manifest, template), encoding="utf-8")
    (out_dir / "assets" / "accents.css").write_text(render_accents(manifest), encoding="utf-8")
    (out_dir / "versions.json").write_text(render_versions(manifest), encoding="utf-8")


def build_site(manifest: Manifest, site_dir: Path, cache_dir: Path, out_dir: Path, fetcher=fetch) -> None:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"{out_dir} is not empty")
    _copy_site(manifest, site_dir, out_dir)
    for app in manifest.apps:
        log.info("%s %s: %s", app.id, app.version, app.download_url)
        build_app(app, cache_dir, out_dir, fetcher)
    compressed = precompress(out_dir)
    log.info("gzip-compressed %d files", len(compressed))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=Path("apps.json"))
    parser.add_argument("--site", type=Path, default=Path("site"), help="landing page sources")
    parser.add_argument("--cache", type=Path, default=Path(".cache"), help="download cache")
    parser.add_argument("--out", type=Path, required=True, help="output folder (must be empty)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build_site(load_manifest(args.manifest), args.site, args.cache, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
