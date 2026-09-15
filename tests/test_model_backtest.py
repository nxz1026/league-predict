"""P0-BACKTEST1 纯指标用例：手算可核（工单 ①②③④），零 DB/零网络、不依赖任何真库存量。

真库那半边（⑤ 合成 run 落库 + ⑥ 汇总与 Python 侧逐值对账 + T4 空作用域）在 tests/test_model_backtest_db.py：
两半相加顶破 100 行机检上限，按 tests/test_model_walk_fallback.py 的同一先例拆文件（工单原意是
"合成用例不依赖真库存量"，不是"必须一个文件"）。

手算基准（工单给的 0.275/1.105 与"多类 Brier = Σ(p−o)²"这条公式**自相矛盾**，见报告 §偏差）：
  {0.6, 0.25, 0.15} 主胜中奖 ⇒ 0.4² + 0.25² + 0.15² = 0.245；客胜中奖 ⇒ 0.6² + 0.25² + 0.85² = 1.145
  两值之差恒 = 2(p_home − p_away) = 0.9（任何三选项分布都成立 ⇒ 工单那两个数不可能是本公式的取值）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from model import backtest  # noqa: E402


def test_brier_and_hit_are_hand_computable():
    """① {0.6,0.25,0.15}：主胜 ⇒ brier=0.245/hit=1；客胜 ⇒ brier=1.145/hit=0（含**未中奖项**）。"""
    home = backtest.score_options([(0.6, 1), (0.25, 0), (0.15, 0)])
    away = backtest.score_options([(0.6, 0), (0.25, 0), (0.15, 1)])
    assert (home["n"], home["hit"], home["brier"]) == (3, 1, pytest.approx(0.245))
    assert (away["hit"], away["brier"]) == (0, pytest.approx(1.145))
    assert away["brier"] - home["brier"] == pytest.approx(0.9)  # 未中奖项若被漏掉，这条恒等式立刻破
    assert home["degenerate"] is False and home["eps"] == backtest.EPS


def test_zero_probability_winner_uses_explicit_eps():
    """② p=0 中奖 ⇒ log_loss 恰 = −ln(eps)，eps 是显式参数且**回显**在返回值里（默认 1e-6）。"""
    res = backtest.score_options([(0.0, 1), (1.0, 0)], eps=1e-3)
    assert res["log_loss"] == pytest.approx(6.907755278982137) and res["eps"] == 1e-3
    assert (res["hit"], res["brier"]) == (0, pytest.approx(2.0))  # 两侧都记反：1 + 1
    assert backtest.score_options([(0.0, 1), (1.0, 0)])["log_loss"] == pytest.approx(13.815510557964274)


def test_perfect_prediction_and_degenerate_single_option():
    """③ 全对 ⇒ brier=0、log_loss=−0.0（== 0）；单选项退化 ⇒ 指标恒 0 且标 degenerate（Σp=1 ⇒ 必中）。"""
    perfect = backtest.score_options([(1.0, 1), (0.0, 0), (0.0, 0)])
    assert (perfect["brier"], perfect["log_loss"], perfect["hit"]) == (0.0, 0.0, 1)
    assert backtest.score_options([(1.0, 1)]) == {"n": 1, "brier": 0.0, "log_loss": 0.0, "hit": 1,
                                                  "eps": backtest.EPS, "degenerate": True}


def test_empty_group_does_not_crash():
    """④ n=0 ⇒ 只有 n/eps，不崩（空玩法/空库边界）。"""
    assert backtest.score_options([]) == {"n": 0, "eps": backtest.EPS}


def test_winners_covers_only_the_four_predicted_plays():
    """判奖口径只认已落库的四玩法：未注册玩法（haf/hhad）点名拒绝，不许给假中奖项。"""
    assert backtest.winners("had", 2, 1) == ["home"] and backtest.winners("ttg", 2, 1) == ["3"]
    assert backtest.winners("crs", 9, 0) == ["胜其它"] and backtest.winners("jqc", 0, 4) == ["h:0", "a:3+"]
    with pytest.raises(KeyError, match="没有判奖口径"):
        backtest.winners("haf", 1, 0)
