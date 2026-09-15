"""黄金用例：对称解析解 / 方向敏感往返 γ 误差 0 / 真数据一阶条件 / 校验与兜底（零第三方依赖）。

真值来自队长 2026-09-15 独立实现钉死的那组数（γ*、atk、def、Σλ == 实际进球），见 .omp-logs/P0-MODEL1.report.txt。
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from model import fit as fitmod  # noqa: E402
from model import walk  # noqa: E402
from model.fit import ConvergenceError, fit_attack_defense, match_lambdas  # noqa: E402
from store import pg  # noqa: E402

PAIRS = (("A", "B"), ("A", "C"), ("B", "A"), ("B", "C"), ("C", "A"), ("C", "B"))
GOLD3 = {("epl", 2024): (1.064815, 575.0, 540.0), ("bundesliga", 2023): (1.280093, 553.0, 432.0),
         ("ligue1", 2023): (1.156658, 443.0, 383.0)}


def _roundtrip(gamma=1.25, repeats=10):
    """用真值生成 λ 当"进球数"：全部有序主客对 ×repeats（拟合只吃线性统计量 ⇒ 非整数进球合法）。"""
    atk, def_ = {"A": 1.4, "B": 1.0, "C": 1 / 1.4}, {"A": 0.8, "B": 1.1, "C": 0.9}
    return [(h, a, gamma * atk[h] * def_[a], atk[a] * def_[h]) for h, a in PAIRS for _ in range(repeats)]


@pytest.fixture()
def ro_conn():
    """ro 只读连接；连不上库就 skip，收尾 rollback（本文件不写任何表）。"""
    try:
        connection = pg.connect("ro")
    except Exception as exc:
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    yield connection
    connection.rollback()
    connection.close()


def test_gold1_symmetric_two_teams_and_unknown_team():
    """黄金 1：γ=1、atk 全 1、def 全 0.5、两场 λ=(0.5,0.5)；未知队名一律 ValueError（不外推）。"""
    fit = fit_attack_defense([("A", "B", 1, 0), ("B", "A", 1, 0)])
    assert (fit.atk, fit.def_, fit.gamma, fit.n_matches) == ({"A": 1.0, "B": 1.0}, {"A": 0.5, "B": 0.5}, 1.0, 2)
    assert match_lambdas(fit, "A", "B") == match_lambdas(fit, "B", "A") == (0.5, 0.5)
    with pytest.raises(ValueError, match="未知队名"):
        match_lambdas(fit, "A", "曼联")


def test_gold2_roundtrip_recovers_truth():
    """方向敏感往返：γ 误差必须为 0，atk/def/λ 误差 ≤1.5e-14（γ 漏乘/多乘时此用例必红，见报告 §8）。"""
    fit = fit_attack_defense(_roundtrip())
    assert fit.n_matches == 60 and fit.gamma == 1.25  # γ 误差 0：由数据一次算出、不进迭代
    assert fit.atk == pytest.approx({"A": 1.4, "B": 1.0, "C": 1 / 1.4}, abs=1.5e-14)  # Π atk ≡ 1
    assert fit.def_ == pytest.approx({"A": 0.8, "B": 1.1, "C": 0.9}, abs=1.5e-14)
    assert math.prod(fit.atk.values()) == pytest.approx(1.0, abs=1e-12)
    assert match_lambdas(fit, "A", "B") == pytest.approx((1.925, 0.8), abs=1e-12)  # 客场 λ 不乘 γ


def test_order_independence():
    """顺序无关：交错重排 60 场后 γ/atk/def 与重排前一致（1e-12）。"""
    rows = _roundtrip()
    a, b = fit_attack_defense(rows), fit_attack_defense(rows[1::2] + rows[::2])
    assert b.gamma == pytest.approx(a.gamma, abs=1e-12)
    assert b.atk == pytest.approx(a.atk, abs=1e-12) and b.def_ == pytest.approx(a.def_, abs=1e-12)


@pytest.mark.parametrize("case", sorted(GOLD3))
def test_gold3_real_data_first_order_condition(case, ro_conn):
    """黄金 3：真库三个 (联赛, 赛季) 的 Σλ主/Σλ客 == 实际主/客队进球（1e-9），并核对队长钉死的 γ。"""
    rows = [(h, a, float(gh), float(ga)) for h, a, gh, ga in ro_conn.execute(walk.TRAIN_SQL, case)]
    fit = fit_attack_defense(rows)
    lam = tuple(math.fsum(v) for v in zip(*(match_lambdas(fit, h, a) for h, a, _, _ in rows)))
    assert lam == pytest.approx((math.fsum(r[2] for r in rows), math.fsum(r[3] for r in rows)), abs=1e-9)
    assert lam == pytest.approx(GOLD3[case][1:], abs=1e-9)
    assert fit.gamma == pytest.approx(GOLD3[case][0], abs=5e-7)


def test_loud_failures(monkeypatch):
    """M3：坏入参点名 ValueError；迭代预算耗尽抛 ConvergenceError —— 绝不静默返回半成品。"""
    cases = [([], None, "为空"), ([("A", "B", 1, 0), (1, "B", 1, 0)], None, "队名非法"),
             ([("A", "B", 1, 0)], ["A"], "队名非法"), ([("A", "A", 1, 0)], None, "主客同队"),
             ([("A", "B", -1, 0)], None, "进球数非法"), ([("A", "B", True, 0)], None, "进球数非法")]
    for matches, teams, needle in cases:
        with pytest.raises(ValueError, match=needle):
            fit_attack_defense(matches, teams)
    monkeypatch.setattr(fitmod, "MAX_ITER", 0)
    with pytest.raises(ConvergenceError, match="0 轮未达"):
        fit_attack_defense([("A", "B", 1, 0), ("B", "A", 1, 0)])


def test_zero_goals_team_is_not_defaulted():
    """M3：GF 或 GA 为 0 ⇒ 强度不可辨识 ⇒ ValueError 带队名，绝不默认 1.0 兜底。"""
    with pytest.raises(ValueError, match="GA=0.0"):
        fit_attack_defense([("A", "B", 2, 0), ("A", "B", 3, 0)])  # A 两场零封 ⇒ A 的 GA=0
    with pytest.raises(ValueError, match="'C'") as never_scores:
        fit_attack_defense([("A", "C", 2, 0), ("C", "A", 0, 1), ("B", "C", 2, 0), ("C", "B", 0, 1), ("A", "B", 1, 1)])
    assert "GF=0.0" in str(never_scores.value)  # C 一场没进 ⇒ 强度不可辨识
