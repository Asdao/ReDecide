"""Create a checksummed manifest for a deployable model release directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from Noah.training.contracts import (
    ENGAGEMENT_FEATURE_SCHEMA_VERSION,
    ENGAGEMENT_FIELD_SPECS,
    SNAPSHOT_FEATURE_SCHEMA_VERSION,
    SNAPSHOT_FIELD_SPECS,
    ModelReleaseManifest,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release_manifest(release_dir: str | Path, *, version: str | None = None) -> Path:
    root = Path(release_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    release_version = version or root.name
    feature_schema_path = root / "feature_schema.json"
    if not feature_schema_path.is_file():
        feature_schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "feature_contracts_v1",
                    "snapshot": {
                        "schema_version": SNAPSHOT_FEATURE_SCHEMA_VERSION,
                        "fields": [field.to_dict() for field in SNAPSHOT_FIELD_SPECS],
                    },
                    "engagement": {
                        "schema_version": ENGAGEMENT_FEATURE_SCHEMA_VERSION,
                        "fields": [field.to_dict() for field in ENGAGEMENT_FIELD_SPECS],
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    components: dict[str, dict[str, Any]] = {}
    known = {
        "full_replay_manifest": "full_replay_value.manifest.json",
        "engagement_model": "engagement_model.json",
        "engagement_lightgbm": "engagement_lightgbm.json",
        "candidate_action_value": "candidate_action_value.txt",
        "candidate_action_metadata": "candidate_action_value.txt.json",
        "statistical_action_prior": "small_statistical.json",
        "engagement_metrics": "engagement_metrics.json",
        "action_model": "action_frequency.json",
        "transition_model": "zone_transitions.json",
        "feature_schema": "feature_schema.json",
        "dataset_manifest": "dataset_manifest.json",
        "metrics": "metrics.json",
        "fingerprint": "fingerprint.json",
    }
    for name, filename in known.items():
        path = root / filename
        if not path.is_file():
            continue
        components[name] = {
            "path": filename,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    manifest = ModelReleaseManifest(
        version=release_version,
        components=components,
        feature_schema_versions={"replay": 2, "engagement": "engagement_features_v1"},
        dataset_manifest="dataset_manifest.json" if (root / "dataset_manifest.json").is_file() else None,
        metrics="metrics.json" if (root / "metrics.json").is_file() else None,
    )
    output = root / "release_manifest.json"
    manifest.save(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=Path("model/artifacts/releases/v2"))
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    output = build_release_manifest(args.release, version=args.version)
    print(json.dumps({"release": args.release.as_posix(), "manifest": output.as_posix()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
