import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cs2_sim.core.model import REPLAY_FEATURE_NAMES

from Blackbox.training.build_release_manifest import build_release_manifest
from Blackbox.training.contracts import (
    CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION,
    CANDIDATE_ACTION_FIELD_SPECS,
    EngagementFeatures,
    ModelReleaseManifest,
    SnapshotFeatures,
)


class ContractTests(unittest.TestCase):
    def test_snapshot_contract_uses_runtime_vector_order(self):
        snapshot = {"map_name": "de_mirage", "ct_alive": 4, "t_alive": 3}
        features = SnapshotFeatures.from_snapshot(snapshot)
        self.assertEqual(list(features.values), list(REPLAY_FEATURE_NAMES))
        self.assertEqual(features.vector(), [features.values[name] for name in REPLAY_FEATURE_NAMES])

    def test_engagement_contract_rejects_post_event_fields(self):
        with self.assertRaises(ValueError):
            EngagementFeatures({"label_kill": True})

    def test_release_manifest_round_trip_and_checksum_validation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            component = root / "engagement_model.json"
            component.write_text("{}", encoding="utf-8")
            manifest = ModelReleaseManifest(
                version="v1",
                components={"engagement_model": {"path": component.name, "bytes": 2}},
            )
            path = root / "release_manifest.json"
            manifest.save(path)
            loaded = ModelReleaseManifest.load(path)
            loaded.validate(root)
            self.assertEqual(loaded.version, "v1")

    def test_release_schema_includes_candidate_probability_features(self):
        with TemporaryDirectory() as directory:
            release = Path(directory) / "v1"
            release.mkdir()
            (release / "feature_schema.json").write_text(
                '{"schema_version":"feature_contracts_v1","snapshot":{}}',
                encoding="utf-8",
            )
            manifest_path = build_release_manifest(release)
            schema = json.loads((release / "feature_schema.json").read_text(encoding="utf-8"))
            manifest = ModelReleaseManifest.load(manifest_path)
            self.assertEqual(schema["candidate_action"]["schema_version"], CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION)
            self.assertEqual(len(schema["candidate_action"]["fields"]), len(CANDIDATE_ACTION_FIELD_SPECS))
            self.assertEqual(
                manifest.feature_schema_versions["candidate_action"],
                CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION,
            )

    def test_release_validation_rejects_feature_schema_version_drift(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            schema_path = root / "feature_schema.json"
            schema_path.write_text(
                json.dumps({"snapshot": {"schema_version": 1}}),
                encoding="utf-8",
            )
            manifest = ModelReleaseManifest(
                version="v1",
                components={"feature_schema": {"path": schema_path.name}},
                feature_schema_versions={"replay": 2},
            )
            with self.assertRaises(ValueError):
                manifest.validate(root)


if __name__ == "__main__":
    unittest.main()
