"""契约 v1.1 官方 payload → 规范行：jczq 场与结果（纯函数：零 DB、零网络、零副作用，只用 stdlib）。
parse_jczq_offer 一行 = 一场 × 一玩法 → fact.jc_offer（快照时刻在外壳上，§5.0，snap_ts 由调用方传入）；
parse_jczq_result 一行 = 一场 → fact.jc_result。规格表写法 "官方键[:转换码]>规范列"，值换算器见 parse_values。
"""

from __future__ import annotations

from .parse_values import build, clock, dec, need, out

BLOCKS = {"had": ("HAD", "had"), "hhad": ("HHAD", "hhad"), "crs": ("CRS", "crs"), "ttg": ("TTG", "ttg"),
          "hafu": ("HAFU", "haf")}  # 官方块名 → (官方 poolCode, DDL 归一化 play_type)
MATCH = ("matchId:i>match_id matchNum:i>match_num matchNumStr>match_num_str matchNumDate>match_num_date "
         "businessDate:c>business_date leagueId>league_id leagueAllName>league_cn leagueAbbName>league_abbr "
         "homeTeamId:i>home_sporttery_id awayTeamId:i>away_sporttery_id homeTeamAllName>home_cn "
         "awayTeamAllName>away_cn homeTeamAbbName>home_abbr awayTeamAbbName>away_abbr homeRank>home_rank "
         "awayRank>away_rank matchStatus>match_status sellStatus>sell_status bettingSingle>betting_single "
         "bettingAllUp>betting_all_up")
RESULT = ("matchId:i>match_id matchNumStr>match_num_str sectionsNo1>sections_no_1 sectionsNo999>sections_no_999 "
          "sectionsNo1:p0>ht_h sectionsNo1:p1>ht_a sectionsNo999:p0>ft_h sectionsNo999:p1>ft_a h:d>sp_home "
          "d:d>sp_draw a:d>sp_away goalLine>goal_line winFlag>win_flag resultStatus>result_status "
          "poolStatus>pool_status matchResultStatus>match_result_status leagueId>league_id leagueName>league_cn "
          "allHomeTeam>home_cn allAwayTeam>away_cn homeTeamId:i>home_sporttery_id awayTeamId:i>away_sporttery_id "
          "bettingSingle>betting_single")


def parse_jczq_offer(payload: dict, snap_ts: str | None = None) -> dict:
    """一行 = 一场 × 一玩法 → fact.jc_offer（快照时刻在**外壳**上，§5.0，故 snap_ts 由调用方传入）。"""
    block = need(payload, "block", str)
    code, play = BLOCKS.get(block, (None, None))
    if code is None or payload.get("poolCode") != code:
        raise ValueError(f"字段 block/poolCode 不在契约五块内或互不匹配：{block!r}/{payload.get('poolCode')!r}")
    match_id, options = need(payload, "matchId", int), need(payload, "options", dict)
    match = build(payload, MATCH) | {"kickoff_bj": clock(f"{payload.get('matchDate')} {payload.get('matchTime')}")}
    if match["kickoff_bj"] is None:
        raise ValueError(f"字段 matchDate/matchTime 拼不出 kickoff_bj：{payload.get('matchDate')}/{payload.get('matchTime')}")
    row = {"match_id": match_id, "snap_ts": snap_ts, "play_type": play, "pool_code": code, "options": options,
           "goal_line": options.get("goalLine") or None, "goal_line_value": dec(options.get("goalLineValue")),
           "odds_update": clock(f"{options.get('updateDate')} {options.get('updateTime')}")}
    notes = ["jc_match 是同一 payload 的另半列（kickoff_bj = matchDate+matchTime），P0-COLLECT2 落"]
    return out("fact.jc_offer", {"match_id": match_id, "play_type": play, "snap_ts": snap_ts}, row, notes, match=match)


def parse_jczq_result(payload: dict) -> dict:
    """一行 = 一场 → fact.jc_result（sectionsNo999="取消" 原值照抄、ft_h/ft_a = None，绝不 raise）。"""
    for key in ("sectionsNo1", "sectionsNo999"):
        if not isinstance(payload.get(key), str):
            raise ValueError(f"字段 {key} 缺失或不是字符串：{payload.get(key)!r}")
    row = build(payload, RESULT)
    row["match_id"] = need(payload, "matchId", int)
    return out("fact.jc_result", {"match_id": row["match_id"]}, row)
