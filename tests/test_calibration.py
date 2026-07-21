from __future__ import annotations

import unittest

from core.calibration import build_calibration, compute_calibration_offset


class TestComputeCalibrationOffset(unittest.TestCase):
    def test_few_matches_returns_none(self) -> None:
        matches = [{"score": "1-0"}, {"score": "2-1"}]
        self.assertIsNone(compute_calibration_offset(matches))

    def test_balanced(self) -> None:
        matches = [
            {"score": "2-0"},
            {"score": "1-1"},
            {"score": "0-2"},
            {"score": "3-1"},
            {"score": "0-0"},
            {"score": "1-3"},
        ]
        result = compute_calibration_offset(matches)
        self.assertIsNotNone(result)
        if result:
            self.assertAlmostEqual(result["actual_home_rate"], 2 / 6, places=3)
            self.assertAlmostEqual(result["actual_draw_rate"], 2 / 6, places=3)
            self.assertAlmostEqual(result["actual_away_rate"], 2 / 6, places=3)
            self.assertAlmostEqual(result["home_correction"], (2 / 6) / (1 / 3), places=3)
            self.assertAlmostEqual(result["draw_correction"], (2 / 6) / (1 / 3), places=3)
            self.assertAlmostEqual(result["away_correction"], (2 / 6) / (1 / 3), places=3)
            self.assertEqual(result["sample_size"], 6)

    def test_all_home_wins(self) -> None:
        matches = [{"score": f"{i+1}-0"} for i in range(10)]
        result = compute_calibration_offset(matches)
        self.assertIsNotNone(result)
        if result:
            self.assertAlmostEqual(result["actual_home_rate"], 1.0, places=3)
            self.assertAlmostEqual(result["home_correction"], 2.0, places=3)

    def test_handles_invalid_scores(self) -> None:
        matches = [
            {"score": "abc"},
            {"score": None},
            {"score": ""},
            {"score": "2-0"},
            {"score": "1-1"},
            {"score": "0-0"},
            {"score": "3-1"},
            {"score": "1-2"},
        ]
        result = compute_calibration_offset(matches)
        self.assertIsNotNone(result)
        if result:
            self.assertEqual(result["sample_size"], 5)

    def test_insufficient_valid_scores(self) -> None:
        matches = [
            {"score": "abc"},
            {"score": None},
            {"score": "invalid"},
        ]
        result = compute_calibration_offset(matches)
        self.assertIsNone(result)


class TestBuildCalibration(unittest.TestCase):
    def test_empty_past(self) -> None:
        result = build_calibration([], [])
        self.assertEqual(result["note"], "no past matches to calibrate from")

    def test_basic_counts(self) -> None:
        past = [
            {"score": "2-0", "home_true_prob": 0.5},
            {"score": "1-1", "home_true_prob": 0.4},
            {"score": "0-2", "home_true_prob": 0.3},
            {"score": "3-0", "home_true_prob": 0.6},
        ]
        result = build_calibration(past, [])
        self.assertEqual(result["home_wins"], 2)
        self.assertEqual(result["draws"], 1)
        self.assertEqual(result["away_wins"], 1)
        self.assertEqual(result["total_matches"], 4)
        self.assertAlmostEqual(result["home_win_rate"], 0.5, places=3)

    def test_odds_accuracy(self) -> None:
        past = [
            {"score": "2-0", "home_true_prob": 0.6},
            {"score": "1-1", "home_true_prob": 0.55},
            {"score": "0-2", "home_true_prob": 0.3},
        ]
        result = build_calibration(past, [])
        self.assertEqual(result["favored_by_odds"], 2)
        self.assertEqual(result["favored_won"], 1)

    def test_no_favored(self) -> None:
        past = [
            {"score": "2-0", "home_true_prob": 0.4},
            {"score": "1-0", "home_true_prob": 0.3},
        ]
        result = build_calibration(past, [])
        self.assertEqual(result["favored_by_odds"], 0)
        self.assertEqual(result["odds_accuracy"], 0)
