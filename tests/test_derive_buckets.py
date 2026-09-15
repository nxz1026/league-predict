"""L3a 玩法派生黄金用例：总进球 8 档 / 官方 31 比分桶 / 每队 8 档（纯算术，零依赖）。
黄金值 = 队长 (λ_h,λ_a,ρ,max_goals)=(1.5,0.8,0.0,8) 归一矩阵，容差 1e-6；手算 3×3（Σ=1）：.06 .10 .04 / .12 .20 .10 / .06 .12 .20
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from derive import goals4, scores31, totals  # noqa: E402
from derive.grid import dc_grid  # noqa: E402

GOLD_TOTALS = {"0": 0.100262, "1": 0.230602, "2": 0.265192, "3": 0.203314, "4": 0.116905,
               "5": 0.053777, "6": 0.020614, "7+": 0.009334}
GOLD_WDL = {"胜": 0.538153, "平": 0.261861, "负": 0.199986}
WIN12 = {"1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2"}
DRAW4 = {"0:0", "1:1", "2:2", "3:3"}
LOSE12 = {"0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5"}
GROUP = {"胜": WIN12 | {"胜其它"}, "平": DRAW4 | {"平其它"}, "负": LOSE12 | {"负其它"}}
KEYS31 = GROUP["胜"] | GROUP["平"] | GROUP["负"]
HAND33 = [[0.06, 0.10, 0.04], [0.12, 0.20, 0.10], [0.06, 0.12, 0.20]]
HAND8T = {"0": 0.06, "1": 0.22, "2": 0.30, "3": 0.22, "4": 0.20, "5": 0.0, "6": 0.0, "7+": 0.0}
HAND_SCORES = {"1:0": 0.12, "2:0": 0.06, "2:1": 0.12, "0:0": 0.06, "1:1": 0.20,
               "2:2": 0.20, "0:1": 0.10, "0:2": 0.04, "1:2": 0.10}
ZERO8 = dict.fromkeys(totals.KEYS, 0.0)


@pytest.fixture(scope="module")
def grid9():
    return dc_grid(1.5, 0.8, 0.0, 8)


def test_totals_gold(grid9):
    """总进球 8 档：键集合全等 + 逐档等于黄金值 + Σ=1。"""
    got = totals.buckets(grid9)
    assert set(got) == set(GOLD_TOTALS)
    assert got == pytest.approx(GOLD_TOTALS, abs=1e-6)
    assert sum(got.values()) == pytest.approx(1.0, abs=1e-6)


def test_scores31_gold(grid9):
    """31 键全等 + Σ=1 + 胜/平/负三组和分别等于黄金三向概率。"""
    got = scores31.buckets(grid9)
    assert len(KEYS31) == 31 and set(got) == KEYS31
    assert sum(got.values()) == pytest.approx(1.0, abs=1e-6)
    for name, keys in GROUP.items():
        assert sum(got[k] for k in keys) == pytest.approx(GOLD_WDL[name], abs=1e-6), name


def test_goals4_gold(grid9):
    """每队 8 档：键集合全等、两侧各自 Σ=1，且每档 = 独立行/列和（"7+" = h/a≥7 尾块）。"""
    home, away = goals4.team_buckets(grid9)
    assert set(home) == set(totals.KEYS) == set(away)
    refs = ([sum(row) for row in grid9], [sum(row[k] for row in grid9) for k in range(9)])
    for side, sums in zip((home, away), refs):
        assert sum(side.values()) == pytest.approx(1.0, abs=1e-6)
        for k in range(7):
            assert side[str(k)] == pytest.approx(sums[k], abs=1e-6), k
        assert side["7+"] == pytest.approx(sum(sums[7:]), abs=1e-6)


def test_hand_3x3_all_playtypes():
    """手算 3×3（Σ=1）逐桶对账，不推导直接数格子。
    8 档：0=0.06(0:0)、1=0.10(0:1)+0.12(1:0)=0.22、2=0.04(0:2)+0.20(1:1)+0.06(2:0)=0.30、3=0.10(1:2)+0.12(2:1)=0.22、
    4=0.20(2:2)、5/6/7+=0（h+a≤4 无更高档）；31 桶：1:0=.12 2:0=.06 2:1=.12 0:0=.06 1:1=.20 2:2=.20 0:1=.10 0:2=.04 1:2=.10，
    余 22 键=0；每队 8 档：主=行和 0.20/0.42/0.38；客=列和 0.24/0.42/0.34；≥3 档=0。"""
    assert totals.buckets(HAND33) == pytest.approx(HAND8T, abs=1e-12)
    assert scores31.buckets(HAND33) == pytest.approx({**dict.fromkeys(KEYS31, 0.0), **HAND_SCORES}, abs=1e-12)
    home, away = goals4.team_buckets(HAND33)
    assert home == pytest.approx({**ZERO8, "0": 0.20, "1": 0.42, "2": 0.38}, abs=1e-12)
    assert away == pytest.approx({**ZERO8, "0": 0.24, "1": 0.42, "2": 0.34}, abs=1e-12)


def _expected_key(h, a):
    """逐格反查用独立实现：官方命名表用字面量集合，不引用被测模块的表。"""
    if h == a:
        return f"{h}:{a}" if f"{h}:{a}" in DRAW4 else "平其它"
    if h > a:
        return f"{h}:{a}" if f"{h}:{a}" in WIN12 else "胜其它"
    return f"{h}:{a}" if f"{h}:{a}" in LOSE12 else "负其它"


def test_coverage_81_cells_no_leak_no_double_count():
    """逐格反查覆盖性：81 格权重两两互异（(h*9+a+1)/Σ）⇒ 漏格或重复计格必让某桶偏掉。"""
    raw = [[float(h * 9 + a + 1) for a in range(9)] for h in range(9)]
    total = sum(map(sum, raw))
    grid = [[p / total for p in row] for row in raw]
    want = dict.fromkeys(KEYS31, 0.0)
    for h, row in enumerate(grid):
        for a, p in enumerate(row):
            want[_expected_key(h, a)] += p
    assert sum(want.values()) == pytest.approx(1.0, abs=1e-6)
    assert want["胜其它"] > 0 and want["平其它"] > 0 and want["负其它"] > 0
    got = scores31.buckets(grid)
    assert set(got) == KEYS31
    assert got == pytest.approx(want, abs=1e-6)
