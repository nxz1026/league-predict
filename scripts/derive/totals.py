"""总进球玩法（竞彩官方 ttg）：8 档边际，键 "0".."6" 与合并档 "7+"。"""

from __future__ import annotations

KEYS = ("0", "1", "2", "3", "4", "5", "6", "7+")
TOP = len(KEYS) - 1  # "7+" 在 KEYS 中的下标


def buckets(grid: list[list[float]]) -> dict[str, float]:
    """h+a 的边际分布；"7+" = h+a>=7 的全部格子（8 档之和 == 网格之和）。"""
    out: dict[str, float] = dict.fromkeys(KEYS, 0.0)
    for h, row in enumerate(grid):
        for a, p in enumerate(row):
            out[KEYS[min(h + a, TOP)]] += p
    return out
