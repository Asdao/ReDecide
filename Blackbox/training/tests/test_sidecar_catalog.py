import unittest
from datetime import date

from Blackbox.training.sidecar_catalog import SidecarCandidate, select_balanced_candidates


class SidecarCatalogTests(unittest.TestCase):
    def test_selection_balances_maps_before_taking_second_from_one_map(self) -> None:
        candidates = [
            SidecarCandidate(f"a-{index}.analysis.json", "de_ancient", 20, 100, 1, date.max, 10)
            for index in range(3)
        ] + [
            SidecarCandidate("nuke.analysis.json", "de_nuke", 20, 100, 0, date.min, 10)
        ]
        selected = select_balanced_candidates(candidates, max_files=2)
        self.assertEqual({candidate.map_name for candidate in selected}, {"de_ancient", "de_nuke"})

    def test_selection_respects_estimated_byte_budget(self) -> None:
        candidates = [
            SidecarCandidate("a.analysis.json", "de_ancient", 20, 100, 1, date.max, 8),
            SidecarCandidate("n.analysis.json", "de_nuke", 20, 100, 1, date.max, 8),
        ]
        self.assertEqual(len(select_balanced_candidates(candidates, max_bytes=10)), 1)
