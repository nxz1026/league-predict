from __future__ import annotations

"""Poisson and Dixon-Coles bivariate Poisson models for score prediction."""

import math
from typing import Any

from core.log import logger


def poisson_confidence_interval(lam: float, confidence: float = 0.95) -> tuple[float, float]:
    if lam <= 0:
        return (0, 0)
    if lam >= 10:
        z = 1.96
        lower = max(0, lam - z * math.sqrt(lam))
        upper = lam + z * math.sqrt(lam)
    else:
        lower = max(0, lam - 1.96 * math.sqrt(lam + 0.5))
        upper = lam + 1.96 * math.sqrt(lam + 0.5)
    return (round(lower, 1), round(upper, 1))


def poisson_pmf(k: int, lam: float) -> float:
    if k < 0:
        return 0.0
    if lam <= 0:
        return 0.0 if k > 0 else 1.0
    log_p = k * math.log(lam) - lam - math.lgamma(k + 1)
    return math.exp(log_p)


def tau_correction(home_goals: int, away_goals: int, lambda_h: float, lambda_a: float, rho: float = 0.2) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - rho
    elif home_goals == 1 and away_goals == 0:
        return 1.0 + rho * lambda_a
    elif home_goals == 0 and away_goals == 1:
        return 1.0 + rho * lambda_h
    elif home_goals == 1 and away_goals == 1:
        return 1.0 - rho * lambda_h * lambda_a
    else:
        return 1.0


def dixon_coles_pmf(home_goals: int, away_goals: int, lambda_h: float, lambda_a: float, rho: float = 0.2) -> float:
    base_prob = poisson_pmf(home_goals, lambda_h) * poisson_pmf(away_goals, lambda_a)
    tau = tau_correction(home_goals, away_goals, lambda_h, lambda_a, rho)
    return base_prob * tau


def dixon_coles_match_probs(lambda_h: float, lambda_a: float, rho: float = 0.2, max_goals: int = 8,
                            mode: str = "full") -> dict[str, Any]:
    """Dixon-Coles 比赛概率计算。

    Args:
        mode: "full" 计算完整比分矩阵(81项), "summary" 仅返回 home/draw/away 概率（更快）
    """
    score_probs: list[tuple[int, int, float]] = []
    home_win_p = 0.0
    draw_p = 0.0
    away_win_p = 0.0

    if mode == "summary":
        # 仅计算胜负平概率，提前剪枝低概率比分
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = dixon_coles_pmf(h, a, lambda_h, lambda_a, rho)
                if p > 0.0001:
                    if h > a:
                        home_win_p += p
                    elif h == a:
                        draw_p += p
                    else:
                        away_win_p += p
    else:
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = dixon_coles_pmf(h, a, lambda_h, lambda_a, rho)
                if p > 0.0001:
                    score_probs.append((h, a, p))
                    if h > a:
                        home_win_p += p
                    elif h == a:
                        draw_p += p
                    else:
                        away_win_p += p

    total = home_win_p + draw_p + away_win_p
    if total > 0:
        home_win_p /= total
        draw_p /= total
        away_win_p /= total

    result: dict[str, Any] = {
        "home_win": round(home_win_p, 4),
        "draw": round(draw_p, 4),
        "away_win": round(away_win_p, 4),
    }
    if mode == "full":
        score_probs.sort(key=lambda x: -x[2])
        result["score_probs"] = score_probs[:12]

    return result


def fit_dc_rho(past_matches: list[dict[str, Any]], rho_min: float = -0.3, rho_max: float = 0.5, step: float = 0.005) -> float:
    scores: list[tuple[int, int]] = []
    for m in past_matches:
        score = m.get("score") or m.get("result", "")
        if not score or "-" not in str(score):
            continue
        try:
            parts = str(score).split("-")
            h, a = int(parts[0]), int(parts[1])
            scores.append((h, a))
        except (ValueError, IndexError):
            continue

    n = len(scores)
    if n < 20:
        logger.info(f"rho fit: only {n} matches with scores (need 20+), using default rho=0.2")
        return 0.2

    adaptive_step = step * math.sqrt(100.0 / n)

    all_h = [s[0] for s in scores]
    all_a = [s[1] for s in scores]
    avg_h = sum(all_h) / n
    avg_a = sum(all_a) / n

    # ── 三分搜索优化（P3-1）：似然函数单峰，O(log N) 替代 O(N×steps）───
    def _neg_log_likelihood(rho_val: float) -> float:
        ll = 0.0
        for h, a in scores:
            p = dixon_coles_pmf(h, a, avg_h, avg_a, rho_val)
            if p > 1e-10:
                ll += math.log(p)
        return -ll

    # 先用粗网格找大致范围，再用三分搜索精化
    best_rho = 0.2
    best_ll = -float("inf")
    rho = rho_min
    while rho <= rho_max:
        ll = -_neg_log_likelihood(rho)
        if ll > best_ll:
            best_ll = ll
            best_rho = rho
        rho += adaptive_step

    # 三分搜索精化（在最佳值附近 ±adaptive_step 范围内）
    lo = max(rho_min, best_rho - 10 * adaptive_step)
    hi = min(rho_max, best_rho + 10 * adaptive_step)

    for _ in range(50):  # ~50次迭代，精度足够
        if hi - lo < 1e-6:
            break
        mid1 = lo + (hi - lo) / 3
        mid2 = hi - (hi - lo) / 3
        if _neg_log_likelihood(mid1) < _neg_log_likelihood(mid2):
            hi = mid2
        else:
            lo = mid1

    final_rho = (lo + hi) / 2
    # 确保三分搜索结果不比网格搜索差
    if -_neg_log_likelihood(final_rho) < best_ll:
        final_rho = best_rho

    logger.info(f"rho fit: {n} matches, lambda_h={avg_h:.2f} lambda_a={avg_a:.2f}, "
                f"rho={final_rho:.3f} (LL={-_neg_log_likelihood(final_rho):.1f})")
    return round(final_rho, 3)
