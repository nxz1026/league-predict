from __future__ import annotations

"""Monte Carlo tournament/league simulation using Dixon-Coles model."""

import random
from typing import Any

from core.log import logger
from core.model.poisson import dixon_coles_pmf


def simulate_match_dc(lambda_h: float, lambda_a: float, rho: float = 0.2) -> tuple[int, int]:
    """用 Dixon-Coles 联合泊松模拟单场比分"""
    from core.model.poisson import dixon_coles_pmf
    from core.config import MAX_GOALS_MC

    _max_g = MAX_GOALS_MC  # 统一范围常量（与 poisson.py dixon_coles_match_probs 一致）
    probs: list[tuple[int, int, float]] = []
    for h in range(_max_g):
        for a in range(_max_g):
            p = dixon_coles_pmf(h, a, lambda_h, lambda_a, rho)
            probs.append((h, a, p))

    total_p = sum(p[2] for p in probs)
    if total_p > 0:
        probs = [(h, a, p / total_p) for h, a, p in probs]

    r = random.random()
    cumulative = 0.0
    for h, a, p in probs:
        cumulative += p
        if r <= cumulative:
            return h, a

    return 0, 0


def monte_carlo_champion(
    fixtures: list[dict[str, Any]],
    team_strengths: dict[str, dict[str, float]],
    n_simulations: int = 10000,
    rho: float = 0.2,
    tournament_type: str = "world_cup",
) -> dict[str, Any]:
    logger.info(f"Starting Monte Carlo simulation: {n_simulations} iterations, type={tournament_type}")

    champion_counts: dict[str, int] = {}
    round_reach_counts: dict[str, dict[str, int]] = {}

    all_teams: set[str] = set()
    for f in fixtures:
        all_teams.add(f.get("home", ""))
        all_teams.add(f.get("away", ""))

    for team in all_teams:
        champion_counts[team] = 0
        round_reach_counts[team] = {}

    for sim in range(n_simulations):
        if sim % 2000 == 0 and sim > 0:
            logger.info(f"  Simulation {sim}/{n_simulations}...")

        if tournament_type == "world_cup":
            result = simulate_world_cup(fixtures, team_strengths, rho)
        else:
            result = simulate_league(fixtures, team_strengths, rho)

        champion = result.get("champion")
        if champion:
            champion_counts[champion] = champion_counts.get(champion, 0) + 1

        for team, rounds in result.get("team_rounds", {}).items():
            for round_name in rounds:
                if round_name not in round_reach_counts[team]:
                    round_reach_counts[team][round_name] = 0
                round_reach_counts[team][round_name] += 1

    champion_probs = {team: round(count / n_simulations, 4)
                      for team, count in champion_counts.items() if count > 0}
    champion_probs = dict(sorted(champion_probs.items(), key=lambda x: -x[1]))

    round_reach_probs: dict[str, dict[str, float]] = {}
    for team, rounds in round_reach_counts.items():
        for round_name, count in rounds.items():
            if round_name not in round_reach_probs:
                round_reach_probs[round_name] = {}
            round_reach_probs[round_name][team] = round(count / n_simulations, 4)

    for round_name in round_reach_probs:
        round_reach_probs[round_name] = dict(
            sorted(round_reach_probs[round_name].items(), key=lambda x: -x[1])
        )

    return {
        "champion_probs": champion_probs,
        "round_reach_probs": round_reach_probs,
        "simulation_count": n_simulations,
        "model": "dixon_coles",
        "rho": rho,
        # P2-C 新增: 收敛性诊断 — 标准误估计
        "convergence_diagnostics": _compute_se(champion_counts, n_simulations),
    }


def _compute_se(champion_counts: dict[str, int], n_simulations: int) -> dict[str, Any]:
    """计算每个队伍冠军概率的标准误（P2-C）。

    SE = sqrt(p_hat * (1 - p_hat) / n)
    用于判断模拟次数是否足够（SE < 0.01 为理想精度）。
    """
    import math as _math
    diagnostics: dict[str, Any] = {}
    for team, count in champion_counts.items():
        p_hat = count / n_simulations
        se = _math.sqrt(p_hat * (1 - p_hat) / n_simulations)
        ci_lo = max(0.0, p_hat - 1.96 * se)
        ci_hi = min(1.0, p_hat + 1.96 * se)
        diagnostics[team] = {
            "count": count,
            "probability": round(p_hat, 4),
            "std_error": round(se, 5),
            "ci_95_lower": round(ci_lo, 4),
            "ci_95_upper": round(ci_hi, 4),
        }
    # 全局收敛指标
    all_se = [d["std_error"] for d in diagnostics.values()]
    diagnostics["_summary"] = {
        "max_std_error": round(max(all_se), 5) if all_se else 0.0,
        "avg_std_error": round(sum(all_se) / len(all_se), 5) if all_se else 0.0,
        "teams_with_se_above_1pct": sum(1 for s in all_se if s > 0.01),
        "n_simulations": n_simulations,
    }
    return diagnostics


