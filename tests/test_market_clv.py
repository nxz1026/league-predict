"""L3a 校准指标黄金用例：CLV / Brier / log loss 逐值 1e-9 对账 + 容差边界 + 校验（零 DB/网络）。

黄金值 = 队长独立 python 复算（不复用本实现）：
  clv(0.55, 0.50) = ln(1.1) = 0.09531017980432493（显示 0.0953102）；clv(0.50, 0.50) = 0.0
  mean_clv([(0.55,.50),(0.45,.50)]) = (ln1.1 + ln0.9)/2 = -0.005025167926750673（显示 -0.0050252）
  brier({home .5, draw .3, away .2}, 'home') = 0.38；brier({home .6, away .4}, 'home') = 0.32000000000000006
  log_loss(前例, 'home') = -ln(0.5) = 0.6931471805599453；'draw' → -ln(0.3) = 1.2039728043259361
  全对 {home 1, draw 0, away 0} 'home' → 0.0；同组 outcome='away' → (1-0)²+(0-0)²+(0-1)² = 2.0
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from market.clv import brier, clv, log_loss, mean_clv  # noqa: E402

THREE = {"home": 0.5, "draw": 0.3, "away": 0.2}
ONEHOT = {"home": 1.0, "draw": 0.0, "away": 0.0}
PAIRS = [(0.55, 0.50), (0.45, 0.50)]


def test_gold_clv():
    """ln 比值逐值 1e-9：>0 = 模型比收盘更看好；同值 → 恰好 0.0（不留 1e-17 噪声）。"""
    assert clv(0.55, 0.50) == pytest.approx(0.09531017980432493, abs=1e-9)
    assert round(clv(0.55, 0.50), 7) == 0.0953102
    assert clv(0.50, 0.50) == 0.0
    assert clv(0.30, 0.50) < 0.0 < clv(0.70, 0.50)


def test_mean_clv_gold():
    """均值对账（题面 -0.0050252）；单样本均值 == 该样本 CLV；空序列 ValueError。"""
    assert mean_clv(PAIRS) == pytest.approx(-0.005025167926750673, abs=1e-9)
    assert round(mean_clv(PAIRS), 7) == -0.0050252
    assert mean_clv([PAIRS[0]]) == clv(*PAIRS[0])
    assert mean_clv(iter(PAIRS)) == pytest.approx(mean_clv(PAIRS), abs=1e-15)
    with pytest.raises(ValueError):
        mean_clv([])
    with pytest.raises(ValueError):
        mean_clv(iter([]))


def test_gold_brier_and_log_loss():
    """逐值对账：Brier 含未中奖项，log loss == -ln(p_outcome)。"""
    assert brier(THREE, "home") == pytest.approx(0.38, abs=1e-9)
    assert brier({"home": 0.6, "away": 0.4}, "home") == pytest.approx(0.32000000000000006, abs=1e-9)
    assert log_loss(THREE, "home") == pytest.approx(0.6931471805599453, abs=1e-9)
    assert log_loss(THREE, "draw") == pytest.approx(1.2039728043259361, abs=1e-9)
    assert log_loss(THREE, "away") == pytest.approx(-math.log(0.2), abs=1e-15)


def test_boundaries_all_right_all_wrong():
    """全对 → 0.0；全错（one-hot 猜 away 开 home）→ Brier 2.0（不是 4.0），log loss 拒。"""
    assert brier(ONEHOT, "home") == pytest.approx(0.0, abs=1e-12)
    assert log_loss(ONEHOT, "home") == pytest.approx(0.0, abs=1e-12)
    assert brier(ONEHOT, "away") == pytest.approx(2.0, abs=1e-12)
    with pytest.raises(ValueError):
        log_loss(ONEHOT, "away")


def test_key_order_and_input_immutability():
    """打分只依赖 {k: p} 本身：键顺序无关；不改传入 dict。"""
    snapshot = dict(THREE)
    assert brier(dict(reversed(list(THREE.items()))), "home") == brier(THREE, "home")
    brier(THREE, "home")
    log_loss(THREE, "away")
    assert THREE == snapshot


@pytest.mark.parametrize("p_model, p_close", [(0.0, 0.5), (-0.1, 0.5), (1.1, 0.5), (float("nan"), 0.5),
                                              (float("inf"), 0.5), (True, 0.5), ("0.5", 0.5), (None, 0.5),
                                              (0.5, 0.0), (0.5, -0.1), (0.5, 1.1), (0.5, float("nan")),
                                              (0.5, float("inf")), (0.5, True), (0.5, "0.5"), (0.5, None)])
def test_clv_bad_inputs(p_model, p_close):
    """p_model ∈ [0,1] 但 0 拒（ln0 不许 -inf）；p_close ∈ (0,1]；bool/str/None/nan/inf → ValueError。"""
    with pytest.raises(ValueError):
        clv(p_model, p_close)


def test_preds_validation_and_tolerance():
    """未归一（偏 1 超 1e-6）不得打分；容差内放行；outcome 缺失/越界/空/非 Mapping → ValueError。"""
    assert brier({"home": 0.5000005, "away": 0.5}, "home") == pytest.approx(0.49999950000025006, abs=1e-9)
    for bad in ({"home": 0.500002, "away": 0.5}, {"home": 0.5, "away": 0.4}, {"home": 1.5, "away": -0.5},
                {}, [0.5, 0.5], None):
        with pytest.raises(ValueError):
            brier(bad, "home")
    with pytest.raises(ValueError):
        log_loss(THREE, "over")
    with pytest.raises(ValueError):
        brier(THREE, 1)
