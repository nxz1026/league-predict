"""契约 v1.1 官方 payload → 规范行：jc_issue 期头与开奖（纯函数：零 DB、零网络、零副作用，只用 stdlib）。
parse_jc_issue 一行 = 一个玩法的一期期头 → fact.jc_issue；parse_jc_issue_result 一行 = 一期开奖 → fact.jc_issue_draw。
规格表写法 "官方键[:转换码]>规范列"，值换算器见 parse_values。
"""

from __future__ import annotations

from .parse_values import build, need, out

GAME_KEYS = ("sfc", "jqc", "bqc")  # jc_issue_result 三棵详情树；任九是 sfc 期里的孪生字段，不单独成期
ISSUE = ("lotteryGameNum>game_num lotteryDrawNum>issue_no lotteryGameName>game_name lotterySaleBeginTime:c>sale_begin "
         "lotterySaleEndTime:c>sale_end lotteryDrawTime:c>draw_at matchList:n>n_matches drawNumList>draw_num_list")
DRAW = ("lotteryGameNum>game_num lotteryDrawNum>issue_no lotteryGameName>game_name lotteryDrawResult>draw_result "
        "poolBalanceAfterdraw>pool_after totalSaleAmount>sales poolBalanceAfterdrawRj>pool_after_rj "
        "totalSaleAmountRj>sales_rj lotteryPaidBeginTime:c>paid_begin lotteryPaidEndTime:c>paid_end "
        "isDelay>is_delay delayRemark>delay_remark")


def parse_jc_issue(payload: dict) -> dict:
    """一行 = 一个玩法的一期期头 → fact.jc_issue（期号跨玩法重号 ⇒ pk 必须 (game_num, issue_no) 两列）。"""
    for key, kind in (("lotteryGameNum", str), ("lotteryDrawNum", str), ("drawNumList", list), ("matchList", list)):
        need(payload, key, kind)
    matches = payload["matchList"]  # need() 已验类型
    if not matches or not all(isinstance(match, dict) for match in matches):
        raise ValueError(f"字段 matchList 必须是非空对象数组（fact.jc_issue.n_matches 必须 > 0）：{matches!r}")
    row = build(payload, ISSUE) | {"raw_head": payload}
    notes = [f"matchList {len(matches)} 场（长度不按常识断言，任九给 14 场）→ fact.jc_issue_match，P0-COLLECT2 落"]
    return out("fact.jc_issue", {"game_num": row["game_num"], "issue_no": row["issue_no"]}, row, notes)


def parse_jc_issue_result(payload: dict) -> dict:
    """一行 = 一个玩法的一期开奖 → fact.jc_issue_draw（任九是 sfc 期里的孪生字段，不单独成期）。"""
    key = need(payload, "gameKey", str)
    if key not in GAME_KEYS:
        raise ValueError(f"字段 gameKey 不在 {GAME_KEYS} 内：{key!r}")
    for field in ("lotteryGameNum", "lotteryDrawNum"):
        need(payload, field, str)
    counts = (len(need(payload, "matchList", list)), len(need(payload, "prizeLevelList", list)))
    row = build(payload, DRAW) | {"game_key": key}
    notes = [f"matchList {counts[0]} 场 + prizeLevelList {counts[1]} 条（条数不固定）→ P0-COLLECT2"]
    return out("fact.jc_issue_draw", {"game_num": row["game_num"], "issue_no": row["issue_no"]}, row, notes)
