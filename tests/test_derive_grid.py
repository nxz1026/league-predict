"""L3a 派生输入黄金用例：归一化硬要求、ρ=0 独立泊松 oracle、非法输入拒绝（零依赖）。

手算 3×3 归一矩阵（原始 [[6,10,4],[12,20,10],[6,12,20]]，Σ=100）：
    0.06 0.10 0.04
    0.12 0.20 0.10
    0.06 0.12 0.20
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core.model.poisson import _dc_pmf_grid, poisson_pmf  # noqa: E402
from derive.grid import dc_grid, renormalize  # noqa: E402

RAW_SUM = 0.999972083662318  # 队长实测：kernel 9×9 原始和 ≠ 1（差 2.8e-5 → 归一化是硬要求）


def test_dc_grid_is_normalized_9x9():
    grid = dc_grid(1.5, 0.8, 0.0, 8)
    assert len(grid) == 9 and all(len(row) == 9 for row in grid)
    assert sum(map(sum, grid)) == pytest.approx(1.0, abs=1e-12)


def test_kernel_raw_sum_needs_renormalize():
    """内核原矩阵 Σ=0.999972083662318，直接当边际用会漏 2.8e-5 概率。"""
    raw = sum(map(sum, _dc_pmf_grid(1.5, 0.8, 0.0, 8)))
    assert raw == pytest.approx(RAW_SUM, abs=1e-12)
    assert abs(raw - 1.0) > 1e-5


def test_rho0_matches_independent_poisson_outer_product():
    """ρ=0 ⇒ DC 退化为独立泊松外积；逐格完全相等（不依赖 DC 实现的独立 oracle）。"""
    grid = _dc_pmf_grid(1.5, 0.8, 0.0, 8)
    devs = [abs(grid[h][a] - poisson_pmf(h, 1.5) * poisson_pmf(a, 0.8))
            for h in range(9) for a in range(9)]
    assert max(devs) == 0.0


def test_max_goals_shape():
    grid = dc_grid(1.2, 0.9, 0.2, 3)
    assert len(grid) == 4 and all(len(row) == 4 for row in grid)
    assert sum(map(sum, grid)) == pytest.approx(1.0, abs=1e-12)


def test_renormalize_hand_3x3():
    """手算：原始 Σ=6+10+4+12+20+10+6+12+20=100，归一后每格 = 原值/100，逐格核对。"""
    out = renormalize([[6.0, 10.0, 4.0], [12.0, 20.0, 10.0], [6.0, 12.0, 20.0]])
    flat = [p for row in out for p in row]
    assert flat == pytest.approx([0.06, 0.10, 0.04, 0.12, 0.20, 0.10, 0.06, 0.12, 0.20], abs=1e-12)
    assert sum(flat) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("bad", [
    [], [[]], [[0.5, 0.5], [0.5]], [[-0.1, 0.6], [0.5, 0.5]], [[0.0, 1.0], [1.0, 1.0]],
    [[float("nan"), 0.5], [0.5, 0.5]], [[float("inf"), 0.5], [0.5, 0.5]], [[0.5, 0.5], [0.5, "x"]],
])
def test_bad_grid_rejected(bad):
    """空/非方阵/负/零/NaN/inf/非数值 → 一律 ValueError，绝不静默出错值。"""
    with pytest.raises(ValueError):
        renormalize(bad)


def test_bad_params_rejected():
    """λ 非正或非数值、ρ 非有限、max_goals 负 → 一律 ValueError。"""
    for lam_h, lam_a in [(-1.0, 0.8), (1.5, 0.0), (float("nan"), 0.8), ("1.5", 0.8)]:
        with pytest.raises(ValueError):
            dc_grid(lam_h, lam_a)
    with pytest.raises(ValueError):
        dc_grid(1.5, 0.8, float("nan"), 8)
    with pytest.raises(ValueError):
        dc_grid(1.5, 0.8, 0.2, -1)
