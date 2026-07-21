from __future__ import annotations

"""Backtesting: compare predictions against actual results."""

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from core.config import PREDICTIONS_DIR, LEAGUE_CONFIG, ESPN_TIMEOUT_SECONDS, FOOTBALL_DIR
from core.log import logger


def reconcile_predictions(past_matches: list[dict[str, Any]], days: int = 7) -> dict[str, Any] | None:
    """将历史预测文件中的预测与当前实际赛果比对，返回回测统计。"""
    actuals: dict[str, tuple[int, int]] = {}
    for m in past_matches:
        name = m.get("name", "")
        score = m.get("score", "")
        if name and score and "-" in score:
            try:
                h, a = score.split("-")
                actuals[name] = (int(h), int(a))
            except (ValueError, IndexError):
                pass
    if not actuals:
        return None

    cutoff = time.time() - days * 86400
    correct_dir = correct_score = correct_ou = total = 0
    details: list[dict[str, Any]] = []

    for f in sorted(PREDICTIONS_DIR.glob("prediction_*.json")):
        if f.stat().st_mtime < cutoff:
            continue
        try:
            data = json.load(open(f))
        except (json.JSONDecodeError, OSError):
            continue
        for p in data.get("predictions", []):
            r = actuals.get(p.get("match", ""))
            if not r:
                continue
            h_act, a_act = r
            total += 1
            d = p.get("direction", "")
            # 三向方向判定：先判平局（最精确），再区分主胜/客胜
            is_home_win = False
            is_away_win = False
            is_draw = "平" in d or "平局" in d
            if not is_draw:
                home_team = p.get("home", "")
                if d.startswith(home_team + " 胜") or (not is_draw and "胜" in d and h_act > a_act):
                    is_home_win = True
                elif "胜" in d:
                    is_away_win = True

            if (is_home_win and h_act > a_act) or \
               (is_draw and h_act == a_act) or \
               (is_away_win and h_act < a_act):
                correct_dir += 1
                dir_ok = True
            else:
                dir_ok = False
            if p.get("predicted_score", "") == f"{h_act}-{a_act}":
                correct_score += 1
            ou = p.get("over_under", "")
            if "Over" in ou and h_act + a_act > 2.5:
                correct_ou += 1
            elif "Under" in ou and h_act + a_act < 2.5:
                correct_ou += 1
            details.append({
                "match": p.get("match",""),
                "predicted": p.get("predicted_score",""),
                "actual": f"{h_act}-{a_act}",
                "direction_correct": dir_ok,
            })

    if total == 0:
        return None
    return {
        "reconciled": total,
        "correct_direction": correct_dir,
        "correct_score": correct_score,
        "correct_over_under": correct_ou,
        "direction_accuracy": round(correct_dir / total, 3),
        "score_accuracy": round(correct_score / total, 3),
        "over_under_accuracy": round(correct_ou / total, 3),
        "details": details,
    }


def backtest_from_source(prediction_file: str) -> dict[str, Any]:
    """Compare predictions against actual results from football-data.org."""
    try:
        pred_data = json.loads(Path(prediction_file).read_text())
    except Exception as e:
        return {"status": "error", "error": str(e)}

    league = pred_data.get("league", "epl")
    league_config = LEAGUE_CONFIG.get(league, LEAGUE_CONFIG["epl"])
    if league_config.get("data_source") != "football-data":
        return {"status": "skip", "reason": "only football-data source supported for auto backtest"}

    actual_index: dict[tuple[str, str], dict[str, Any]] = {}
    for m in pred_data.get("past_matches", []):
        if m.get("status") == "STATUS_FULL_TIME" or m.get("completed"):
            home = m.get("home", "")
            away = m.get("away", "")
            score = m.get("score", "")
            winner = m.get("winner")
            if not winner and "-" in (score or ""):
                try:
                    h, a = [int(x.strip()) for x in score.split("-", 1)]
                    winner = "home" if h > a else "away" if a > h else "draw"
                except Exception:
                    winner = None
            if home and away and winner:
                actual_index[(home, away)] = {"winner": winner, "score": score}

    rows: list[dict[str, Any]] = []
    for pred in pred_data.get("predictions", []):
        home = pred.get("home", "")
        away = pred.get("away", "")
        actual = actual_index.get((home, away))
        if not actual:
            continue
        predicted: str | None = None
        score = pred.get("predicted_score") or ""
        if "-" in score:
            try:
                h, a = [int(x.strip()) for x in score.split("-", 1)]
            except Exception:
                h = a = None
            if h is not None:
                predicted = "home" if h > a else "away" if a > h else "draw"
        if predicted is None:
            continue
        rows.append({
            "home": home,
            "away": away,
            "predicted": predicted,
            "actual": actual["winner"],
            "correct": predicted == actual["winner"],
            "predicted_score": score,
            "actual_score": actual.get("score", ""),
        })

    if not rows:
        return {"status": "no_evaluable_matches", "matched_matches": 0}
    correct = sum(1 for r in rows if r["correct"])
    return {
        "status": "ok",
        "matched_matches": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "rows": rows,
    }


