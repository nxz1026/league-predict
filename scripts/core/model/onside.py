from __future__ import annotations

"""Onside 4+1 signal model: FIFA rankings, league footprint, host advantage, confederation strength."""

import json
import math
from pathlib import Path
from typing import Any

from core.config import CONFEDERATION_STRENGTH, COUNTRY_CONFEDERATION, ONSIDE_WEIGHTS
from core.log import logger

# 统一从 data.fetch 导入，避免两处实现漂移
from core.data.fetch import fetch_fifa_rankings


def fifa_rank_to_score(rank: int | None, max_rank: int = 200) -> float:
    if not rank or rank <= 0:
        return 0.5
    rank = min(rank, max_rank)
    score = math.exp(-3.0 * (rank - 1) / max_rank)
    return max(0.0, min(1.0, score))


def get_confederation(country_name: str) -> str:
    return COUNTRY_CONFEDERATION.get(country_name, "UEFA")


def confederation_score(country_name: str) -> float:
    conf = get_confederation(country_name)
    return CONFEDERATION_STRENGTH.get(conf, 0.5)


def league_footprint_score(country_name: str, fifa_rank: int | None = None) -> float:
    if fifa_rank and fifa_rank > 0:
        if fifa_rank <= 10:
            return 1.0
        elif fifa_rank <= 30:
            return 0.8
        elif fifa_rank <= 60:
            return 0.6
        elif fifa_rank <= 100:
            return 0.4
        else:
            return 0.2
    conf = get_confederation(country_name)
    if conf in ("UEFA", "CONMEBOL"):
        return 0.7
    elif conf in ("AFC", "CAF", "CONCACAF"):
        return 0.5
    else:
        return 0.3


def host_advantage_score(country_name: str, host_country: str | None) -> float:
    if host_country and country_name == host_country:
        return 1.0
    return 0.5


def compute_onside_signals(home_team: str, away_team: str, fifa_rankings: dict[str, int], host_country: str | None = None) -> dict[str, Any]:
    home_rank = fifa_rankings.get(home_team, 100)
    away_rank = fifa_rankings.get(away_team, 100)

    home_fifa = fifa_rank_to_score(home_rank)
    away_fifa = fifa_rank_to_score(away_rank)

    home_league = league_footprint_score(home_team, home_rank)
    away_league = league_footprint_score(away_team, away_rank)

    home_host = host_advantage_score(home_team, host_country)
    away_host = host_advantage_score(away_team, host_country)

    home_conf = confederation_score(home_team)
    away_conf = confederation_score(away_team)

    w = ONSIDE_WEIGHTS
    home_onside = (
        home_fifa * w["fifa_ranking"]
        + home_league * w["league_footprint"]
        + home_host * w["host_advantage"]
        + home_conf * w["confederation"]
    )
    away_onside = (
        away_fifa * w["fifa_ranking"]
        + away_league * w["league_footprint"]
        + away_host * w["host_advantage"]
        + away_conf * w["confederation"]
    )

    return {
        "home": {
            "fifa_rank": home_rank,
            "fifa_score": round(home_fifa, 3),
            "league_footprint": round(home_league, 3),
            "host_advantage": round(home_host, 3),
            "confederation": round(home_conf, 3),
            "onside_score": round(home_onside, 3),
        },
        "away": {
            "fifa_rank": away_rank,
            "fifa_score": round(away_fifa, 3),
            "league_footprint": round(away_league, 3),
            "host_advantage": round(away_host, 3),
            "confederation": round(away_conf, 3),
            "onside_score": round(away_onside, 3),
        }
    }
