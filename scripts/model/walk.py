"""上一季拟合 → 当季预测：λ + 9×9 矩阵 + 四玩法概率落 model.*（真跑由队长执行；本模块零网络）。

取数口径 = _SCOPE 的谓词逐字照工单：status='ft' AND round <> 'Relegation Round' 且结果取 source='api_football'
行（排除 3 场升降级附加赛 aet/pen：90 分钟口径不一致，会污染 λ）。训练季 = 同联赛严格更早的最大赛季（run()
硬守卫）；2022 只当训练集、永不作预测目标。model.* 只有 app 角色可写（league_ing 连 SELECT 都 42501）。
本单缺口（不许 0.0 占位）：hhad 要竞彩官方让球线（盘口到货后才有）；haf 未注册（registry 直接 KeyError）；
jqc 落主队 8 档（PK 无侧别列 ⇒ 客队边际不落库，需要时用 pred_fixture.matrix 重算，无失真）；当季新升班马
不在训练季 ⇒ 该场跳过并计数（不给新队编强度）。
"""
import argparse
import json
import subprocess

from core.constants import DC_RHO, MAX_GOALS_MC
from core.log import logger
from derive.grid import dc_grid
from derive.registry import derive_play
from model.fit import fit_attack_defense, match_lambdas
from store import pg

PLAYS = ("had", "crs", "ttg", "jqc")  # 本单只写这四种；hhad 缺官方让球线、haf 未注册
SEASONS_SQL = "SELECT DISTINCT league_key, season FROM fact.fixture WHERE status = 'ft' AND round <> 'Relegation Round'"
_SCOPE = """FROM fact.fixture f
  JOIN fact.fixture_result r ON r.fixture_id = f.fixture_id AND r.source = 'api_football'
  JOIN ref.team th ON th.team_id = f.home_team_id JOIN ref.team ta ON ta.team_id = f.away_team_id
 WHERE f.league_key = %s AND f.season = %s AND f.status = 'ft' AND f.round <> 'Relegation Round'
 ORDER BY f.kickoff_at, f.fixture_id"""
TRAIN_SQL = "SELECT th.name_cn, ta.name_cn, r.ft_h, r.ft_a " + _SCOPE
TARGET_SQL = "SELECT f.fixture_id, th.name_cn, ta.name_cn " + _SCOPE
RUN_SQL = ("INSERT INTO model.pred_run (commit, params, n_fixtures, note)"
           " VALUES (%s, %s::jsonb, %s, %s) RETURNING run_id")
FIX_SQL = ("INSERT INTO model.pred_fixture (run_id, fixture_id, lambda_home, lambda_away, matrix, features)"
           " VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)")
MARKET_SQL = "INSERT INTO model.pred_market (run_id, fixture_id, play_type, option_code, p) VALUES (%s, %s, %s, %s, %s)"


def season_pairs(conn) -> list[tuple[str, int, int]]:
    """可预测组合 (联赛, 预测季, 训练季)；训练季 = 同联赛严格更早的最大赛季 ⇒ 2022 天生只当训练集。"""
    scored = conn.execute(SEASONS_SQL).fetchall()
    return [(lk, s, max(t for k, t in scored if k == lk and t < s))
            for lk, s in sorted(scored) if any(k == lk and t < s for k, t in scored)]


def run(conn, league_key: str, season: int, train_season: int | None = None) -> dict:
    """一个 (联赛, 预测季) = 一个 model.pred_run；泄漏防线在入口硬守卫，返回本 run 的真实计数。"""
    if train_season is None:
        train_season = next((t for lk, s, t in season_pairs(conn) if (lk, s) == (league_key, season)), season)
    if train_season >= season:
        raise ValueError(f"泄漏防线：{league_key} {train_season} 不是 {season} 的严格更早赛季（2022 只当训练集）")
    train = [(h, a, float(gh), float(ga)) for h, a, gh, ga in conn.execute(TRAIN_SQL, (league_key, train_season))]
    fit = fit_attack_defense(train)
    targets = conn.execute(TARGET_SQL, (league_key, season)).fetchall()
    predicted = [(f, (h, a), match_lambdas(fit, h, a)) for f, h, a in targets if h in fit.atk and a in fit.atk]
    skipped = len(targets) - len(predicted)
    params = {"train_season": train_season, "plays": list(PLAYS), "gamma": fit.gamma, "rho": DC_RHO,
              "max_goals": MAX_GOALS_MC, "skipped_unknown": skipped}
    note = f"{league_key} {season} 预测（训练季 {train_season}）；跳过 {skipped} 场：当季球队不在训练季"
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        commit = None
    run_id = conn.execute(RUN_SQL, (commit, json.dumps(params), len(predicted), note)).fetchone()[0]
    market = []
    for fixture_id, (home, away), (lambda_home, lambda_away) in predicted:
        grid = dc_grid(lambda_home, lambda_away, rho=DC_RHO, max_goals=MAX_GOALS_MC)
        features = {"atk_home": fit.atk[home], "def_away": fit.def_[away], "gamma": fit.gamma}
        conn.execute(FIX_SQL, (run_id, fixture_id, lambda_home, lambda_away, json.dumps(grid),
                               json.dumps(features)))
        for play in PLAYS:
            probs = derive_play(play, grid)
            probs = probs[0] if play == "jqc" else probs  # jqc=(主队档, 客队档)：只落主队侧（见 docstring）
            market += [(run_id, fixture_id, play, code, p) for code, p in probs.items()]
    conn.cursor().executemany(MARKET_SQL, market)
    logger.info(f"[walk] {league_key} {season} run_id={run_id} γ={fit.gamma:.6f} 写入 {len(predicted)} 跳过 {skipped}")
    return {"run_id": run_id, "n_fixtures": len(predicted), "n_market": len(market), "skipped": skipped,
            "gamma": fit.gamma, "train_season": train_season}


def main(argv: list[str] | None = None) -> int:
    """CLI：--league/--season 过滤；每个 (联赛, 预测季) 一个真事务（write_conn('app') 退出即提交）。"""
    ap = argparse.ArgumentParser(description="上一季拟合 → 当季预测：λ/9×9 矩阵/四玩法落 model.*")
    ap.add_argument("--league", help="只跑一个联赛（默认全部）")
    ap.add_argument("--season", type=int, help="只跑一个预测季（默认全部可预测季）")
    args = ap.parse_args(argv)
    with pg.read_conn("app") as conn:
        pairs = [p for p in season_pairs(conn) if args.league in (None, p[0]) and args.season in (None, p[1])]
    if not pairs:
        logger.error("没有可预测的 (联赛, 赛季)：需在库且存在更早赛季作训练集")
        return 1
    for league_key, season, _ in pairs:
        with pg.write_conn("app") as conn:  # 每个 run 一个事务：退出即提交，异常即回滚本 run
            run(conn, league_key, season)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
