from __future__ import annotations

"""Calibration: historical match analysis and prediction offset computation."""

import json
import time
from typing import Any

from core.config import PREDICTIONS_DIR, FOOTBALL_DIR
from core.log import logger


def _try_load_json(path) -> dict | None:
    """尝试用多种编码加载 JSON 文件（兼容 Windows gbk 历史文件）"""
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            with open(path, encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            continue
    return None


def load_historical_past_matches(days: int = 30) -> list[dict[str, Any]]:
    """读取历史 predictions/ 文件中的 past_matches + references/historical_past_matches.json，去重后返回"""
    all_past: list[dict[str, Any]] = []
    cutoff = time.time() - days * 86400

    for f in PREDICTIONS_DIR.glob("prediction_*.json"):
        if f.stat().st_mtime < cutoff:
            continue
        try:
            d = _try_load_json(f)
            if d is not None:
                all_past.extend(d.get("past_matches", []))
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    hist_file = FOOTBALL_DIR / "references" / "historical_past_matches.json"
    if hist_file.exists():
        try:
            hist_data = _try_load_json(hist_file)
            all_past.extend(hist_data)
        except (json.JSONDecodeError, OSError):
            pass

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for m in all_past:
        key = f"{m.get('kickoff_utc','')}_{m.get('home','')}_{m.get('away','')}"
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def compute_calibration_offset(past_matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    从累积 past_matches 计算 calibration 修正因子。
    用实际赛果分布 vs 均匀分布(1/3)的比率做软修正。
    """
    if len(past_matches) < 5:
        return None

    home_wins = draws = away_wins = 0

    for m in past_matches:
        score = m.get("score", "")
        if not score or "-" not in score:
            continue
        parts = score.split("-")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        hs, aws = int(parts[0]), int(parts[1])
        if hs > aws:
            home_wins += 1
        elif hs == aws:
            draws += 1
        else:
            away_wins += 1

    total = home_wins + draws + away_wins
    if total < 5:
        logger.debug(f"Calibration: only {total} finished matches (<5), skipping offset")
        return None

    actual_home_rate = home_wins / total
    actual_draw_rate = draws / total
    actual_away_rate = away_wins / total

    # 使用足球联赛实际分布作为基线（主胜~45%, 平局~25%, 客胜~30%）
    _baseline_home = 0.45
    _baseline_draw = 0.25
    _baseline_away = 0.30

    # 样本量加权：小样本时降低修正幅度，避免噪声放大（P1-1）
    sample_weight = min(1.0, total / 50.0)
    _clamp_lo, _clamp_hi = 0.5, 2.0

    home_correction = max(_clamp_lo, min(_clamp_hi, actual_home_rate / _baseline_home))
    draw_correction = max(_clamp_lo, min(_clamp_hi, actual_draw_rate / _baseline_draw))
    away_correction = max(_clamp_lo, min(_clamp_hi, actual_away_rate / _baseline_away))

    # 指数平滑：新旧修正值加权融合，防止跳变（P1-1）
    _smooth = 0.7
    prev_offset = None  # TODO: 从持久化文件加载上一次 offset
    if prev_offset:
        home_correction = _smooth * prev_offset.get("home_correction", home_correction) + (1 - _smooth) * home_correction
        draw_correction = _smooth * prev_offset.get("draw_correction", draw_correction) + (1 - _smooth) * draw_correction
        away_correction = _smooth * prev_offset.get("away_correction", away_correction) + (1 - _smooth) * away_correction

    # 对 Onside signal 的修正幅度减半（P1-1：避免双修正误差放大）
    onside_home_correction = 1.0 + (home_correction - 1.0) * sample_weight * 0.5
    onside_away_correction = 1.0 + (away_correction - 1.0) * sample_weight * 0.5

    logger.info(f"Calibration offset(n={total}, weight={sample_weight:.2f}): "
                f"home×{home_correction:.3f} draw×{draw_correction:.3f} away×{away_correction:.3f} | "
                f"onside_home×{onside_home_correction:.3f} onside_away×{onside_away_correction:.3f}")

    return {
        "home_correction": round(home_correction, 3),
        "draw_correction": round(draw_correction, 3),
        "away_correction": round(away_correction, 3),
        "onside_home_correction": round(onside_home_correction, 3),
        "onside_away_correction": round(onside_away_correction, 3),
        "sample_size": total,
        "sample_weight": round(sample_weight, 3),
        "actual_home_rate": round(actual_home_rate, 3),
        "actual_draw_rate": round(actual_draw_rate, 3),
        "actual_away_rate": round(actual_away_rate, 3),
    }


def _parse_score(score_str: str | None) -> tuple[int, int] | None:
    """Parse 'H-A' score string → (home, away) ints, or None on failure."""
    if not score_str or "-" not in str(score_str):
        return None
    parts = str(score_str).split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def build_calibration(past_matches: list[dict[str, Any]], future_matches: list[dict[str, Any]]) -> dict[str, Any]:
    """从结束比赛计算校准参数"""
    if not past_matches:
        return {"note": "no past matches to calibrate from"}

    home_wins = sum(1 for m in past_matches if (s := _parse_score(m.get("score"))) and s[0] > s[1])
    draws = sum(1 for m in past_matches if (s := _parse_score(m.get("score"))) and s[0] == s[1])
    away_wins = sum(1 for m in past_matches if (s := _parse_score(m.get("score"))) and s[0] < s[1])
    total = home_wins + draws + away_wins

    favorite_wins = 0
    total_odds_based = 0
    for m in past_matches:
        hp = m.get("home_true_prob")
        if hp and hp > 0.5:
            total_odds_based += 1
            if m["score"]:
                try:
                    s = _parse_score(m.get("score"))
                    if s and s[0] > s[1]:
                        favorite_wins += 1
                except (ValueError, AttributeError):
                    pass

    return {
        "total_matches": total,
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "home_win_rate": round(home_wins/total, 3) if total else 0,
        "draw_rate": round(draws/total, 3) if total else 0,
        "away_win_rate": round(away_wins/total, 3) if total else 0,
        "favored_by_odds": total_odds_based,
        "favored_won": favorite_wins,
        "odds_accuracy": round(favorite_wins/total_odds_based, 3) if total_odds_based else 0,
    }
