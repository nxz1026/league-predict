"""契约 v1.1 官方 payload → 规范行：lottery_draw 开奖与 jclq 篮彩（纯函数：零 DB、零网络、零副作用，只用 stdlib）。
parse_lottery_draw 一行 = 一个彩种的一期 → fact.lottery_draw（号码串原样；解析结果另存新列 numbers，不重排不去重）。
jclq 两 topic 的裁决行为原样保留：§5.5 未冻结 ⇒ parse_jclq_offer raise；§5.6 已冻结但无落点表 ⇒ parse_jclq_result raise。
"""

from __future__ import annotations

from .parse_values import build, need, out, split_numbers

LOTTERY = ("lotteryGameNum>game_num lotteryDrawNum>issue_no lotteryGameName>game_name lotteryDrawTime:c>draw_date "
           "lotteryDrawStatus>status lotteryDrawResult>numbers_raw drawFlowFund>pool "
           "lotteryEquipmentCount>equipment_count")


def parse_lottery_draw(payload: dict) -> dict:
    """一行 = 一个彩种的一期 → fact.lottery_draw（号码串原样；解析结果另存新列 numbers，不重排不去重）。"""
    for key, kind in (("lotteryGameNum", str), ("lotteryDrawNum", str), ("lotteryDrawResult", str),
                      ("prizeLevelList", list)):
        need(payload, key, kind)
    row = build(payload, LOTTERY) | {"numbers": None, "prizes": payload["prizeLevelList"]}
    row["numbers"] = split_numbers(row["game_num"], row["numbers_raw"])
    notes = ["prizes 整数组原样（含 stakeAmount '---' 与千分位逗号），解析层不转数字"]
    return out("fact.lottery_draw", {"game_num": row["game_num"], "issue_no": row["issue_no"]}, row, notes)


def parse_jclq_offer(payload: dict) -> dict:
    """§5.5：jclq_offer 契约 v1.1 **不冻结**（探针窗口内篮彩无开售）⇒ 不解析、不推测字段名。"""
    raise ValueError("jclq_offer 契约 v1.1 未冻结（§5.5）：等开售窗口复探后升 v1.2 再解析")


def parse_jclq_result(payload: dict) -> dict:
    """§5.6 已冻结 jclq_result 形态，但 P0-STORE2 的 DDL 只有足球 8 表、无篮彩落点 ⇒ 不产行（点名等定）。"""
    raise ValueError("fact 层无篮彩落点表（P0-STORE2 DDL 未建）：形态已冻结但无可落之表")