def backtest_with_live_results(prediction_file: str) -> dict[str, Any]:
    """Auto-fetch actual results from football-data.org for the prediction window."""
    try:
        pred_data = json.loads(Path(prediction_file).read_text())
    except Exception as e:
        return {"status": "error", "error": str(e)}

    league = pred_data.get("league", "epl")
    league_config = LEAGUE_CONFIG.get(league, LEAGUE_CONFIG["epl"])
    if league_config.get("data_source") != "football-data":
        return {"status": "skip", "reason": "only football-data source supported for live backtest"}

    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not api_key:
        return {"status": "skip", "reason": "FOOTBALL_DATA_API_KEY not set"}

    data_window = pred_data.get("data_window", "")
    if "-" in data_window:
        start_raw, end_raw = data_window.split("-", 1)
    else:
        start_raw = end_raw = data_window

    def normalize_date(s: str) -> str:
        s = s.strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        if len(s) == 10 and s[4] == '-' and s[7] == '-':
            return s
        return s

    start_date = normalize_date(start_raw)
    end_date = normalize_date(end_raw)
    league_id = league_config["league_id"]
    url = f"https://api.football-data.org/v4/competitions/{league_id}/matches?dateFrom={start_date}&dateTo={end_date}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "WorldCupPredict/3.0",
        "X-Auth-Token": api_key,
    })
    try:
        resp = urllib.request.urlopen(req, timeout=ESPN_TIMEOUT_SECONDS)
        data = json.loads(resp.read())
    except Exception as e:
        return {"status": "error", "error": f"fetch failed: {e}"}

    actual_index: dict[tuple[str, str], dict[str, Any]] = {}
    for m in data.get("matches", []):
        home_name = m.get("homeTeam", {}).get("name", "")
        away_name = m.get("awayTeam", {}).get("name", "")
        score = m.get("score", {})
        home_goals = score.get("fullTime", {}).get("home")
        away_goals = score.get("fullTime", {}).get("away")
        status = m.get("status", "")
        if status != "FINISHED" or home_goals is None or away_goals is None:
            continue
        try:
            h, a = int(home_goals), int(away_goals)
        except Exception:
            continue
        actual_index[(home_name, away_name)] = {
            "winner": "home" if h > a else "away" if a > h else "draw",
            "score": f"{h}-{a}",
        }

    rows: list[dict[str, Any]] = []
    for pred in pred_data.get("predictions", []):
        home = pred.get("home", "")
        away = pred.get("away", "")
        actual = actual_index.get((home, away))
        if not actual:
            continue
        predicted: str | None = None
        score = pred.get("predicted_score") or ""
        if "-" in score:
            try:
                h, a = [int(x.strip()) for x in score.split("-", 1)]
            except Exception:
                h = a = None
            if h is not None:
                predicted = "home" if h > a else "away" if a > h else "draw"
        if predicted is None:
            continue
        rows.append({
            "home": home,
            "away": away,
            "predicted": predicted,
            "actual": actual["winner"],
            "correct": predicted == actual["winner"],
            "predicted_score": score,
            "actual_score": actual.get("score", ""),
        })

    if not rows:
        return {"status": "no_evaluable_matches", "matched_matches": 0}
    correct = sum(1 for r in rows if r["correct"])
    return {
        "status": "ok",
        "matched_matches": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "rows": rows,
    }
