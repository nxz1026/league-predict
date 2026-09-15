"""L3a 市场层：十进制赔率 → 概率（比例去水）与庄家水钱。纯 stdlib，零 DB/网络/新依赖。"""

from __future__ import annotations

import math
from collections.abc import Mapping


def _validate(odds: Mapping[str, float]) -> None:
    """非 Mapping/选项<2/任一赔率非有限或 <=1 一律 ValueError（宁炸不静默），消息带值。"""
    if not isinstance(odds, Mapping):
        raise ValueError(f"odds 必须是 Mapping，得到 {type(odds).__name__}: {odds!r}")
    if len(odds) < 2:
        raise ValueError(f"至少需要 2 个选项，得到 {len(odds)} 个: {odds!r}")
    for k, v in odds.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"odds[{k!r}]={v!r} 非法（{type(v).__name__}）：赔率须为数值")
        if not math.isfinite(v) or v <= 1.0:
            raise ValueError(f"odds[{k!r}]={v!r} 非法：十进制赔率须为有限且 >1")


def implied(odds: Mapping[str, float]) -> dict[str, float]:
    """1/odds：含水隐含概率，Σ == 1 + margin；不改传入 dict，返回新 dict。"""
    _validate(odds)
    return {k: 1.0 / v for k, v in odds.items()}


def devig(odds: Mapping[str, float]) -> dict[str, float]:
    """比例去水 p_k = (1/odds_k) / Σ(1/odds_j)：同除一个常数 ⇒ 选项间比值不变，Σ == 1。"""
    raw = implied(odds)
    total = math.fsum(raw.values())
    return {k: v / total for k, v in raw.items()}


def margin(odds: Mapping[str, float]) -> float:
    """Σ(1/odds) - 1：庄家水钱比例（1.85/3.40/4.20 → 0.072753 = 7.28%）。"""
    return math.fsum(implied(odds).values()) - 1.0
