from __future__ import annotations

"""Core prediction engine: Onside 4+1 signal model combined with Dixon-Coles.

P0-2 修复: 统一 λ 计算与方向预测的权重体系，消除内在矛盾。
"""

import json
from core.config import ONSIDE_WEIGHTS, MARKET_ODDS_WEIGHT, DC_RHO, THRESHOLDS, LEAGUE_DC_RHO
from core.log import logger
# 统一从 core.rankings 导入（P1-3：打破循环依赖）
from core.rankings import fetch_fifa_rankings
from core.model.onside import compute_onside_signals
from core.model.poisson import dixon_coles_match_probs, poisson_pmf, poisson_confidence_interval
from core.elo import expected_score, DEFAULT_ELO


def calculate_prediction(
    match: dict,
    weights: dict | None = None,
    calibration_offset: dict | None = None,
    fifa_rankings: dict | None = None,
    host_country: str | None = None,
    use_dixon_coles: bool = True,
    dc_rho: float | None = None,  # P0-3: 允许 None 以使用联赛差异化 ρ
    elo_ratings: dict[str, float] | None = None,
    league_key: str = "epl",  # P0-3: 传入联赛 key 用于差异化 ρ
) -> dict:
    """
    Onside 4 信号 + ELO + Dixon-Coles 预测 → 方向 + 信心 + 比分预测 + 95% CI

    Args:
        match: 比赛数据字典
        weights: 权重字典（可选，默认 ONSIDE_WEIGHTS）
        calibration_offset: 校准偏移字典
        fifa_rankings: FIFA 排名字典
        host_country: 东道主国家
        use_dixon_coles: 是否使用 Dixon-Coles 模型
        dc_rho: Dixon-Coles ρ 参数，None 时按联赛自动选择 (P0-3)
        elo_ratings: ELO 评分表 {team: elo}，提供则加入信号融合
        league_key: 联赛键名，用于查找联赛特定参数 (P0-3)
    """
    if weights is None:
        weights = ONSIDE_WEIGHTS

    # ── P0-3: 联赛差异化 ρ ──
    if dc_rho is None:
        dc_rho = LEAGUE_DC_RHO.get(league_key, DC_RHO)
        if dc_rho != DC_RHO:
            logger.debug(f"Using league-specific rho for {league_key}: {dc_rho}")

    hp = match.get("home_true_prob") or 0.5
    dp = match.get("draw_true_prob") or 0.25
    ap = match.get("away_true_prob") or 0.25
    hfs = match.get("home_form_score", 0.5)
    afs = match.get("away_form_score", 0.5)
    hrs = match.get("home_record_score", 0.5)
    ars = match.get("away_record_score", 0.5)
    sm = match.get("spread_movement_score", 0)

    # ── Onside 4 信号 ──
    home_en = match.get("home_en", match.get("home", ""))
    away_en = match.get("away_en", match.get("away", ""))

    if fifa_rankings is None:
        fifa_rankings = fetch_fifa_rankings()

    onside = compute_onside_signals(home_en, away_en, fifa_rankings, host_country, elo_ratings=elo_ratings)
    home_onside = onside["home"]["onside_score"]
    away_onside = onside["away"]["onside_score"]

    # ── 应用 calibration offset 修正隐含概率 ──
    calibration_note = None
    if calibration_offset:
        hc = calibration_offset.get("home_correction", 1.0)
        dc_val = calibration_offset.get("draw_correction", 1.0)
        ac = calibration_offset.get("away_correction", 1.0)

        # 修正 market odds：乘以 offset 后重新归一化
        hp_corrected = hp * hc
        dp_corrected = dp * dc_val
        ap_corrected = ap * ac
        total_corrected = hp_corrected + dp_corrected + ap_corrected
        if total_corrected > 0:
            hp = hp_corrected / total_corrected
            dp = dp_corrected / total_corrected
            ap = ap_corrected / total_corrected

        # 修正 Onside 4 信号：同方向校正后归一化
        onside_h = home_onside * hc
        onside_a = away_onside * ac
        total_on = onside_h + onside_a
        if total_on > 0:
            home_onside = onside_h / total_on
            away_onside = onside_a / total_on

        calibration_note = f"calibration applied (n={calibration_offset.get('sample_size','?')}, " \
                           f"home×{hc}/draw×{dc_val}/away×{ac})"
        logger.info(calibration_note)

    sm_capped = max(-THRESHOLDS["spread_movement_cap"], min(THRESHOLDS["spread_movement_cap"], sm))

    # ── ELO 信号（可选） ──
    elo_home_expected = None
    if elo_ratings:
        home_elo = elo_ratings.get(home_en, DEFAULT_ELO)
        away_elo = elo_ratings.get(away_en, DEFAULT_ELO)
        elo_home_expected = expected_score(home_elo, away_elo, home_adv=True)
        elo_away_expected = 1.0 - elo_home_expected
    ELO_WEIGHT = 0.18  # P0-2: 从 10% 提升到 18%，ELO 信息量被低估

    # ══════════════════════════════════════════════════════
    # P0-2 统一权重体系：方向概率和 λ 使用同一套加权信号
    # ══════════════════════════════════════════════════════
    
    onside_weight = (1 - MARKET_ODDS_WEIGHT) * (1 - ELO_WEIGHT if elo_ratings else 1.0)

    # ── 方向概率计算 ──
    market_home = hp
    market_draw = dp
    market_away = ap

    home_strength = (
        market_home * MARKET_ODDS_WEIGHT
        + home_onside * onside_weight
        + sm_capped * 0.5
    )
    away_strength = (
        market_away * MARKET_ODDS_WEIGHT
        + away_onside * onside_weight
        + (-sm_capped) * 0.5
    )

    # ELO 加成
    if elo_ratings and elo_home_expected is not None:
        home_strength += elo_home_expected * ELO_WEIGHT
        away_strength += elo_away_expected * ELO_WEIGHT

    # P0-C 修复: Calibration 的 draw_correction 现在应用到 draw_strength
    _dc_draw = dc_val if calibration_offset else 1.0
    draw_strength = max(0, (market_draw * _dc_draw) * MARKET_ODDS_WEIGHT + THRESHOLDS["draw_base_score"])

    total = max(home_strength + draw_strength + away_strength, 0.05)
    home_prob = home_strength / total
    draw_prob_calc = draw_strength / total
    away_prob = away_strength / total

    # ── 方向判断 ──
    if home_prob > THRESHOLDS["direction_min_prob"] and home_prob > away_prob * THRESHOLDS["direction_odds_ratio"]:
        direction = f"{match['home']} 胜"
        confidence_raw = (home_prob - 0.25) * 2
    elif away_prob > THRESHOLDS["direction_min_prob"] and away_prob > home_prob * THRESHOLDS["direction_odds_ratio"]:
        direction = f"{match['away']} 胜"
        confidence_raw = (away_prob - 0.25) * 2
    elif draw_prob_calc > THRESHOLDS["draw_threshold"]:
        direction = "平局"
        confidence_raw = (draw_prob_calc - 0.25) * 2
    else:
        if home_prob >= away_prob and home_prob >= draw_prob_calc:
            direction = f"{match['home']} 胜 (接近)"
            confidence_raw = (home_prob - THRESHOLDS["near_mode_base"]) * 3
        elif away_prob >= home_prob and away_prob >= draw_prob_calc:
            direction = f"{match['away']} 胜 (接近)"
            confidence_raw = (away_prob - THRESHOLDS["near_mode_base"]) * 3
        else:
            direction = "平局 (接近)"
            confidence_raw = (draw_prob_calc - THRESHOLDS["near_mode_base"]) * 3

    confidence_raw = min(max(confidence_raw, 0.0), 1.0)

    # ── 盘口数据缺失降级 ──
    if not match.get("odds_data_available", False):
        confidence_raw = max(confidence_raw - 0.25, 0.0)
        confidence_note = "无盘口数据，仅基本面参考"
    else:
        confidence_note = None

    if confidence_raw >= THRESHOLDS["star_5"]:
        stars = "5-star"
    elif confidence_raw >= THRESHOLDS["star_4"]:
        stars = "4-star"
    elif confidence_raw >= THRESHOLDS["star_3"]:
        stars = "3-star"
    elif confidence_raw >= THRESHOLDS["star_2"]:
        stars = "2-star"
    else:
        stars = "1-star"

    # ══════════════════════════════════════════════════════
    # P0-2 修复: λ 计算现在使用与方向相同的统一权重体系
    # 旧代码: raw = market*40% + form*20% + record*15% + spread*25%
    # 新代码: 与方向一致 — market + onside + elo + spread
    # ══════════════════════════════════════════════════════
    _lambda_mult = THRESHOLDS["lambda_multiplier"]
    # P1-C: 联赛差异化 λ 映射系数（覆盖全局默认值）
    from core.config import LEAGUE_LAMBDA_MULTIPLIER
    if league_key in LEAGUE_LAMBDA_MULTIPLIER:
        _lambda_mult = LEAGUE_LAMBDA_MULTIPLIER[league_key]

    # 统一的 raw strength（与方向概率同一套信号）
    raw_home_unified = (
        hp * MARKET_ODDS_WEIGHT
        + home_onside * onside_weight
        + sm_capped * 0.5
    )
    raw_away_unified = (
        ap * MARKET_ODDS_WEIGHT
        + away_onside * onside_weight
        + (-sm_capped) * 0.5
    )

    if elo_ratings and elo_home_expected is not None:
        raw_home_unified += elo_home_expected * ELO_WEIGHT
        raw_away_unified += elo_away_expected * ELO_WEIGHT

    # 加入 form/record 作为补充微调（保留但降权）
    raw_home = raw_home_unified * 0.75 + (hfs * 0.15 + hrs * 0.10)
    raw_away = raw_away_unified * 0.75 + (afs * 0.15 + ars * 0.10)

    lambda_home = max(raw_home * _lambda_mult, THRESHOLDS["lambda_lower_bound"])
    lambda_away = max(raw_away * _lambda_mult, THRESHOLDS["lambda_lower_bound"])

    # ── Dixon-Coles 或独立泊松比分预测 ──
    if use_dixon_coles:
        dc_result = dixon_coles_match_probs(lambda_home, lambda_away, rho=dc_rho)
        all_scores = dc_result["score_probs"]
        top3 = [(s[0], s[1], round(s[2], 4)) for s in all_scores[:3]]
        predicted_score = f"{top3[0][0]}-{top3[0][1]}"

        # 从 DC 模型计算 BTTS 和 Over/2.5
        btts_prob = sum(s[2] for s in all_scores if s[0] > 0 and s[1] > 0)
        over_25_prob = sum(s[2] for s in all_scores if s[0] + s[1] > 2)
    else:
        all_scores = []
        for h in range(9):
            for a in range(9):
                p = poisson_pmf(h, lambda_home) * poisson_pmf(a, lambda_away)
                if p >= 0.001:
                    all_scores.append((h, a, p))
        all_scores.sort(key=lambda x: -x[2])
        top3 = [(s[0], s[1], round(s[2], 4)) for s in all_scores[:3]]
        predicted_score = f"{top3[0][0]}-{top3[0][1]}"
        btts_prob = sum(s[2] for s in all_scores if s[0] > 0 and s[1] > 0)
        over_25_prob = sum(s[2] for s in all_scores if s[0] + s[1] > 2)

    # ── 方向一致性检查（P1-4：结构化枚举 + 主客胜全覆盖） ──
    def _resolve_direction_winner(dir_str: str, match_ctx: dict) -> str | None:
        """解析方向字符串 → 'home' | 'draw' | 'away' | None"""
        if "胜" not in dir_str:
            return None
        home_name = match_ctx.get("home", "")
        away_name = match_ctx.get("away", "")
        if dir_str.startswith(home_name):
            return "home"
        elif dir_str.startswith(away_name):
            return "away"
        return None

    if "胜" in direction:
        winner = _resolve_direction_winner(direction, match)
        predicted_h = int(predicted_score.split("-")[0])
        predicted_a = int(predicted_score.split("-")[1])
        if predicted_h == predicted_a and winner:
            for h, a, p in all_scores:
                if (winner == "home" and h > a) or (winner == "away" and a > h):
                    predicted_score = f"{h}-{a}"
                    break

    # 95% 置信区间
    ci_home = poisson_confidence_interval(lambda_home)
    ci_away = poisson_confidence_interval(lambda_away)

    ou_total = match.get("total_over_close", "2.5")
    ou_total = ou_total.lstrip("ou")
    if over_25_prob > 0.5:
        ou = f"Over {ou_total}"
    else:
        ou = f"Under {ou_total}"

    return {
        "direction": direction,
        "stars": stars,
        "confidence_score": round(confidence_raw, 3),
        "predicted_score": predicted_score,
        "poisson_top3": [
            {"score": f"{h}-{a}", "prob": round(p, 4)} for h, a, p in top3
        ],
        "lambda_home": round(lambda_home, 2),
        "lambda_away": round(lambda_away, 2),
        "lambda_home_ci95": ci_home,
        "lambda_away_ci95": ci_away,
        "over_under": f"{ou}",
        "btts": "Yes" if btts_prob > 0.5 else "No",
        "dixon_coles_used": use_dixon_coles,
        "dixon_coles_rho": dc_rho if use_dixon_coles else None,
        "dixon_coles_league_rho": LEAGUE_DC_RHO.get(league_key, DC_RHO),  # P0-3: 报告使用的 ρ 来源
        "onside_signals": onside,
        "confidence_note": confidence_note,
        "odds_data_available": match.get("odds_data_available", False),
        "reasoning_factors": {
            "home_ml_true_prob": round(hp, 3),
            "draw_true_prob": round(dp, 3),
            "away_ml_true_prob": round(ap, 3),
            "home_form_score": round(hfs, 3),
            "away_form_score": round(afs, 3),
            "home_record_score": round(hrs, 3),
            "away_record_score": round(ars, 3),
            "spread_movement": round(sm, 3),
            "home_onside_score": round(home_onside, 3),
            "away_onside_score": round(away_onside, 3),
            "home_prob_weighted": round(home_prob, 3),
            "draw_prob_weighted": round(draw_prob_calc, 3),
            "away_prob_weighted": round(away_prob, 3),
            "elo_home_expected": round(elo_home_expected, 3) if elo_ratings and elo_home_expected is not None else None,
            "raw_lambda_home": round(raw_home, 4),   # P0-2: 暴露原始 λ 输入便于调试
            "raw_lambda_away": round(raw_away, 4),   # P0-2: 暴露原始 λ 输入便于调试
        },
    }
