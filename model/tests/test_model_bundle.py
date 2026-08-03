import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cs2_sim.core.model import REPLAY_FEATURE_NAMES, ReplayValueEnsemble, SnapshotValueModel, snapshot_features
from training.model_bundle import BundleError, ModelBundleStore, validate_bundle


class _FixedBooster:
    def __init__(self, probability: float) -> None:
        self.probability = probability
        self.rows: list[list[float]] = []

    def predict(self, rows: list[list[float]]) -> list[float]:
        self.rows.extend(rows)
        return [self.probability for _ in rows]


def _write_bayesian_bundle(root: Path, *, name: str = "manifest.json") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "small.json"
    model = SnapshotValueModel()
    model.observe({"map_name": "de_mirage", "ct_alive": 4, "t_alive": 2, "label_round_winner": "ct"})
    model.save(model_path)
    manifest_path = root / name
    ReplayValueEnsemble(booster_weight=0.0).save_manifest(
        manifest_path,
        bayesian_path=model_path,
    )
    return manifest_path


class ModelBundleTests(unittest.TestCase):
    def test_direct_feature_prediction_validates_order_and_uses_booster(self) -> None:
        booster = _FixedBooster(0.72)
        model = ReplayValueEnsemble(booster=booster)
        snapshot = {
            "map_name": "de_mirage",
            "ct_alive": 3,
            "t_alive": 2,
            "elapsed_seconds": 10,
        }
        prediction = model.predict_features(snapshot_features(snapshot))
        self.assertAlmostEqual(prediction.probability, 0.72)
        self.assertIsNone(prediction.bayesian_probability)
        self.assertEqual(len(booster.rows[0]), len(REPLAY_FEATURE_NAMES))
        with self.assertRaises(ValueError):
            model.predict_features([0.0])

    def test_manifest_paths_are_relative_to_manifest_and_checksums_are_verified(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as other:
            root = Path(directory) / "bundle"
            manifest = _write_bayesian_bundle(root)
            previous = Path.cwd()
            try:
                os.chdir(other)
                loaded = ReplayValueEnsemble.load(manifest)
            finally:
                os.chdir(previous)
            self.assertEqual(loaded.bayesian.global_sample_count(), 1)

            (root / "small.json").write_text("corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                ReplayValueEnsemble.load(manifest)
            degraded = ReplayValueEnsemble.load(manifest, allow_fallback=True)
            self.assertEqual(degraded.bayesian.global_sample_count(), 0)

    def test_missing_manifest_component_requires_explicit_fallback(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "bundle"
            manifest = _write_bayesian_bundle(root)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["components"]["bayesian"]["path"] = "missing.json"
            payload["bayesian"] = "missing.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                ReplayValueEnsemble.load(manifest)
            self.assertIsNotNone(ReplayValueEnsemble.load(manifest, allow_fallback=True))

    def test_bundle_store_stages_atomically_and_rolls_back(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_one = _write_bayesian_bundle(root / "source-one")
            source_two = _write_bayesian_bundle(root / "source-two")
            releases = root / "releases"
            store = ModelBundleStore(releases)
            store.stage(source_one, version="v1", require_checksums=True)
            store.activate("v1", require_checksums=True)
            store.stage(source_two, version="v2", require_checksums=True)
            store.activate("v2", require_checksums=True)
            self.assertEqual(store.current(), releases.resolve() / "v2")
            store.rollback(require_checksums=True)
            self.assertEqual(store.current(), releases.resolve() / "v1")

            (releases / "v1" / "small.json").write_text("tampered", encoding="utf-8")
            with self.assertRaises(BundleError):
                validate_bundle(releases / "v1", require_checksums=True)


if __name__ == "__main__":
    unittest.main()
