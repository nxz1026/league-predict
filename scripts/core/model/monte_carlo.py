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

    # ── 标准 World Cup 淘汰赛对阵 ──
    # 8 组 (A-H)，每组前2名晋级，16强对阵：
    # A1 v B2, C1 v D2, E1 v F2, G1 v H2,
    # B1 v A2, D1 v C2, F1 v E2, H1 v G2
    _KNOCKOUT_PAIRING = [
        (0, 1),  # A1 vs B2
        (2, 3),  # C1 vs D2
        (4, 5),  # E1 vs F2
        (6, 7),  # G1 vs H2
        (1, 0),  # B1 vs A2
        (3, 2),  # D1 vs C2
        (5, 4),  # F1 vs E2
        (7, 6),  # H1 vs G2
    ]

    # 构建淘汰赛队伍列表：[A1, A2, B1, B2, C1, C2, ...]
    group_order = sorted(group_standings.keys())
    seeded: list[str] = []
    for gn in group_order:
        advanced = group_standings[gn][:2]
        seeded.extend(advanced)

    if len(seeded) >= 16:
        # 按标准对阵配对
        r16_matchups: list[tuple[str, str]] = []
        for first_idx, second_idx in _KNOCKOUT_PAIRING:
            # first_idx: 组号（0=A,1=B...），取该组第1名
            # second_idx: 组号，取该组第2名
            t1 = seeded[first_idx * 2]      # 组 first_idx 的第1名
            t2 = seeded[second_idx * 2 + 1]  # 组 second_idx 的第2名
            r16_matchups.append((t1, t2))

        remaining_teams = _simulate_knockout_bracket(r16_matchups, team_strengths, rho, team_rounds)
    elif len(seeded) >= 2:
        # 组数不足 8 组（种子不足 16 强）时，退化为顺序配对：
        # 汇总所有组的晋级队，按顺序两两淘汰（修复：此前 remaining_teams
        # 永远为空列表，该分支恒不可达，冠军静默为 None）
        for group_name in sorted(group_standings.keys()):
            advanced = group_standings[group_name][:2]
            remaining_teams.extend(advanced)
        remaining_teams = _simulate_knockout_sequential(remaining_teams, team_strengths, rho, team_rounds)
    else:
        remaining_teams = []
        logger.warning("simulate_world_cup: 晋级队伍不足 2 支，无法模拟淘汰赛，冠军为 None")

    champion = remaining_teams[0] if remaining_teams else None

    return {
        "champion": champion,
        "team_rounds": team_rounds,
    }


def _simulate_knockout_bracket(
    matchups: list[tuple[str, str]],
    team_strengths: dict[str, dict[str, float]],
    rho: float,
    team_rounds: dict[str, list[str]],
) -> list[str]:
    """按给定对阵表模拟淘汰赛，返回冠军队伍列表。"""
    round_names = {16: "round_of_16", 8: "quarter_final", 4: "semi_final", 2: "final"}

    current_matchups = matchups
    while len(current_matchups) >= 1:
        n_teams = len(current_matchups) * 2
        round_name = round_names.get(n_teams, f"r{n_teams}")
        next_matchups: list[tuple[str, str]] = []

        for t1, t2 in current_matchups:
            lh = team_strengths.get(t1, {}).get("lambda_home", 1.5)
            la = team_strengths.get(t2, {}).get("lambda_away", 1.2)
            hg, ag = simulate_match_dc(lh, la, rho)

            if hg == ag:
                winner = t1 if random.random() < 0.5 else t2
            elif hg > ag:
                winner = t1
            else:
                winner = t2

            if winner not in team_rounds:
                team_rounds[winner] = []
            team_rounds[winner].append(round_name)

            # 将胜者配对进入下一轮
            if not next_matchups or len(next_matchups[-1]) == 2:
                next_matchups.append((winner,))
            else:
                next_matchups[-1] = (next_matchups[-1][0], winner)

        # 如果只剩1场（决赛），冠军已决出
        if len(current_matchups) == 1:
            return [current_matchups[0][0] if isinstance(current_matchups[0], tuple) and len(current_matchups[0]) == 1 else winner]

        current_matchups = next_matchups

    return []


def _simulate_knockout_sequential(
    remaining_teams: list[str],
    team_strengths: dict[str, dict[str, float]],
    rho: float,
    team_rounds: dict[str, list[str]],
) -> list[str]:
    """顺序配对模拟淘汰赛（组数不足8组时的退化方案）。"""
    while len(remaining_teams) > 1:
        next_round_teams: list[str] = []
        round_name = f"r{len(remaining_teams)}"
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

                if winner not in team_rounds:
                    team_rounds[winner] = []
                team_rounds[winner].append(round_name)
            else:
                next_round_teams.append(remaining_teams[i])

        remaining_teams = next_round_teams

    return remaining_teams


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
