import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cs2_sim import ModelConfig, ModelError, ReplayModel
from cs2_sim.core.model import ReplayValueEnsemble, SnapshotValueModel


class ReplayModelReleaseLoadingTests(unittest.TestCase):
    def _release(self, root: Path) -> Path:
        release = root / "v1"
        release.mkdir(parents=True)
        model = SnapshotValueModel()
        model.save(release / "small_snapshot_value.json")
        ReplayValueEnsemble(booster_weight=0.0).save_manifest(
            release / "full_replay_value.manifest.json",
            bayesian_path=release / "small_snapshot_value.json",
        )
        return release

    def test_malformed_candidate_artifact_fails_in_strict_mode(self) -> None:
        with TemporaryDirectory() as directory:
            releases = Path(directory)
            release = self._release(releases)
            (release / "candidate_action_value.txt").write_text("not a LightGBM model", encoding="utf-8")
            with self.assertRaises(ModelError):
                ReplayModel.load(ModelConfig(releases_dir=releases, version="v1"))

            degraded = ReplayModel.load(
                ModelConfig(releases_dir=releases, version="v1", allow_fallback=True)
            )
            self.assertFalse(degraded.status.has_candidate_model)

    def test_explicit_missing_engagement_component_requires_fallback_flag(self) -> None:
        with TemporaryDirectory() as directory:
            releases = Path(directory)
            self._release(releases)
            missing = releases / "v1" / "missing-engagement.json"
            with self.assertRaises(ModelError):
                ReplayModel.load(
                    ModelConfig(
                        releases_dir=releases,
                        version="v1",
                        engagement_model_path=missing,
                    )
                )
            degraded = ReplayModel.load(
                ModelConfig(
                    releases_dir=releases,
                    version="v1",
                    engagement_model_path=missing,
                    allow_fallback=True,
                )
            )
            self.assertFalse(degraded.status.has_engagement_model)

    def test_default_release_root_resolves_packaged_noah_layout(self) -> None:
        model = ReplayModel.load(ModelConfig(version="v2"))
        self.assertTrue(model.status.release_path.is_dir())
        self.assertEqual(model.status.release_path.name, "v2")
        self.assertTrue(model.status.has_engagement_model)
        self.assertTrue(model.status.has_candidate_model)


if __name__ == "__main__":
    unittest.main()
