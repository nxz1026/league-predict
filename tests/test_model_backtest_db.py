"""P0-BACKTEST1 真库用例（单事务，收尾 ROLLBACK ⇒ 不留痕）：合成 run 的落库副作用与计数；本文件兼脚手架
（`build_scenario`/`_dists`/`conn`/`PER_GROUP`），汇总那半边（⑥+T4）在 test_model_backtest_report.py import（先例：
test_upsert_from_raw ← test_align），拆文件为顶住 100 行上限；⚠️ 库里已有生产 run ⇒ 断言限定自造 run（§9-33）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from derive import scores31, totals  # noqa: E402
from model import backtest  # noqa: E402
from store import pg  # noqa: E402

FIT = {"home": "fit", "away": "fit"}  # features.fallback 的"两队都是拟合队"原值（walk.py 写的就是它）
PRIOR = {"home": "league_avg_prior", "away": "league_avg_prior"}  # 升班马兜底（walk.sides 写的原值）
EPS_LOSS = 13.815510557964274  # −ln(1e-6)：p=0 中奖时的 log_loss（钉住汇总 SQL 与 Python 的 eps 同值）
JQC = ("0", "1", "2", "3+")
PER_GROUP = """SELECT count(*) FROM (SELECT fixture_id, play_type,
    CASE WHEN play_type = 'jqc' THEN left(option_code, 1) ELSE '' END AS side
  FROM analysis.backtest_market WHERE src_run = %s GROUP BY 1, 2, 3 HAVING sum(outcome) <> 1) x"""


@pytest.fixture()
def conn():
    """app 角色（model/analysis 只有它有写权限）；连不上库就 skip，收尾 rollback 保证不留痕。"""
    try:
        connection = pg.connect("app")
    except Exception as exc:
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    yield connection
    connection.rollback()
    connection.close()


def _dists(ft_h: int, ft_a: int) -> dict[str, dict[str, float]]:
    """四玩法合成概率（中奖项手算：2:1 ⇒ "2:1"/"3"/h:2+a:1，0:0 ⇒ "0:0"/"0"/h:0+a:0）；had 恒 {home: 0.0,
    draw: 0.5, away: 0.5} ⇒ "2:1 那场"的中奖项 p=0：hit=0 与 eps 口径一起钉住。"""
    jqc = {f"{side}:{bucket}": (0.7 if bucket == ("3+" if goals > 2 else str(goals)) else 0.1)
           for side, goals in (("h", ft_h), ("a", ft_a)) for bucket in JQC}
    return {"had": {"home": 0.0, "draw": 0.5, "away": 0.5},
            "crs": {c: (0.25 if c == f"{ft_h}:{ft_a}" else 0.75 / 30) for c in scores31.KEYS},
            "ttg": {c: (0.65 if c == str(ft_h + ft_a) else 0.35 / 7) for c in totals.KEYS}, "jqc": jqc}


def _fixture(conn, ft_h: int, ft_a: int) -> int:
    """按真比分取一场真 fixture（2:1 / 0:0 都是官方命名比分 ⇒ 中奖项唯一、手算基准固定）。"""
    return conn.execute("SELECT f.fixture_id FROM fact.fixture f JOIN fact.fixture_result r"
                        " ON r.fixture_id = f.fixture_id AND r.source = 'api_football'"
                        " WHERE f.status = 'ft' AND f.round <> 'Relegation Round' AND r.ft_h = %s"
                        " AND r.ft_a = %s ORDER BY f.fixture_id LIMIT 1", (ft_h, ft_a)).fetchone()[0]


def build_scenario(conn) -> tuple[int, int, int]:
    """造合成 run：2 场有 label（2:1 拟合 / 0:0 兜底）+ 1 场被 label 谓词排除的（no_label）。

    返回 (run_id, 2:1 场, 0:0 场)；run_id 由 IDENTITY 发（绝不与生产 run 撞），全部落进调用方的事务里。
    """
    a, b = _fixture(conn, 2, 1), _fixture(conn, 0, 0)
    orphan = conn.execute("SELECT fixture_id FROM fact.fixture WHERE status <> 'ft'"
                          " ORDER BY fixture_id LIMIT 1").fetchone()[0]
    plans = [(a, FIT, _dists(2, 1)), (b, PRIOR, _dists(0, 0)), (orphan, FIT, {"had": {"home": 1.0}})]
    run = conn.execute("INSERT INTO model.pred_run (params, n_fixtures, note) VALUES ('{}'::jsonb, 2,"
                       " 'P0-BACKTEST1 合成') RETURNING run_id").fetchone()[0]
    market = []
    for fixture_id, fallback, dists in plans:
        conn.execute("INSERT INTO model.pred_fixture (run_id, fixture_id, lambda_home, lambda_away, matrix,"
                     " features) VALUES (%s, %s, 1, 1, '[[1]]'::jsonb, %s::jsonb)",
                     (run, fixture_id, json.dumps({"fallback": fallback})))
        market += [(run, fixture_id, play, code, p) for play, dist in dists.items() for code, p in dist.items()]
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO model.pred_market (run_id, fixture_id, play_type, option_code, p)"
                        " VALUES (%s, %s, %s, %s, %s)", market)
    return run, a, b


def test_run_writes_outcomes_counts_and_null_clv(conn):
    """⑤ 合成 run：每场 50 行、计数正确、中奖项手算对得上、sum(outcome) 每组恰 1（jqc 每侧恰 1）、
    clv 全 NULL（T2）、重跑幂等（同 src_run 不翻倍）。"""
    run, a, _b = build_scenario(conn)
    res = backtest.run(conn, run)
    assert (res["n_rows"], res["n_fixtures"], res["plays"]) == (
        100, 2, {"had": 6, "crs": 62, "ttg": 16, "jqc": 16})  # 2 场 × (3+31+8+8) 行，无 label 那场不计
    assert res["no_label"] == 1  # 无 label 的场计入并返回，不静默丢
    hits = conn.execute("SELECT play_type, option_code FROM analysis.backtest_market WHERE src_run = %s"
                        " AND fixture_id = %s AND outcome = 1 ORDER BY 1, 2", (run, a)).fetchall()
    assert hits == [("crs", "2:1"), ("had", "home"), ("jqc", "a:1"), ("jqc", "h:2"), ("ttg", "3")]
    assert dict(conn.execute("SELECT play_type, sum(outcome) FROM analysis.backtest_market WHERE src_run = %s"
                             " GROUP BY 1", (run,)).fetchall()) == {"had": 2, "crs": 2, "ttg": 2, "jqc": 4}
    assert conn.execute(PER_GROUP, (run,)).fetchone()[0] == 0  # T3 的 jqc 例外：按侧别前缀分组
    assert conn.execute("SELECT count(*) FROM analysis.backtest_market WHERE src_run = %s AND clv IS NOT NULL",
                        (run,)).fetchone()[0] == 0  # T2：绝不许 0.0 占位
    assert backtest.run(conn, run)["n_rows"] == res["n_rows"] == conn.execute(
        "SELECT count(*) FROM analysis.backtest_market WHERE src_run = %s", (run,)).fetchone()[0]
