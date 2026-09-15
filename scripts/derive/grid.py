"""L3a 派生输入：Dixon-Coles 比分概率矩阵（归一化到 Σ=1 的纯函数包装，零依赖）。"""

from __future__ import annotations

import math

from core.constants import MAX_GOALS_MC
from core.model.poisson import _dc_pmf_grid


def _validate(grid: list[list[float]]) -> None:
    """空矩阵/非方阵/非有限或非正概率一律 ValueError（宁炸不静默）。"""
    if not grid or not grid[0]:
        raise ValueError("grid 为空")
    n = len(grid)
    if any(len(row) != n for row in grid):
        raise ValueError(f"grid 非方阵：{n} 行，各行长 {[len(row) for row in grid]}")
    for h, row in enumerate(grid):
        for a, p in enumerate(row):
            if not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0.0:
                raise ValueError(f"grid[{h}][{a}]={p!r} 非法：概率须为有限正数")


def renormalize(grid: list[list[float]]) -> list[list[float]]:
    """整体缩放使 Σ == 1；网格本身非法直接抛 ValueError。"""
    _validate(grid)
    total = math.fsum(math.fsum(row) for row in grid)
    return [[p / total for p in row] for row in grid]


def dc_grid(lambda_h: float, lambda_a: float, rho: float = 0.2,
            max_goals: int = MAX_GOALS_MC) -> list[list[float]]:
    """内核 _dc_pmf_grid 的归一化包装：内核原矩阵 Σ≈0.999972，不归一化会漏概率。"""
    if not isinstance(lambda_h, (int, float)) or not isinstance(lambda_a, (int, float)):
        raise ValueError(f"λ 必须为数值：λ_h={lambda_h!r}, λ_a={lambda_a!r}")
    if not (lambda_h > 0 and lambda_a > 0):
        raise ValueError(f"λ 必须为正：λ_h={lambda_h!r}, λ_a={lambda_a!r}")
    if not isinstance(rho, (int, float)) or not math.isfinite(rho):
        raise ValueError(f"ρ 必须为有限数值：ρ={rho!r}")
    if not isinstance(max_goals, int) or max_goals < 0:
        raise ValueError(f"max_goals 必须为非负整数：{max_goals!r}")
    return renormalize(_dc_pmf_grid(lambda_h, lambda_a, rho, max_goals))
