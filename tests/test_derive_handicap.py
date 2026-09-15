"""L3a 让球胜平负黄金用例：竞彩口径（让球加主队）、结构不变式、退化边界、int 硬拒。
黄金值 = 队长独立算的 dc_grid(1.5, 0.8, ρ=0.2, max_goals=8) 归一矩阵，容差 1e-6（手算组 1e-12）。
手算 3×3（Σ=1.0）逐格：  a=0   a=1   a=2          line=0 归桶：主=h>a {.15,.10,.10}=.35
                h=0  .20   .10   .05                     平=h==a {.20,.20,.05}=.45
                h=1  .15   .20   .05                     客=h<a  {.10,.05,.05}=.20
                h=2  .10   .10   .05          line=-1 判 h-1 对 a：主={(2,0).10}=.10
                                                          平={(1,0).15,(2,1).10}=.25
                                                          客=其余 6 格 {.20,.10,.05,.20,.05,.05}=.65
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from derive.grid import dc_grid  # noqa: E402
from derive.handicap import KEYS, probs  # noqa: E402

GOLD = {
    0: {"home": 0.562667, "draw": 0.213104, "away": 0.224229},
    -1: {"home": 0.277783, "draw": 0.284884, "away": 0.437333},
    -2: {"home": 0.112401, "draw": 0.165382, "away": 0.722217},
    1: {"home": 0.775771, "draw": 0.163176, "away": 0.061052},
}
HAND = [[0.20, 0.10, 0.05], [0.15, 0.20, 0.05], [0.10, 0.10, 0.05]]


@pytest.fixture(scope="module")
def grid9():
    return dc_grid(1.5, 0.8, 0.2, 8)


@pytest.mark.parametrize("line", sorted(GOLD))
def test_gold_lines(grid9, line):
    """4 条黄金线：键集合全等 + 逐项等于队长数值 + 三向和 == 1（1e-12）。"""
    got = probs(grid9, line)
    assert set(got) == set(KEYS) == {"home", "draw", "away"}
    assert got == pytest.approx(GOLD[line], abs=1e-6)
    assert sum(got.values()) == pytest.approx(1.0, abs=1e-12)


def test_structural_invariants(grid9):
    """结构不变式（比数值更能抓错）：+1 把 0 线平局全并进主胜；-1 把 0 线平局全并进客胜。"""
    p0, plus, minus = probs(grid9, 0), probs(grid9, 1), probs(grid9, -1)
    assert plus["home"] == pytest.approx(p0["home"] + p0["draw"], abs=1e-12)
    assert minus["away"] == pytest.approx(p0["away"] + p0["draw"], abs=1e-12)
    assert plus["home"] > p0["home"] > minus["home"] > probs(grid9, -2)["home"]


def test_hand_3x3():
    """手算 3×3 逐桶对账（算式见文件头注释），含 +1 线：主 = 0 线主+.45 平 = .80。"""
    assert probs(HAND, 0) == pytest.approx({"home": 0.35, "draw": 0.45, "away": 0.20}, abs=1e-12)
    assert probs(HAND, -1) == pytest.approx({"home": 0.10, "draw": 0.25, "away": 0.65}, abs=1e-12)
    assert probs(HAND, 1) == pytest.approx({"home": 0.80, "draw": 0.15, "away": 0.05}, abs=1e-12)


def test_degenerate_boundaries(grid9):
    """越界线不报错，但必须落进全主胜/全客胜退化边界（9×9 网格翻不动）。"""
    assert probs(grid9, 10) == pytest.approx({"home": 1.0, "draw": 0.0, "away": 0.0}, abs=1e-12)
    assert probs(grid9, -10) == pytest.approx({"home": 0.0, "draw": 0.0, "away": 1.0}, abs=1e-12)


@pytest.mark.parametrize("bad", [1.0, -1.0, 0.0, True, False, "1", None])
def test_non_int_line_rejected(grid9, bad):
    """float（哪怕整数值）/bool/str/None 一律 TypeError：True 不许当 1 混进来。"""
    with pytest.raises(TypeError):
        probs(grid9, bad)
