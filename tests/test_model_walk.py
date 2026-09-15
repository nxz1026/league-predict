"""真库单事务编排用例：最小 (联赛, 赛季) 子集跑两遍 + 四玩法归一/白名单 + 泄漏守卫；收尾整体 ROLLBACK。

⚠️ 库里已有生产 run（队长真跑）⇒ 断言一律相对增量（OMP-SKILL §9-33），绝不读全局绝对值。
本文件只写 model.*（app 角色；league_ing 连 SELECT 都被拒），收尾 rollback ⇒ 不留痕。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from model import walk  # noqa: E402
from store import pg  # noqa: E402

CASE = ("bundesliga", 2023)  # 306 场 / 18 队：本单最小的联赛赛季规模
COUNTS = {"had": 3, "crs": 31, "ttg": 8, "jqc": 8}  # 队长 11:32Z 实测的每个 (场, 玩法) 选项数


@pytest.fixture()
def conn():
    """app 角色（model.* 只有它有写权限）；连不上库就 skip，收尾 rollback 保证不留痕。"""
    try:
        connection = pg.connect("app")
    except Exception as exc:
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    yield connection
    connection.rollback()
    connection.close()


def _counts(conn) -> tuple:
    return conn.execute("select (select count(*) from model.pred_run), (select count(*) from model.pred_fixture),"
                        " (select count(*) from model.pred_market)").fetchone()


def test_market_shape_counts_and_whitelist(conn):
    """四玩法齐、每 (场, 玩法[, 侧]) Σp==1、选项数 3/31/8/8、hhad 与 haf 一条不落、params 口径正确。"""
    res = walk.run(conn, *CASE)
    run, n = res["run_id"], res["n_fixtures"]
    per_play = dict(conn.execute("select play_type, count(*) from model.pred_market where run_id = %s"
                                 " group by 1", (run,)).fetchall())
    assert per_play == {play: n * k for play, k in COUNTS.items()}
    assert conn.execute("select count(*) from model.pred_market where run_id = %s"
                        " and play_type in ('hhad', 'haf')", (run,)).fetchone()[0] == 0
    unnormalized = conn.execute(  # jqc 一行一个侧别（h:/a:）⇒ 归一化按侧分组；其余玩法整组归一
        "select count(*) from (select fixture_id, play_type, case when play_type = 'jqc'"
        " then left(option_code, 1) else '' end as side from model.pred_market where run_id = %s"
        " group by 1, 2, 3 having abs(sum(p) - 1) > 1e-9) x", (run,))
    assert unnormalized.fetchone()[0] == 0
    matrices = conn.execute("select count(*) from model.pred_fixture where run_id = %s"
                            " and jsonb_array_length(matrix) = 9 and features ? 'atk_home'", (run,)).fetchone()[0]
    assert matrices == n and res["n_market"] == n * sum(COUNTS.values())
    params, written = conn.execute("select params, n_fixtures from model.pred_run where run_id = %s", (run,)).fetchone()
    assert written == n and params["train_season"] < CASE[1] and set(params["plays"]) == set(COUNTS)
    assert params["gamma"] == pytest.approx(res["gamma"]) and params["rho"] == 0.2


def test_rerun_is_a_new_run_not_an_overwrite(conn):
    """跑两遍：新 run_id 不覆盖旧 run、行数按预期翻倍，且每个 run 的 pred_fixture 每场恰好一行。"""
    before = _counts(conn)
    first, second = walk.run(conn, *CASE), walk.run(conn, *CASE)
    after = _counts(conn)
    assert second["run_id"] != first["run_id"] and first["n_fixtures"] == second["n_fixtures"]
    assert (after[0] - before[0], after[1] - before[1]) == (2, 2 * first["n_fixtures"])
    assert after[2] - before[2] == 2 * first["n_market"]
    for run in (first["run_id"], second["run_id"]):
        rows, distinct = conn.execute("select count(*), count(distinct fixture_id) from model.pred_fixture"
                                      " where run_id = %s", (run,)).fetchone()
        assert rows == distinct == first["n_fixtures"]  # 一场一行、不重复


def test_unseen_promoted_teams_fall_back_not_skipped(conn):
    """当季新升班马不在训练季 ⇒ 该场照写并标 features.fallback（本单改口径：不再跳过）：epl 2024 当场验。"""
    targets = conn.execute(walk.TARGET_SQL, ("epl", 2024)).fetchall()
    trained = {name for row in conn.execute(walk.TRAIN_SQL, ("epl", 2023)) for name in row[:2]}
    unseen = [fid for fid, home, away in targets if home not in trained or away not in trained]
    res = walk.run(conn, "epl", 2024)
    assert unseen and res["skipped"] == 0 and res["n_fixtures"] == len(targets)
    assert res["n_fallback"] == len(unseen)
    marked = conn.execute("select count(*) from model.pred_fixture where run_id = %s and features->'fallback'"
                          " <> '{\"home\": \"fit\", \"away\": \"fit\"}'::jsonb", (res["run_id"],)).fetchone()[0]
    assert marked == len(unseen)


def test_leak_guard_and_season_pairs(conn):
    """M4：训练季必须严格更早；2022 无更早赛季 ⇒ 既不在可预测组合里，也不能被 run 当预测季。"""
    pairs = walk.season_pairs(conn)
    assert all(train < season for _, season, train in pairs) and 2022 not in {season for _, season, _ in pairs}
    before = _counts(conn)
    for args in (("epl", 2022), ("epl", 2023, 2023)):
        with pytest.raises(ValueError, match="泄漏防线"):
            walk.run(conn, *args)
    assert _counts(conn) == before  # 守卫在写任何行之前触发
