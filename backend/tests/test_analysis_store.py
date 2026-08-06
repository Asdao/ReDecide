from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.analysis_store import (
    analysis_result_path,
    analysis_state_path,
    analysis_store_root,
    load_analysis_result,
    load_analysis_state,
    save_analysis_result,
    save_analysis_state,
)


class AnalysisStoreTests(unittest.TestCase):
    def test_vercel_default_uses_writable_temporary_storage(self) -> None:
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=False):
            os.environ.pop("REDECIDE_ANALYSIS_STORE", None)
            self.assertEqual(
                analysis_store_root(),
                Path(tempfile.gettempdir()) / "redecide" / "analysis",
            )

    def test_state_and_result_round_trip_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_id = "sample:demo/analysis"
            with patch("backend.app.analysis_store.analysis_store_root", return_value=root):
                state_payload = {"status": "running", "progress": 42, "notes": ["α", "β"]}
                result_payload = {"status": "complete", "score": 0.98}

                state_path = save_analysis_state(analysis_id, state_payload)
                result_path = save_analysis_result(analysis_id, result_payload)

                self.assertEqual(state_path, analysis_state_path(analysis_id))
                self.assertEqual(result_path, analysis_result_path(analysis_id))
                self.assertEqual(load_analysis_state(analysis_id), state_payload)
                self.assertEqual(load_analysis_result(analysis_id), result_payload)

                self.assertTrue(state_path.is_file())
                self.assertTrue(result_path.is_file())
                self.assertEqual(sorted(p.name for p in state_path.parent.iterdir()), ["result.json", "state.json"])

    def test_load_rejects_missing_or_non_object_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("backend.app.analysis_store.analysis_store_root", return_value=root):
                with self.assertRaises(FileNotFoundError):
                    load_analysis_state("missing")

                path = analysis_state_path("bad")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("[]", encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_analysis_state("bad")

    def test_safe_analysis_ids_are_encoded_for_filesystem_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_id = "a:b/c?d"
            with patch("backend.app.analysis_store.analysis_store_root", return_value=root):
                saved = save_analysis_result(analysis_id, {"ok": True})

            self.assertTrue(saved.is_file())
            self.assertEqual(saved.parent.name, "a%3Ab%2Fc%3Fd")


if __name__ == "__main__":
    unittest.main()
