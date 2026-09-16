"""契约 v1.4 盘口全历史纯解析器：一行 payload 摊成每玩法每版一行的记录。

公开面：parse_history / parse_env。不连库、不碰 ref.team、不用本机时区
（updateDate/updateTime 是北京墙上时钟，用 Asia/Shanghai 解释）。
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_BJ = ZoneInfo("Asia/Shanghai")
_PLAYS = (("hadList", "had"), ("hhadList", "hhad"), ("crsList", "crs"),
          ("ttgList", "ttg"), ("hafuList", "haf"))
_META = ("updateDate", "updateTime", "goalLine")


def _goal_line_value(raw):
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _row(payload, play, seq, rec, src_hash, src_file):
    raw = str(rec.get("updateDate", "")) + " " + str(rec.get("updateTime", ""))
    try:
        ts = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_BJ).astimezone(timezone.utc)
    except ValueError:
        return None
    goal = rec.get("goalLine", "")
    goal = goal if isinstance(goal, str) else str(goal or "")
    lid = payload.get("leagueId")
    match = payload.get("matchId")
    return {
        "match_id": match if isinstance(match, int) else None,
        "play_type": play,
        "seq_no": seq,
        "update_ts": ts,
        "goal_line": goal if goal else None,
        "goal_line_value": _goal_line_value(goal),
        "odds": {k: v for k, v in rec.items() if k not in _META},
        "is_first": seq == 0,
        "is_close": False,
        "league_id": int(lid) if isinstance(lid, str) and lid.isdigit() else None,
        "src_hash": src_hash,
        "src_file": src_file,
    }


def parse_history(payload, src_hash="", src_file=""):
    if not isinstance(payload, dict) or not payload:
        return []
    rows = []
    for key, play in _PLAYS:
        arr = payload.get(key)
        if not isinstance(arr, list):
            continue
        for i, rec in enumerate(arr):
            if not isinstance(rec, dict):
                continue
            row = _row(payload, play, len(arr) - 1 - i, rec, src_hash, src_file)
            if row:
                rows.append(row)
    return rows



def parse_env(env, src_file=""):
    if not isinstance(env, dict) or not isinstance(env.get("payload"), dict):
        return []
    payload = env["payload"]
    if not payload:
        return []
    return parse_history(payload, src_hash=env.get("src_hash", ""), src_file=src_file)
