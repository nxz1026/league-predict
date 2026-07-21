from __future__ import annotations

"""Core prediction engine: Onside 4+1 signal model combined with Dixon-Coles."""

import json
from core.config import ONSIDE_WEIGHTS, HOST_ADVANTAGE_BOOST, DC_RHO, THRESHOLDS
from core.log import logger
from core.model.onside import compute_onside_signals, fetch_fifa_rankings
from core.model.poisson import dixon_coles_match_probs, poisson_pmf, poisson_confidence_interval


def calculate_prediction(
    match: dict,
    weights: dict | None = None,
    calibration_offset: dict | None = None,
    fifa_rankings: dict | None = None,
    host_country: str | None = None,
    use_dixon_coles: bool = True,
    dc_rho: float = DC_RHO,
) -> dict:
    """
    Onside 4 信号 + Dixon-Coles 预测 → 方向 + 信心 + 比分预测 + 95% CI

    Args:
        match: 比赛数据字典
        weights: 权重字典（可选，默认 ONSIDE_WEIGHTS）
        calibration_offset: 校准偏移字典
        fifa_rankings: FIFA 排名字典
        host_country: 东道主国家
        use_dixon_coles: 是否使用 Dixon-Coles 模型
    """
    if weights is None:
        weights = ONSIDE_WEIGHTS

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

    onside = compute_onside_signals(home_en, away_en, fifa_rankings, host_country)
    home_onside = onside["home"]["onside_score"]
    away_onside = onside["away"]["onside_score"]

    # ── 应用 calibration offset 修正隐含概率 ──
    calibration_note = None
    if calibration_offset:
        hc = calibration_offset.get("home_correction", 1.0)
        dc = calibration_offset.get("draw_correction", 1.0)
        ac = calibration_offset.get("away_correction", 1.0)

        # 修正 market odds：乘以 offset 后重新归一化
        hp_corrected = hp * hc
        dp_corrected = dp * dc
        ap_corrected = ap * ac
        total_corrected = hp_corrected + dp_corrected + ap_corrected
        if total_corrected > 0:
            hp = hp_corrected / total_corrected
            dp = dp_corrected / total_corrected
            ap = ap_corrected / total_corrected

        # 修正 Onside 4 信号：同方向校正后归一化（ponytail: 单向线性，误差累积超出 ±50% 再考虑分层）
        onside_h = home_onside * hc
        onside_a = away_onside * ac
        total_on = onside_h + onside_a
        if total_on > 0:
            home_onside = onside_h / total_on
            away_onside = onside_a / total_on

        calibration_note = f"calibration applied (n={calibration_offset.get('sample_size','?')}, " \
                           f"home×{hc}/draw×{dc}/away×{ac})"
        logger.info(calibration_note)

    sm_capped = max(-THRESHOLDS["spread_movement_cap"], min(THRESHOLDS["spread_movement_cap"], sm))

    # ── Onside 4 信号加权评分 ──
    # 市场信号 (20%): 盘口隐含概率
    market_home = hp
    market_draw = dp
    market_away = ap

    # 综合评分 = 市场信号×20% + Onside信号×80%
    home_strength = (
        market_home * weights["market_odds"]
        + home_onside * (1 - weights["market_odds"])
        + sm_capped * 0.5
    )
    away_strength = (
        market_away * weights["market_odds"]
        + away_onside * (1 - weights["market_odds"])
        + (-sm_capped) * 0.5
    )
    draw_strength = max(0, market_draw * weights["market_odds"] + THRESHOLDS["draw_base_score"])

    # 东道主额外加成
    if host_country and home_en == host_country:
        home_strength += HOST_ADVANTAGE_BOOST

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
        stars = "⭐⭐⭐⭐⭐"
    elif confidence_raw >= THRESHOLDS["star_4"]:
        stars = "⭐⭐⭐⭐"
    elif confidence_raw >= THRESHOLDS["star_3"]:
        stars = "⭐⭐⭐"
    elif confidence_raw >= THRESHOLDS["star_2"]:
        stars = "⭐⭐"
    else:
        stars = "⭐"

    # ── 期望进球计算 ──
    # _lambda_mult: maps raw strength (0-1 scale) to realistic λ range (~0.5-2.8)
    # Removed shared draw inflation which pushed both λ values up equally → 1-1 stuck
    _lambda_mult = THRESHOLDS["lambda_multiplier"]
    raw_home = hp * 0.40 + hfs * 0.20 + hrs * 0.15 + sm * 0.25
    raw_away = ap * 0.40 + afs * 0.20 + ars * 0.15 + (-sm) * 0.25
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
        top3 = all_scores[:3]
        predicted_score = f"{top3[0][0]}-{top3[0][1]}"

        btts_prob = sum(p[2] for p in all_scores if p[0] > 0 and p[1] > 0)
        over_25_prob = sum(p[2] for p in all_scores if p[0] + p[1] > 2)

    # ── 方向一致性检查（ponytail: 避免 "X 胜" 但 predicted_score 为平局） ──
    if "胜" in direction:
        predicted_h = int(predicted_score.split("-")[0])
        predicted_a = int(predicted_score.split("-")[1])
        if predicted_h == predicted_a:
            is_home_win = direction.startswith(match.get("home", ""))
            for h, a, p in all_scores:
                if (is_home_win and h > a) or (not is_home_win and a > h):
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
        }
    }
