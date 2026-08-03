"""Download Awpy CS2 nav meshes and overview images for the replay maps."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from Noah.training.data_paths import DATA_PATHS


DEFAULT_MAPS = (
    "de_ancient",
    "de_anubis",
    "de_dust2",
    "de_inferno",
    "de_mirage",
    "de_nuke",
    "de_overpass",
)
DEFAULT_PATCH = 17595823


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "cs2-replay-analyser/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_maps(output_dir: Path, *, maps: tuple[str, ...] = DEFAULT_MAPS, patch: int = DEFAULT_PATCH) -> dict[str, object]:
    """Download only the requested nav/overview files into ``output_dir``."""

    if not maps:
        raise ValueError("at least one map is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cs2-map-download-") as temporary:
        root = Path(temporary)
        nav_zip = root / "navs.zip"
        maps_zip = root / "maps.zip"
        _download(f"https://awpycs.com/{patch}/navs.zip", nav_zip)
        _download(f"https://awpycs.com/{patch}/maps.zip", maps_zip)
        nav_root = root / "navs"
        overview_root = root / "maps"
        with zipfile.ZipFile(nav_zip) as archive:
            archive.extractall(nav_root)
        with zipfile.ZipFile(maps_zip) as archive:
            archive.extractall(overview_root)

        downloaded: list[dict[str, object]] = []
        for map_name in maps:
            nav = next(nav_root.rglob(f"{map_name}.json"), None)
            overview = next(overview_root.rglob(f"{map_name}.png"), None)
            lower_overview = next(overview_root.rglob(f"{map_name}_lower.png"), None)
            if nav is None or overview is None:
                raise FileNotFoundError(f"Awpy archive has no complete asset pair for {map_name}")
            map_dir = output_dir / map_name
            map_dir.mkdir(parents=True, exist_ok=True)
            nav_target = map_dir / nav.name
            overview_target = map_dir / overview.name
            shutil.copy2(nav, nav_target)
            shutil.copy2(overview, overview_target)
            item: dict[str, object] = {
                "map": map_name,
                "nav": str(nav_target),
                "overview": str(overview_target),
                "nav_sha256": _sha256(nav_target),
                "overview_sha256": _sha256(overview_target),
            }
            if lower_overview is not None:
                lower_target = map_dir / lower_overview.name
                shutil.copy2(lower_overview, lower_target)
                item["overview_lower"] = str(lower_target)
                item["overview_lower_sha256"] = _sha256(lower_target)
            downloaded.append(item)
        map_data = next(overview_root.rglob("map-data.json"), None)
        if map_data is not None:
            shutil.copy2(map_data, output_dir / "map-data.json")
    manifest = {
        "source": "Awpy public artifact mirror",
        "patch": patch,
        "urls": {
            "navs": f"https://awpycs.com/{patch}/navs.zip",
            "maps": f"https://awpycs.com/{patch}/maps.zip",
        },
        "maps": downloaded,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DATA_PATHS.public_maps)
    parser.add_argument("--patch", type=int, default=DEFAULT_PATCH)
    parser.add_argument("--maps", nargs="+", default=list(DEFAULT_MAPS))
    args = parser.parse_args()
    manifest = download_maps(args.output, maps=tuple(args.maps), patch=args.patch)
    print(f"[maps] downloaded {len(manifest['maps'])} maps -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
