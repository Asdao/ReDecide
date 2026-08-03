import json
import tempfile
import unittest
from pathlib import Path

from Noah.training.candidate_rollouts import generate_rollouts
from Noah.training.candidate_states import extract_candidate_state_report
from Noah.training.split_candidate_dataset import split_candidate_dataset


class CandidateDatasetSplitTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> dict:
        path = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "coach_full_replay.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_split_keeps_record_groups_separate(self) -> None:
        report = extract_candidate_state_report([self._fixture(), self._fixture()])
        with tempfile.TemporaryDirectory() as source_directory:
            states = Path(source_directory) / "states.json"
            rollouts = Path(source_directory) / "rollouts.jsonl"
            states.write_text(json.dumps(report.to_dict()), encoding="utf-8")
            rollouts.write_text(
                "".join(json.dumps(row) + "\n" for row in generate_rollouts(report.rows, rollouts=1)),
                encoding="utf-8",
            )
            with tempfile.TemporaryDirectory() as directory:
                manifest = split_candidate_dataset(states, rollouts, directory)
                self.assertTrue(manifest["train_groups"])
                self.assertTrue(manifest["heldout_groups"])
                self.assertTrue(set(manifest["train_groups"]).isdisjoint(manifest["heldout_groups"]))
                self.assertTrue((Path(directory) / "heldout_candidate_rollouts.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
