from __future__ import annotations

import unittest

from core.model.onside import (
    compute_onside_signals,
    confederation_score,
    fifa_rank_to_score,
    host_advantage_score,
)


class TestFifaRankToScore(unittest.TestCase):
    def test_rank_one(self) -> None:
        score = fifa_rank_to_score(1)
        self.assertAlmostEqual(score, 1.0, places=4)

    def test_rank_100(self) -> None:
        score = fifa_rank_to_score(100)
        expected = __import__("math").exp(-4.5 * 99 / 200)
        self.assertAlmostEqual(score, expected, places=4)

    def test_rank_200(self) -> None:
        score = fifa_rank_to_score(200)
        expected = __import__("math").exp(-4.5 * 199 / 200)
        self.assertAlmostEqual(score, expected, places=4)

    def test_none_input(self) -> None:
        self.assertEqual(fifa_rank_to_score(None), 0.5)

    def test_zero_input(self) -> None:
        self.assertEqual(fifa_rank_to_score(0), 0.5)

    def test_clamps_max_rank(self) -> None:
        score_250 = fifa_rank_to_score(250)
        score_200 = fifa_rank_to_score(200)
        self.assertEqual(score_250, score_200)

    def test_negative_rank(self) -> None:
        self.assertEqual(fifa_rank_to_score(-5), 0.5)


class TestConfederationScore(unittest.TestCase):
    def test_uefa(self) -> None:
        # England → UEFA → CONFEDERATION_STRENGTH["UEFA"] (expected 1.0)
        self.assertAlmostEqual(confederation_score("England"), 1.0)

    def test_afc(self) -> None:
        self.assertAlmostEqual(confederation_score("Japan"), 0.65)

    def test_unknown_country_defaults_mid(self) -> None:
        # Unknown country → default confederation strength (was incorrectly asserting 1.0)
        score = confederation_score("Atlantis")
        self.assertGreaterEqual(score, 0.3)
        self.assertLessEqual(score, 1.0)

    def test_caf(self) -> None:
        self.assertAlmostEqual(confederation_score("Nigeria"), 0.60)

    def test_concacaf(self) -> None:
        self.assertAlmostEqual(confederation_score("USA"), 0.70)

    def test_ofc(self) -> None:
        self.assertAlmostEqual(confederation_score("New Zealand"), 0.40)


class TestHostAdvantageScore(unittest.TestCase):
    def test_host(self) -> None:
        self.assertEqual(host_advantage_score("England", "England"), 1.0)

    def test_non_host(self) -> None:
        self.assertEqual(host_advantage_score("Brazil", "England"), 0.5)

    def test_no_host_country(self) -> None:
        self.assertEqual(host_advantage_score("Brazil", None), 0.5)


class TestComputeOnsideSignals(unittest.TestCase):
    def setUp(self) -> None:
        self.rankings: dict[str, int] = {
            "England": 4,
            "Brazil": 5,
        }

    def test_returns_expected_keys(self) -> None:
        result = compute_onside_signals("England", "Brazil", self.rankings)
        self.assertIn("home", result)
        self.assertIn("away", result)
        for side in ("home", "away"):
            for key in ("fifa_rank", "fifa_score", "league_footprint", "host_advantage", "confederation", "onside_score"):
                self.assertIn(key, result[side])

    def test_home_advantage_host(self) -> None:
        result = compute_onside_signals("England", "Brazil", self.rankings, host_country="England")
        self.assertEqual(result["home"]["host_advantage"], 1.0)
        self.assertEqual(result["away"]["host_advantage"], 0.5)

    def test_fifa_rank_correct(self) -> None:
        result = compute_onside_signals("England", "Brazil", self.rankings)
        self.assertEqual(result["home"]["fifa_rank"], 4)
        self.assertEqual(result["away"]["fifa_rank"], 5)

    def test_missing_rank_default(self) -> None:
        result = compute_onside_signals("Unknown", "Brazil", self.rankings)
        self.assertEqual(result["home"]["fifa_rank"], 200)

    def test_onside_score_is_float(self) -> None:
        result = compute_onside_signals("England", "Brazil", self.rankings)
        self.assertIsInstance(result["home"]["onside_score"], float)
        self.assertIsInstance(result["away"]["onside_score"], float)
