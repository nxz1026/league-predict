"""传统足彩「4 场进球」：主/客各自进球 8 档边际（两侧各自 Σ=1），供相关性链路复用。"""

from __future__ import annotations

from derive.totals import KEYS, TOP  # 与总进球共用同一档位定义（"0".."6","7+"）


def team_buckets(grid: list[list[float]]) -> tuple[dict[str, float], dict[str, float]]:
    """返回 (主队进球档, 客队进球档)；主队取行和、客队取列和，"7+" 为 ≥7 合并档。"""
    home: dict[str, float] = dict.fromkeys(KEYS, 0.0)
    away: dict[str, float] = dict.fromkeys(KEYS, 0.0)
    for h, row in enumerate(grid):
        for a, p in enumerate(row):
            home[KEYS[min(h, TOP)]] += p
            away[KEYS[min(a, TOP)]] += p
    return home, away
