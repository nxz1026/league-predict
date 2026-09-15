"""竞彩官方比分玩法 31 选项：12 命名胜 +「胜其它」/4 命名平 +「平其它」/12 命名负 +「负其它」。"""

from __future__ import annotations

# 官方 12 个命名「胜」比分（h>a）；「负」12 项与其严格镜像
WIN_NAMED: tuple[tuple[int, int], ...] = (
    (1, 0), (2, 0), (2, 1), (3, 0), (3, 1), (3, 2),
    (4, 0), (4, 1), (4, 2), (5, 0), (5, 1), (5, 2),
)
LOSE_NAMED: tuple[tuple[int, int], ...] = tuple((a, h) for h, a in WIN_NAMED)
DRAW_NAMED: tuple[tuple[int, int], ...] = ((0, 0), (1, 1), (2, 2), (3, 3))

WIN_OTHER, DRAW_OTHER, LOSE_OTHER = "胜其它", "平其它", "负其它"

KEYS: tuple[str, ...] = (
    tuple(f"{h}:{a}" for h, a in WIN_NAMED) + (WIN_OTHER,)
    + tuple(f"{h}:{a}" for h, a in DRAW_NAMED) + (DRAW_OTHER,)
    + tuple(f"{h}:{a}" for h, a in LOSE_NAMED) + (LOSE_OTHER,)
)
_NAMED: dict[tuple[int, int], str] = {
    cell: f"{cell[0]}:{cell[1]}" for cell in WIN_NAMED + DRAW_NAMED + LOSE_NAMED
}


def _key(h: int, a: int) -> str:
    """格子 → 官方选项键：命名比分优先，其余按胜/平/负落「其它」桶。"""
    named = _NAMED.get((h, a))
    if named is not None:
        return named
    if h > a:
        return WIN_OTHER
    return LOSE_OTHER if h < a else DRAW_OTHER


def buckets(grid: list[list[float]]) -> dict[str, float]:
    """31 个官方比分选项概率；每格恰好入一个桶（不重不漏），Σ == 网格之和。"""
    out: dict[str, float] = dict.fromkeys(KEYS, 0.0)
    for h, row in enumerate(grid):
        for a, p in enumerate(row):
            out[_key(h, a)] += p
    return out
