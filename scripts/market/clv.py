"""L3a 市场层校准指标：CLV（模型概率 vs 收盘去水概率）、多元 Brier、log loss。纯 stdlib。"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

SUM_TOL = 1e-6


def _check_prob(p: float, name: str, lo: float, hi: float) -> None:
    """bool/非数值/非有限/越界一律 ValueError，消息带 offending 值。"""
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        raise ValueError(f"{name}={p!r} 非法（{type(p).__name__}）：概率须为数值")
    if not math.isfinite(p) or not lo <= p <= hi:
        raise ValueError(f"{name}={p!r} 非法：须落在 [{lo}, {hi}] 内且有限")


def _check_preds(preds: Mapping[str, float], outcome: str) -> None:
    """非 Mapping/空/概率越界/Σ 偏离 1 超容差/outcome 不在键里 → ValueError。"""
    if not isinstance(preds, Mapping) or not preds:
        raise ValueError(f"preds 必须为非空 Mapping，得到 {preds!r}")
    for k, p in preds.items():
        _check_prob(p, f"preds[{k!r}]", 0.0, 1.0)
    total = math.fsum(preds.values())
    if abs(total - 1.0) > SUM_TOL:
        raise ValueError(f"preds 概率和 {total!r} 偏离 1 超过 {SUM_TOL}：未归一不得打分")
    if outcome not in preds:
        raise ValueError(f"outcome={outcome!r} 不在 preds 键 {sorted(preds)!r} 中")


def clv(p_model: float, p_close: float) -> float:
    """ln(p_model / p_close)：>0 = 模型比收盘市场更看好该选项（p_close 须为去水收盘概率）。

    p_model=0 → ValueError（ln(0) 无定义），不许 -inf 混进账本。
    """
    _check_prob(p_model, "p_model", 0.0, 1.0)
    _check_prob(p_close, "p_close", 0.0, 1.0)
    if p_close == 0.0:
        raise ValueError(f"p_close={p_close!r} 非法：ln(x/0) 无定义")
    if p_model == 0.0:
        raise ValueError(f"p_model={p_model!r} 非法：ln(0) 无定义，不许 -inf 混进账本")
    return math.log(p_model / p_close)


def mean_clv(pairs: Iterable[tuple[float, float]]) -> float:
    """(p_model, p_close) 对的 CLV 均值；空序列 → ValueError（不许静默返回 0.0）。"""
    vals = [clv(m, c) for m, c in pairs]
    if not vals:
        raise ValueError("mean_clv 收到空序列：无样本，不返回默认值 0.0")
    return math.fsum(vals) / len(vals)


def brier(preds: Mapping[str, float], outcome: str) -> float:
    """多元 Brier = Σ_k (p_k - 1[k==outcome])²：未中奖项也计入（三元全错 = 2.0）。"""
    _check_preds(preds, outcome)
    hit = {outcome: 1.0}
    return math.fsum((p - hit.get(k, 0.0)) ** 2 for k, p in preds.items())


def log_loss(preds: Mapping[str, float], outcome: str) -> float:
    """-ln(p_outcome)：命中项概率为 0 时拒绝（-ln(0)=+inf 不许混进账本）。"""
    _check_preds(preds, outcome)
    p = preds[outcome]
    if p <= 0.0:
        raise ValueError(f"preds[{outcome!r}]={p!r} 非法：-ln(0) 无定义")
    return -math.log(p)
