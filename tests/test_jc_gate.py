"""P0-JCGATE1 封闭清单闸门测试（T1~T4，全离线断言，不碰库）：
A 表 10 组 (league_id, league_abbr) 常量照抄队长 12:53 实测；只有西甲可预测。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import jc_gate  # noqa: E402

# A 表（fact.jc_match 今天在场 10 组，league_cn 全称恒配缩写；清单内仅西甲 id=62）
ROWS = [
    {"league_abbr": "欧罗巴", "league_id": 70, "n": 12},
    {"league_abbr": "西甲", "league_id": 62, "n": 9},
    {"league_abbr": "解放者杯", "league_id": 49, "n": 4},
    {"league_abbr": "英联赛杯", "league_id": 24, "n": 3},
    {"league_abbr": "亚冠精英", "league_id": 1, "n": 2},
    {"league_abbr": "亚运男足", "league_id": 83, "n": 2},
    {"league_abbr": "荷甲", "league_id": 17, "n": 1},
    {"league_abbr": "巴甲", "league_id": 6, "n": 1},
    {"league_abbr": "亚运女足", "league_id": 106, "n": 1},
    {"league_abbr": "英冠", "league_id": 20, "n": 1},
]


def test_t1_a_table_exact_one():
    for row in ROWS:
        got = jc_gate.is_predictable(row["league_abbr"], row["league_id"])
        assert got is (row["league_abbr"] == "西甲")
    assert sum(1 for r in ROWS if jc_gate.is_predictable(r["league_abbr"], r["league_id"])) == 1
    assert jc_gate.is_predictable("西甲", 62) is True
    assert jc_gate.is_predictable("西甲", 999) is True  # 缩写命中即放行，id 不参与判定
    assert jc_gate.is_predictable("欧罗巴", 62) is True  # id 命中亦放行（两条路任一）


def test_t2_basketball_only_nba_cba():
    assert jc_gate.is_predictable("NBA") is True
    assert jc_gate.is_predictable("CBA") is True
    assert jc_gate.is_predictable("WNBA") is False
    assert jc_gate.is_predictable("欧洲篮球联赛") is False


def test_t3_odd_inputs_never_raise():
    assert jc_gate.is_predictable(None) is False
    assert jc_gate.is_predictable("") is False
    assert jc_gate.is_predictable("   ") is False
    assert jc_gate.is_predictable("西甲   ") is True  # 去空白一次仍要认
    assert jc_gate.is_predictable("西甲联赛") is False  # 未见过的相似写法必须拒（禁模糊匹配）


def test_t4_partition_counts_and_order():
    ok, blocked = jc_gate.partition(ROWS)
    assert [r["n"] for r in ok] == [9]
    assert [r["n"] for r in blocked] == [12, 4, 3, 2, 2, 1, 1, 1, 1]
    assert [r["league_abbr"] for r in ok] == ["西甲"]
    assert [r["league_abbr"] for r in blocked] == [r["league_abbr"] for r in ROWS if r["league_abbr"] != "西甲"]
    assert jc_gate.partition([]) == ([], [])
