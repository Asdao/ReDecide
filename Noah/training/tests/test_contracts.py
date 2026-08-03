import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cs2_sim.core.model import REPLAY_FEATURE_NAMES

from Noah.training.contracts import (
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


if __name__ == "__main__":
    unittest.main()
