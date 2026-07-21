"""Tests for calibration module (P1-5: 补充核心路径覆盖)"""

import unittest
import tempfile
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from core.calibration import compute_calibration_offset, build_calibration, _parse_score


class TestParseScore(unittest.TestCase):
    def test_normal_score(self):
        self.assertEqual(_parse_score("2-1"), (2, 1))

    def test_zero_score(self):
        self.assertEqual(_parse_score("0-0"), (0, 0))

    def test_high_score(self):
        self.assertEqual(_parse_score("5-4"), (5, 4))

    def test_none_input(self):
        self.assertIsNone(_parse_score(None))

    def test_empty_string(self):
        self.assertIsNone(_parse_score(""))

    def test_no_dash(self):
        self.assertIsNone(_parse_score("21"))

    def test_non_numeric(self):
        self.assertIsNone(_parse_score("a-b"))


class TestComputeCalibrationOffset(unittest.TestCase):
    def test_insufficient_data(self):
        past = [{"score": "1-0"}, {"score": "2-1"}]
        self.assertIsNone(compute_calibration_offset(past))

    def test_balanced_distribution(self):
        past = [
            {"score": "1-0"}, {"score": "0-1"},
            {"score": "1-1"}, {"score": "2-1"}, {"score": "0-1"},
        ]
        offset = compute_calibration_offset(past)
        self.assertIsNotNone(offset)
        self.assertIn("home_correction", offset)
        self.assertEqual(offset["sample_size"], 5)

    def test_home_heavy_bias(self):
        past = [{"score": f"{i}-0"} for i in range(1, 6)]
        offset = compute_calibration_offset(past)
        self.assertIsNotNone(offset)
        self.assertGreater(offset["home_correction"], 1.0)

    def test_output_keys_include_onside(self):
        past = [
            {"score": "2-1"}, {"score": "1-2"}, {"score": "1-1"},
            {"score": "3-0"}, {"score": "0-3"}, {"score": "2-2"},
        ]
        offset = compute_calibration_offset(past)
        expected_keys = {
            "home_correction", "draw_correction", "away_correction",
            "onside_home_correction", "onside_away_correction",
            "sample_size", "sample_weight",
        }
        for key in expected_keys:
            self.assertIn(key, offset)


class TestBuildCalibration(unittest.TestCase):
    def test_empty_past(self):
        result = build_calibration([], [])
        self.assertIn("note", result)

    def test_with_matches(self):
        past = [
            {"score": "2-1", "home_true_prob": 0.6},
            {"score": "1-2", "home_true_prob": 0.3},
            {"score": "1-1", "home_true_prob": 0.5},
        ]
        result = build_calibration(past, [])
        self.assertEqual(result["total_matches"], 3)


if __name__ == "__main__":
    unittest.main()
