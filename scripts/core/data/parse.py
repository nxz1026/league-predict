from __future__ import annotations

"""Event parsing and odds/statistics extraction."""

import json
from datetime import datetime, timezone
from core.config import COUNTRY_CN
from core.log import logger


def parse_american_odds(odds_str: str | None) -> float | None:
    """解析美式赔率 → 隐含概率 (含 vig)"""
    try:
        raw = str(odds_str).strip().lstrip('+')
        odds = int(raw)
        abs_odds = abs(odds)
        if odds < 0:
            return abs_odds / (abs_odds + 100)
        else:
            return 100 / (abs_odds + 100)
    except (ValueError, TypeError):
        return None


def parse_details(details_str: str | None) -> tuple[str | None, str | None, float | None]:
    """解析 details 字段如 'CZE -125' → (team, odds_str, implied)"""
    if not details_str:
        return None, None, None
    parts = details_str.strip().split()
    if len(parts) >= 2:
        team = parts[0]
        odds_str = parts[-1]
        impl = parse_american_odds(odds_str)
        return team, odds_str, impl
    return None, None, None


def to_cn(name: str | None) -> str:
    """英文国家名/俱乐部名 → 中文"""
    if not name:
        return name
    return COUNTRY_CN.get(name, COUNTRY_CN.get(name.replace("'", ""), name))


def form_to_score(form_str: str | None) -> float:
    """'DWDDW' → 0-1, W=3, D=1, L=0，带指数时间衰减（最近比赛权重更高）

    P1-A 修复: 衰减系数从线性 0.3 升级为指数 2^i，
    最新一场权重是最老的 16 倍，更符合足球状态敏感性。
    """
    if not form_str:
        return 0.5
    total_weight = 0
    weighted_sum = 0
    # 指数时间衰减：从左到右（最老→最新），最新权重最高
    for i, c in enumerate(form_str):
        w = 2.0 ** i  # 最后一场权重 = 2^4 = 16x（5场时）
        score = 3 if c == 'W' else 1 if c == 'D' else 0
        weighted_sum += score * w
        total_weight += w * 3
    return weighted_sum / total_weight if total_weight > 0 else 0.5


def record_to_score(records: list) -> float:
    """records[0].summary '1-0-0' (W-D-L) → 0-1"""
    if not records:
        return 0.5
    summary = records[0].get("summary", "")
    parts = summary.split("-")
    if len(parts) >= 3:
        w, d, l = int(parts[0]), int(parts[1]), int(parts[2])
        total = w + d + l
        return (w * 3 + d) / (total * 3) if total > 0 else 0.5
    return 0.5


def spread_movement_factor(away_open: dict | None, away_close: dict | None,
                          home_open: dict | None = None, home_close: dict | None = None) -> float:
    """综合主客场盘口 line + odds 变化判断 market 方向。

    P1-B 升级: 原版仅用 away spread line 差值，
    现在加入 home spread + 双方 odds 变化作为辅助信号。

    正值 = 盘口向主队移动（利好主队）
    负值 = 盘口向客队移动（利好客队）
    """
    signal = 0.0

    # Away spread line 变化
    if away_open and away_close:
        ol = away_open.get("line")
        cl = away_close.get("line")
        if ol is not None and cl is not None:
            try:
                signal += (float(cl) - float(ol)) / 3.0
            except (ValueError, TypeError):
                pass

    # Home spread line 变化（方向相反：home line 升高 = 客队被看好）
    if home_open and home_close:
        ol = home_open.get("line")
        cl = home_close.get("line")
        if ol is not None and cl is not None:
            try:
                signal += (float(ol) - float(cl)) / 3.0
            except (ValueError, TypeError):
                pass

    # Away odds 变化辅助信号（赔率下降 = 被看好）
    if away_open and away_close:
        oo = away_open.get("odds")
        co = away_close.get("odds")
        if oo and co:
            try:
                odds_shift = (float(oo) - float(co)) / 100.0
                signal += odds_shift * 0.3
            except (ValueError, TypeError):
                pass

    return max(-1.0, min(1.0, signal))


def decimal_to_american(decimal_odds: str | float | None) -> str | None:
    """Convert decimal odds to American format (API-Football uses decimal)."""
    if decimal_odds is None:
        return None
    try:
        dec = float(decimal_odds)
        if dec <= 1.0:
            return None
        if dec >= 2.0:
            return f"+{round((dec - 1) * 100)}"
        else:
            return str(round(-100 / (dec - 1)))
    except (ValueError, TypeError):
        return None


def remove_vig(home_p: float | None, draw_p: float | None, away_p: float | None = None,
              method: str = "logit") -> tuple[float | None, float | None, float | None]:
    """三向去水。

    P1-D 升级: 支持两种去水方法：
    - "logit"（默认）: 对数比例法 (Shen & Steinberg, 1994)，更准确处理热门方高抽水
    - "proportional": 简单比例法（向后兼容）
    """
    from core.config import BOOKMAKER_MARGIN, MIN_IMPLIED_PROB
    import math

    if draw_p is None:
        return None, None, None
    if home_p is None and away_p is None:
        return None, None, None
    _margin = BOOKMAKER_MARGIN
    if away_p is None:
        away_p = max(MIN_IMPLIED_PROB, 1.0 - home_p - draw_p)
    if home_p is None:
        home_p = max(MIN_IMPLIED_PROB, 1.0 - draw_p - away_p)

    if method == "logit":
        # 对数比例法：对隐含概率取对数 → 减均值 → 指数化 → 归一化
        probs = [home_p, draw_p, away_p]
        try:
            log_probs = [math.log(max(p, 1e-10)) for p in probs]
            mean_log = sum(log_probs) / len(log_probs)
            shifted = [math.exp(lp - mean_log) for lp in log_probs]
            total = sum(shifted)
            if total > 0:
                return (shifted[0] / total, shifted[1] / total, shifted[2] / total)
        except (ValueError, OverflowError, ZeroDivisionError):
            pass  # fallback to proportional

    # 比例法兜底
    total = home_p + draw_p + away_p
    if total <= 0:
        return home_p / _margin, draw_p / _margin, away_p / _margin
    return home_p / total, draw_p / total, away_p / total


