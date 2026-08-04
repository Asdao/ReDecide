"""Create a checksummed manifest for a deployable model release directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from Noah.training.contracts import (
    CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION,
    CANDIDATE_ACTION_FIELD_SPECS,
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


def _component(path: Path, *, relative_to: Path) -> dict[str, Any]:
    """Return stable path/size/hash metadata for one release artifact."""

    return {
        "path": path.relative_to(relative_to).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON without exposing a partially-written release file."""

    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.part")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(payload, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def build_release_manifest(release_dir: str | Path, *, version: str | None = None) -> Path:
    root = Path(release_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    release_version = version or root.name
    feature_schema_path = root / "feature_schema.json"
    if feature_schema_path.is_file():
        payload = json.loads(feature_schema_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"feature schema must be an object: {feature_schema_path}")
    else:
        payload = {
            "schema_version": "feature_contracts_v1",
            "snapshot": {
                "schema_version": SNAPSHOT_FEATURE_SCHEMA_VERSION,
                "fields": [field.to_dict() for field in SNAPSHOT_FIELD_SPECS],
            },
            "engagement": {
                "schema_version": ENGAGEMENT_FEATURE_SCHEMA_VERSION,
                "fields": [field.to_dict() for field in ENGAGEMENT_FIELD_SPECS],
            },
        }
    # Refresh evolving schemas even when cloning a previous release. This
    # prevents a v2 engagement artifact from being packaged with the v1
    # feature contract copied from its base release.
    payload["engagement"] = {
        "schema_version": ENGAGEMENT_FEATURE_SCHEMA_VERSION,
        "fields": [field.to_dict() for field in ENGAGEMENT_FIELD_SPECS],
    }
    # Candidate-action probabilities are consumed by the replay harness and
    # must be versioned alongside replay/engagement inputs.
    payload["candidate_action"] = {
        "schema_version": CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION,
        "fields": [field.to_dict() for field in CANDIDATE_ACTION_FIELD_SPECS],
    }
    _atomic_json_write(feature_schema_path, payload)
    components: dict[str, dict[str, Any]] = {}
    known = {
        "full_replay_manifest": "full_replay_value.manifest.json",
        "full_replay_booster": "full_replay_value.txt",
        "full_replay_bayesian": "small_snapshot_value.json",
        "full_replay_calibrator": "full_replay_calibrator.json",
        "full_replay_metrics": "full_replay_metrics.json",
        "full_replay_booster_metadata": "full_replay_value.txt.json",
        "engagement_model": "engagement_model.json",
        "engagement_lightgbm": "engagement_lightgbm.json",
        "candidate_action_value": "candidate_action_value.txt",
        "candidate_action_metadata": "candidate_action_value.txt.json",
        "statistical_action_prior": "small_statistical.json",
        "engagement_metrics": "engagement_metrics.json",
        "engagement_lightgbm_metrics": "engagement_lightgbm_metrics.json",
        "action_vocabulary_coverage": "action_vocabulary_coverage.json",
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
        components[name] = _component(path, relative_to=root)

    # The replay manifest is itself a contract for the files that make up the
    # deployed value ensemble.  Mirror its component metadata in the complete
    # release manifest so validation covers every runtime artifact, not only
    # the top-level manifest file.
    replay_manifest_path = root / known["full_replay_manifest"]
    if replay_manifest_path.is_file():
        try:
            replay_payload = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not read replay manifest: {replay_manifest_path}") from exc
        replay_components = replay_payload.get("components") if isinstance(replay_payload, dict) else None
        if isinstance(replay_components, dict):
            for replay_name, metadata in replay_components.items():
                if metadata is None:
                    # Optional replay components (for example a booster or
                    # calibrator) are represented as null when omitted.
                    continue
                if not isinstance(metadata, dict):
                    raise TypeError(f"replay component metadata must be an object: {replay_name}")
                value = metadata.get("path")
                if not isinstance(value, str) or not value:
                    raise ValueError(f"replay component path is missing: {replay_name}")
                candidate = (replay_manifest_path.parent / value).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError as exc:
                    raise ValueError(f"replay component escapes release directory: {candidate}") from exc
                if not candidate.is_file():
                    raise FileNotFoundError(candidate)
                components.setdefault(
                    f"full_replay_{replay_name}",
                    _component(candidate, relative_to=root),
                )
    manifest = ModelReleaseManifest(
        version=release_version,
        components=components,
        feature_schema_versions={
            "replay": 2,
            "engagement": ENGAGEMENT_FEATURE_SCHEMA_VERSION,
            "candidate_action": CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION,
        },
        dataset_manifest="dataset_manifest.json" if (root / "dataset_manifest.json").is_file() else None,
        metrics="metrics.json" if (root / "metrics.json").is_file() else None,
    )
    output = root / "release_manifest.json"
    manifest.save(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=Path("model/artifacts/releases/v4"))
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    output = build_release_manifest(args.release, version=args.version)
    print(json.dumps({"release": args.release.as_posix(), "manifest": output.as_posix()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