def simulate_world_cup(fixtures: list[dict[str, Any]], team_strengths: dict[str, dict[str, float]], rho: float) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    knockout: list[dict[str, Any]] = []

    for f in fixtures:
        stage = f.get("stage", "group")
        if stage == "group":
            group_name = f.get("group", "A")
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(f)
        else:
            knockout.append(f)

    group_standings: dict[str, list[str]] = {}
    team_rounds: dict[str, list[str]] = {}

    for group_name, group_fixtures in groups.items():
        teams_in_group: set[str] = set()
        for f in group_fixtures:
            teams_in_group.add(f["home"])
            teams_in_group.add(f["away"])

        standings: dict[str, dict[str, int]] = {team: {"points": 0, "gf": 0, "ga": 0, "gd": 0} for team in teams_in_group}

        for f in group_fixtures:
            home = f["home"]
            away = f["away"]

            lh = team_strengths.get(home, {}).get("lambda_home", 1.5)
            la = team_strengths.get(away, {}).get("lambda_away", 1.2)

            hg, ag = simulate_match_dc(lh, la, rho)

            standings[home]["gf"] += hg
            standings[home]["ga"] += ag
            standings[home]["gd"] += hg - ag
            standings[away]["gf"] += ag
            standings[away]["ga"] += hg
            standings[away]["gd"] += ag - hg

            if hg > ag:
                standings[home]["points"] += 3
            elif hg == ag:
                standings[home]["points"] += 1
                standings[away]["points"] += 1
            else:
                standings[away]["points"] += 3

        sorted_teams = sorted(standings.keys(),
                              key=lambda t: (standings[t]["points"], standings[t]["gd"], standings[t]["gf"]),
                              reverse=True)

        group_standings[group_name] = sorted_teams

        for team in teams_in_group:
            if team not in team_rounds:
                team_rounds[team] = []
            team_rounds[team].append("group_stage")

        advanced = sorted_teams[:2]
        for team in advanced:
            if team not in team_rounds:
                team_rounds[team] = []
            team_rounds[team].append("round_of_16")

    current_round = "round_of_16"
    remaining_teams: list[str] = []

    for group_name in sorted(group_standings.keys()):
        advanced = group_standings[group_name][:2]
        remaining_teams.extend(advanced)

    if not knockout and len(remaining_teams) >= 2:
        while len(remaining_teams) > 1:
            next_round_teams: list[str] = []
            for i in range(0, len(remaining_teams), 2):
                if i + 1 < len(remaining_teams):
                    t1 = remaining_teams[i]
                    t2 = remaining_teams[i + 1]

                    lh = team_strengths.get(t1, {}).get("lambda_home", 1.5)
                    la = team_strengths.get(t2, {}).get("lambda_away", 1.2)

                    hg, ag = simulate_match_dc(lh, la, rho)

                    if hg == ag:
                        winner = t1 if random.random() < 0.5 else t2
                    elif hg > ag:
                        winner = t1
                    else:
                        winner = t2

                    next_round_teams.append(winner)

                    round_name = f"r{len(remaining_teams)}"
                    if winner not in team_rounds:
                        team_rounds[winner] = []
                    team_rounds[winner].append(round_name)
                else:
                    next_round_teams.append(remaining_teams[i])

            remaining_teams = next_round_teams
            if len(remaining_teams) > 1:
                current_round = f"r{len(remaining_teams)}"

    champion = remaining_teams[0] if remaining_teams else None

    return {
        "champion": champion,
        "team_rounds": team_rounds,
    }


def simulate_league(fixtures: list[dict[str, Any]], team_strengths: dict[str, dict[str, float]], rho: float) -> dict[str, Any]:
    standings: dict[str, dict[str, int]] = {}

    for f in fixtures:
        home = f["home"]
        away = f["away"]

        if home not in standings:
            standings[home] = {"points": 0, "gf": 0, "ga": 0, "gd": 0}
        if away not in standings:
            standings[away] = {"points": 0, "gf": 0, "ga": 0, "gd": 0}

        lh = team_strengths.get(home, {}).get("lambda_home", 1.5)
        la = team_strengths.get(away, {}).get("lambda_away", 1.2)

        hg, ag = simulate_match_dc(lh, la, rho)

        standings[home]["gf"] += hg
        standings[home]["ga"] += ag
        standings[home]["gd"] += hg - ag
        standings[away]["gf"] += ag
        standings[away]["ga"] += hg
        standings[away]["gd"] += ag - hg

        if hg > ag:
            standings[home]["points"] += 3
        elif hg == ag:
            standings[home]["points"] += 1
            standings[away]["points"] += 1
        else:
            standings[away]["points"] += 3

    sorted_teams = sorted(standings.keys(),
                          key=lambda t: (standings[t]["points"], standings[t]["gd"], standings[t]["gf"]),
                          reverse=True)

    champion = sorted_teams[0] if sorted_teams else None

    team_rounds: dict[str, list[str]] = {}
    for team in standings:
        team_rounds[team] = ["season"]

    return {
        "champion": champion,
        "team_rounds": team_rounds,
    }
