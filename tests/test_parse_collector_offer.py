"""契约 v1.1 解析层逐条对着夹具断言（零 DB；夹具 = tests/fixtures/collector_v11/**，真实探针响应，一个字节都不许改）：
① 77 行外壳校验全过、src_hash 复算 0 失败；② jczq_offer 40 行 = 8 场 × 5 块、crs 31 选项键（28+3）与块内 66 键；
③ hhad 让球线 "-1"/"+1"、had 的空线串 ⇒ 解析列 None（不是 0）；④ jczq_result 两行"取消" ⇒ ft_* 为 None 且不 raise、
空 SP 5 行、"+4" 原值照抄。P0-COLLECT1b 机械拆分：⑤~⑨ 移 tests/test_parse_collector_issue.py。
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from store import parse_collector as pc  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "collector_v11"
SNAP = "2026-09-15T11:07:35Z"


def rows(name: str) -> list[dict]:
    """夹具原样读入（payload 与官方响应逐字一致，见 PROVENANCE.md）。"""
    text = (FIX / f"{name}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def payloads(name: str) -> list[dict]:
    return [env["payload"] for env in rows(name)]


def test_all_lines_pass_envelope_and_src_hash():
    """① 77 行：外壳八字段/类型/snap_ts(Z)/src_hash 复算全过（幂等键只认本地复算）。"""
    seen = 0
    for path in sorted(FIX.glob("*.jsonl")):
        for env in [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]:
            seen += 1
            topic = path.stem if path.stem != "errors" else env["topic"]  # errors 行各自带真实 topic
            assert pc.envelope_error(env, topic) is None
            assert env["src_hash"] == pc.canonical_src_hash(env["payload"])
    assert seen == 77


def test_jczq_offer_block_structure():
    """② 40 行聚成 8 场、每场 5 块；crs 块 66 键 = (28 比分格 + 3 其它) × 2 旗标 + 4 元键。"""
    offers = payloads("jczq_offer")
    by_match: dict = {}
    for payload in offers:
        by_match.setdefault(payload["matchId"], []).append(payload["block"])
    assert len(offers) == 40 and len(by_match) == 8
    assert all(sorted(blocks) == ["crs", "had", "hafu", "hhad", "ttg"] for blocks in by_match.values())
    options = next(p["options"] for p in offers if p["block"] == "crs")
    scores = [key for key in options if re.fullmatch(r"s\d{2}s\d{2}$", key)]
    others = [key for key in options if re.fullmatch(r"s1s[hda]$", key)]
    assert len(scores) == 28 and len(others) == 3 and len(options) == 66 == (len(scores) + len(others)) * 2 + 4


def test_jczq_offer_goal_line_parsed_columns():
    """③ hhad 有 "-1"/"+1" 让球线；had/crs/ttg/hafu 的空线串 ⇒ goal_line/goal_line_value 必须是 None。"""
    parsed = [pc.parse_jczq_offer(payload, SNAP) for payload in payloads("jczq_offer")]
    lines = {(row["row"]["goal_line"], row["row"]["goal_line_value"])
             for row in parsed if row["row"]["play_type"] == "hhad"}
    assert ("-1", Decimal("-1.00")) in lines and ("+1", Decimal("1.00")) in lines
    for row in parsed:
        if row["row"]["play_type"] != "hhad":
            assert row["row"]["goal_line"] is None and row["row"]["goal_line_value"] is None
    assert parsed[0]["table"] == "fact.jc_offer"
    assert parsed[0]["pk"] == {"match_id": 2041483, "play_type": "had", "snap_ts": SNAP}
    assert parsed[0]["row"]["options"]["goalLine"] == ""  # 原值照抄，清洗只发生在解析列
    assert parsed[0]["match"]["kickoff_bj"].strftime("%Y-%m-%d %H:%M") == "2026-09-15 20:15"  # matchDate+matchTime


def test_jczq_result_cancel_and_empty_sp():
    """④ 14 行里 2 行 "取消" ⇒ ft_h/ft_a None 且不 raise；空 SP 5 行 ⇒ sp_home None；"+4"/"-4" 原值照抄。"""
    parsed = [pc.parse_line(env) for env in rows("jczq_result")]
    cancelled = [row["row"] for row in parsed if row["row"]["sections_no_999"] == "取消"]
    assert len(cancelled) == 2
    assert all(row["ft_h"] is None and row["ft_a"] is None and row["sections_no_999"] == "取消" for row in cancelled)
    assert sum(1 for row in parsed if row["row"]["sp_home"] is None) == 5  # 非竞彩开盘场次：空 SP 是常态
    goals = {row["row"]["goal_line"] for row in parsed}
    assert {"+4", "-4"} <= goals and all(isinstance(goal, str) for goal in goals)  # 含正号也不许换算
    scored = next(row["row"] for row in parsed if row["row"]["sections_no_999"] == "5:1")
    assert (scored["ft_h"], scored["ft_a"], scored["sections_no_1"]) == (5, 1, "2:1")
