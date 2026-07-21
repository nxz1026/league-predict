"""Tests for core.data.parse — data parsing and odds handling."""

from __future__ import annotations

import unittest

from core.data.parse import remove_vig, to_cn


class TestRemoveVig(unittest.TestCase):
    """P1-4 / P2-2: remove_vig with config-based constants."""

    def test_normal_three_way(self):
        h, d, a = remove_vig(0.50, 0.30, 0.27)
        total = h + d + a
        self.assertAlmostEqual(total, 1.0, places=4)
        self.assertGreater(h, a)  # home favorite

    def test_missing_away_fills_from_margin(self):
        h, d, a = remove_vig(0.50, 0.30)
        self.assertIsNotNone(a)
        self.assertGreater(a, 0)

    def test_missing_home_fills_from_margin(self):
        h, d, a = remove_vig(None, 0.30, 0.25)
        self.assertIsNotNone(h)
        self.assertGreater(h, 0)

    def test_none_draw_returns_none(self):
        result = remove_vig(0.50, None, 0.30)
        self.assertEqual(result, (None, None, None))

    def test_all_none_returns_none(self):
        result = remove_vig(None, None, None)
        self.assertEqual(result, (None, None, None))


class TestToCn(unittest.TestCase):
    """Test Chinese name mapping."""

    def test_known_team(self):
        self.assertIn(to_cn("Arsenal"), ["阿森纳", "Arsenal"])

    def test_unknown_team_passthrough(self):
        self.assertEqual(to_cn("UnknownTeamXYZ"), "UnknownTeamXYZ")

    def test_empty_input(self):
        self.assertEqual(to_cn(""), "")


class TestParseScoreHelper(unittest.TestCase):
    """P2-4: _parse_score helper from calibration module."""

    def test_normal_score(self):
        from core.calibration import _parse_score
        self.assertEqual(_parse_score("2-1"), (2, 1))

    def test_zero_zero(self):
        from core.calibration import _parse_score
        self.assertEqual(_parse_score("0-0"), (0, 0))

    def test_none_input(self):
        from core.calibration import _parse_score
        self.assertIsNone(_parse_score(None))

    def test_invalid_format(self):
        from core.calibration import _parse_score
        self.assertIsNone(_parse_score("abc"))
        self.assertIsNone(_parse_score(""))
        self.assertIsNone(_parse_score("2"))