def parse_events(events: list, now_utc: datetime | None = None) -> tuple[list, list, list]:
    """解析 ESPN events → 结束比赛列表 + 待预测比赛列表"""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    past = []
    future = []
    in_progress = []

    for ev in events:
        en_name = ev.get("name", "")
        if " at " in en_name:
            # ESPN: "Away at Home" → display "主队 vs 客队"
            away_en, home_en = en_name.split(" at ", 1)
            name = f"{to_cn(home_en)} vs {to_cn(away_en)}"
        else:
            name = to_cn(en_name)
        comps = ev.get("competitions", [{}])
        if not comps or not isinstance(comps, list) or len(comps) == 0:
            logger.warning(f"Event missing competitions data: {en_name}")
            continue
        comp = comps[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        completed = comp.get("status", {}).get("type", {}).get("completed", False)

        date_str = ev.get("date", "")
        try:
            kickoff = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            kickoff = now_utc
        time_to = (kickoff - now_utc).total_seconds() / 3600

        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)

        home_name = to_cn(home["team"]["displayName"]) if home else "?"
        away_name = to_cn(away["team"]["displayName"]) if away else "?"
        home_abbr = home["team"]["abbreviation"] if home else ""
        away_abbr = away["team"]["abbreviation"] if away else ""
        home_score = home.get("score", "0") if home else "0"
        away_score = away.get("score", "0") if away else "0"

        home_form = home.get("form", "") if home else ""
        away_form = away.get("form", "") if away else ""
        home_records = home.get("records", []) if home else []
        away_records = away.get("records", []) if away else []

        odds_raw = comp.get("odds") or []
        odds = next((o for o in odds_raw if o), {}) if odds_raw else {}

        details = odds.get("details", "")
        draw_ml = (odds.get("drawOdds") or {}).get("moneyLine", None)

        ps = odds.get("pointSpread") or {}
        spread_h = ps.get("home") or {}
        spread_a = ps.get("away") or {}
        spread_h_open = spread_h.get("open") or {}
        spread_h_close = spread_h.get("close") or {}
        spread_a_open = spread_a.get("open") or {}
        spread_a_close = spread_a.get("close") or {}

        tot = odds.get("total") or {}
        tot_o = tot.get("over") or {}
        tot_u = tot.get("under") or {}
        tot_o_close = tot_o.get("close") or {}
        tot_u_close = tot_u.get("close") or {}

        spread_h_line = spread_h_close.get("line", "")
        spread_h_odds = spread_h_close.get("odds", "")

        ml_team, ml_odds_str, home_ml_implied = parse_details(details)
        draw_implied = parse_american_odds(draw_ml)

        home_true, draw_true, away_true = remove_vig(home_ml_implied, draw_implied)

        spread_move = spread_movement_factor(spread_a_open, spread_a_close)

        h_fs = form_to_score(home_form)
        a_fs = form_to_score(away_form)
        h_rs = record_to_score(home_records)
        a_rs = record_to_score(away_records)

        rec = {
            "name": name,
            "status": status,
            "completed": completed,
            "kickoff_utc": date_str,
            "time_to_kickoff_h": round(time_to, 1),
            "home": home_name,
            "away": away_name,
            "home_en": home["team"]["displayName"] if home else "",
            "away_en": away["team"]["displayName"] if away else "",
            "home_abbr": home_abbr,
            "away_abbr": away_abbr,
            "score": f"{home_score}-{away_score}" if status in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_ET") else "",
            "home_form": home_form,
            "away_form": away_form,
            "home_form_score": round(h_fs, 3),
            "away_form_score": round(a_fs, 3),
            "home_record": home_records[0].get("summary","") if home_records else "",
            "away_record": away_records[0].get("summary","") if away_records else "",
            "home_record_score": round(h_rs, 3),
            "away_record_score": round(a_rs, 3),
            "ml_home_close": ml_odds_str,
            "draw_ml": draw_ml,
            "home_ml_implied": round(home_ml_implied, 4) if home_ml_implied else None,
            "draw_implied": round(draw_implied, 4) if draw_implied else None,
            "home_true_prob": round(home_true, 4) if home_true else None,
            "draw_true_prob": round(draw_true, 4) if draw_true else None,
            "away_true_prob": round(away_true, 4) if away_true else None,
            "spread_home_line": spread_h_line,
            "spread_home_close_odds": spread_h_odds,
            "spread_movement_score": round(spread_move, 3),
            "total_over_close": tot_o_close.get("line",""),
            "total_under_close": tot_u_close.get("line",""),
            "odds_data_available": bool(odds.get("details") or odds.get("drawOdds") or odds.get("pointSpread") or odds.get("total")),
        }

        if status in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_ET"):
            past.append(rec)
        elif status == "STATUS_SCHEDULED":
            future.append(rec)
        else:
            in_progress.append(rec)

    return past, future, in_progress
