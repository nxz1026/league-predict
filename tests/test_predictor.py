"""Tests for core.predictor — prediction calculation logic.

Uses mock data to avoid network calls.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestCalculatePrediction(unittest.TestCase):
    """P4-1: Core prediction function smoke tests."""

    def _make_match(self, **overrides):
        base = {
            "home": "Brazil",
            "away": "Argentina",
            "home_prob": 0.55,
            "draw_prob": 0.25,
            "away_prob": 0.20,
            "odds_data_available": True,
        }
        base.update(overrides)
        return base

    @patch("core.predictor.compute_onside_signals")
    def test_direction_home_favorite(self, mock_onside):
        mock_onside.return_value = {
            "home": {"onside_score": 0.7},
            "away": {"onside_score": 0.4},
        }
        from core.predictor import calculate_prediction
        match = self._make_match(home_prob=0.55, draw_prob=0.22, away_prob=0.23)
        result = calculate_prediction(match, use_dixon_coles=False)
        self.assertIn("direction", result)
        self.assertIn("confidence_score", result)
        self.assertIn("stars", result)
        # Home favorite should predict home win or draw
        self.assertIn(result["direction"], [f"{match['home']} 胜", "平局", f"{match['home']} 胜 (接近)", "平局 (接近)"])

    @patch("core.predictor.compute_onside_signals")
    def test_no_odds_penalty_applied(self, mock_onside):
        mock_onside.return_value = {
            "home": {"onside_score": 0.6},
            "away": {"onside_score": 0.6},
        }
        from core.predictor import calculate_prediction
        match = self._make_match(odds_data_available=False)
        result = calculate_prediction(match, use_dixon_coles=False)
        # Without odds, confidence should be penalized
        self.assertIn("confidence_note", result)


class TestThresholdConstants(unittest.TestCase):
    """P2-2: Verify THRESHOLDS config is loaded correctly."""

    def test_thresholds_exist(self):
        from core.config import THRESHOLDS
        expected_keys = [
            "direction_min_prob", "direction_odds_ratio", "draw_threshold",
            "star_5", "star_4", "star_3", "star_2",
            "lambda_multiplier", "lambda_lower_bound",
        ]
        for key in expected_keys:
            self.assertIn(key, THRESHOLDS)

    def test_star_ordering(self):
        from core.config import THRESHOLDS
        self.assertGreater(THRESHOLDS["star_5"], THRESHOLDS["star_4"])
        self.assertGreater(THRESHOLDS["star_4"], THRESHOLDS["star_3"])
        self.assertGreater(THRESHOLDS["star_3"], THRESHOLDS["star_2"])
