"""L3a 市场层去水黄金用例：逐值 1e-9 对账 + 结构不变式 + 校验分支（纯函数，零 DB/网络）。

黄金值 = 队长独立 python 按定义复算（不复用本实现）的全精度值；题面 6/8 位显示是舍入形式：
  devig(1.85/3.40/4.20) = {home .5038814396612561, draw .2741707833450953, away .22194777699364857}
  Σ(1/odds) = 1.072753425694602（显示 1.07275343）；margin = 0.07275342569460208（显示 0.072753）
  两向 1.91/1.91：Σ = 1.0471204188481675，margin = 0.04712041884816753（显示 0.04712），devig = .5/.5
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from market.devig import devig, implied, margin  # noqa: E402

MAIN = {"home": 1.85, "draw": 3.40, "away": 4.20}
GOLD_MAIN = {"home": 0.5038814396612561, "draw": 0.2741707833450953, "away": 0.22194777699364857}
GROUPS = [MAIN, {"home": 2.10, "draw": 3.30, "away": 3.60}, {"home": 1.30, "draw": 5.50, "away": 9.00},
          {"home": 1.75, "draw": 3.60, "away": 4.80}, {"home": 1.91, "away": 1.91},
          {"home": 1.55, "draw": 4.00, "away": 6.25}, {"home": 2.05, "draw": 3.15, "away": 3.90}]


def test_gold_devig():
    """逐值 1e-9 相等 + 键集合全等 + 去水后 Σ == 1（1e-12）。"""
    got = devig(MAIN)
    assert set(got) == set(MAIN)
    for k, v in GOLD_MAIN.items():
        assert got[k] == pytest.approx(v, abs=1e-9)
    assert sum(got.values()) == pytest.approx(1.0, abs=1e-12)


def test_gold_margin_and_implied():
    """implied = 1/odds 原水；margin 与 Σimplied 对账，并复现题面显示的舍入值。"""
    raw = implied(MAIN)
    assert raw == pytest.approx({k: 1.0 / v for k, v in MAIN.items()}, abs=1e-15)
    assert margin(MAIN) == pytest.approx(0.07275342569460208, abs=1e-9)
    assert sum(raw.values()) == pytest.approx(1.072753425694602, abs=1e-9)
    assert round(margin(MAIN), 6) == 0.072753
    assert round(sum(raw.values()), 8) == 1.07275343


def test_two_way_still_has_water():
    """纯二元 1.91/1.91：去水后 .5/.5，但 margin 仍 > 0 —— 两边和 ≠ 1 本身就是水。"""
    two = {"home": 1.91, "away": 1.91}
    assert devig(two) == pytest.approx({"home": 0.5, "away": 0.5}, abs=1e-9)
    assert margin(two) == pytest.approx(0.04712041884816753, abs=1e-9)
    assert round(margin(two), 5) == 0.04712
    assert 0.0 < margin(two) < 0.05


@pytest.mark.parametrize("group", GROUPS)
def test_structural_invariant(group):
    """devig = implied 同除常数 S ⇒ devig[k]*S == 1/odds[k]，两两比值与 implied 一致。"""
    raw, got = implied(group), devig(group)
    s = math.fsum(raw.values())
    for k in group:
        assert got[k] * s == pytest.approx(1.0 / group[k], abs=1e-12)
    a, b = list(group)[0], list(group)[1]
    assert got[a] / got[b] == pytest.approx(raw[a] / raw[b], abs=1e-12)
    assert sum(got.values()) == pytest.approx(1.0, abs=1e-12)


def test_key_order_and_input_immutability():
    """键顺序无关；纯函数不许改传入 dict（被覆盖就再算不回原水）。"""
    assert devig(dict(reversed(list(MAIN.items())))) == devig(MAIN)
    snapshot = dict(MAIN)
    devig(MAIN)
    implied(MAIN)
    margin(MAIN)
    assert MAIN == snapshot


def test_devig_output_rejected_as_input():
    """去水结果（概率 ≤1）回灌必须炸：赔率口径要求 >1（概率当赔率用 = 记错账）。"""
    with pytest.raises(ValueError):
        devig(devig(MAIN))
    with pytest.raises(ValueError):
        margin(implied(MAIN))


BAD_ODDS = [({}, "{}"), ({"home": 1.85}, "1.85"), ({"home": 0.0, "away": 1.9}, "0.0"),
            ({"home": -1.9, "away": 1.9}, "-1.9"), ({"home": 1.0, "away": 1.0}, "1.0"),
            ({"home": float("nan"), "away": 1.9}, "nan"), ({"home": float("inf"), "away": 1.9}, "inf"),
            ({"home": True, "away": 1.9}, "True"), ({"home": "1.9", "away": 1.9}, "'1.9'"),
            ({"home": None, "away": 1.9}, "None"), ([1.85, 3.40], "Mapping"), (None, "Mapping")]


@pytest.mark.parametrize("bad, frag", BAD_ODDS)
@pytest.mark.parametrize("fn", [implied, devig, margin])
def test_bad_odds_valueerror(fn, bad, frag):
    """空/单选项/0/负/1.0/nan/inf/bool/str/None/非 Mapping 一律 ValueError，消息带 offending 值。"""
    with pytest.raises(ValueError) as err:
        fn(bad)
    assert frag in str(err.value)
