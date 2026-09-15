"""P0-MODEL2 新口径用例：未见队（升班马）兜底落库 + jqc 两侧 4 档（既有用例仍在 test_model_walk.py）。

单开本文件的原因：既有两文件加满新用例会顶破 100 行机检上限（见报告 §偏差）。
⚠️ 库里已有生产 run ⇒ 断言一律相对增量（OMP-SKILL §9-33）；收尾 rollback ⇒ 不留痕。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from derive import goals4  # noqa: E402
from model import walk  # noqa: E402
from store import pg  # noqa: E402

SMALL = ("bundesliga", 2023)  # 306 场：本单最小规模，jqc 行数对账用
FALLBACK = ("epl", 2024)  # 380 场，其中 108 场涉及训练季（2023）没有的升班马


@pytest.fixture()
def conn():
    """app 角色（只有它有 model.* 写权限）；连不上库就 skip，收尾 rollback 保证不留痕。"""
    try:
        connection = pg.connect("app")
    except Exception as exc:
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    yield connection
    connection.rollback()
    connection.close()


def test_fallback_lambdas_use_gamma_and_opponent_only(conn):
    """兜底队 λ 只由 γ 与对手强度决定（prior=1.0 手算对照，≤1e-12）：未见队自身强度一律不参与。"""
    train = [(h, a, float(gh), float(ga)) for h, a, gh, ga in conn.execute(walk.TRAIN_SQL, ("epl", 2023))]
    fit = walk.fit_attack_defense(train)
    res = walk.run(conn, *FALLBACK)
    names = {f: (h, a) for f, h, a in conn.execute(walk.TARGET_SQL, FALLBACK)}
    rows = conn.execute("select fixture_id, lambda_home::float8, lambda_away::float8, features"
                        " from model.pred_fixture where run_id = %s and features->'fallback'"
                        " <> '{\"home\": \"fit\", \"away\": \"fit\"}'::jsonb", (res["run_id"],)).fetchall()
    assert len(rows) == res["n_fallback"] == 108
    for fid, lam_h, lam_a, feats in rows:
        home, away = names[fid]
        if home not in fit.atk:  # 主队未见 ⇒ λ_h = γ·1.0·def_away，features 落先验
            assert feats["atk_home"] == 1.0 and lam_h == pytest.approx(res["gamma"] * feats["def_away"], abs=1e-12)
        if away not in fit.atk:  # 客队未见 ⇒ λ_a = 1.0·def_home（主队也未见时 def_home 同样取先验 1.0）
            assert feats["def_away"] == 1.0
            assert lam_a == pytest.approx(fit.def_.get(home, 1.0), abs=1e-12)


def test_jqc_two_sides_four_buckets(conn):
    """jqc 每场 8 行（h:0..3+ / a:0..3+）、两侧各自 Σ=1、'3+' == goals4 的 3 档及以后尾块、无静默丢行。"""
    res = walk.run(conn, *SMALL)
    run, n = res["run_id"], res["n_fixtures"]
    rows, distinct = conn.execute("select count(*), count(distinct (fixture_id, option_code)) from model.pred_market"
                                  " where run_id = %s and play_type = 'jqc'", (run,)).fetchone()
    assert rows == distinct == n * 8
    sides = dict(conn.execute("select left(option_code, 1), count(*) from model.pred_market"
                              " where run_id = %s and play_type = 'jqc' group by 1", (run,)).fetchall())
    assert sides == {"h": n * 4, "a": n * 4}
    fid, matrix = conn.execute("select fixture_id, matrix from model.pred_fixture where run_id = %s"
                               " order by fixture_id limit 1", (run,)).fetchone()
    got = dict(conn.execute("select option_code, p::float8 from model.pred_market where run_id = %s"
                            " and fixture_id = %s and play_type = 'jqc'", (run, fid)).fetchall())
    want_h, want_a = goals4.team_buckets(matrix)  # 独立 oracle：从落库矩阵重算 8 档边际
    for side, want in (("h", want_h), ("a", want_a)):
        head, tail = [want[k] for k in ("0", "1", "2")], sum(p for k, p in want.items() if k not in ("0", "1", "2"))
        assert [got[f"{side}:{k}"] for k in ("0", "1", "2")] == pytest.approx(head, abs=1e-12)
        assert got[f"{side}:3+"] == pytest.approx(tail, abs=1e-12)
        assert sum(got[f"{side}:{k}"] for k in ("0", "1", "2", "3+")) == pytest.approx(1.0, abs=1e-9)
