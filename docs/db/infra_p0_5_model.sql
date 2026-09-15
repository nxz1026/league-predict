-- ============================================================================
-- P0-infra 追加：派生层 model.* + 评估层 analysis.*（预测与回测的落库面）
-- 与前面几块最大的区别 = **权限取向相反**：
--   · ref/stg/raw/fact 是"源数据"，league_ing 只能追加（无 UPDATE/DELETE/TRUNCATE），插错就只能超级用户洗；
--   · model/analysis 是**可重算的派生物**，给 league_app（模型进程）**INSERT + UPDATE + DELETE 全套**：
--     一次 run 要能整批重跑、清理旧 run、回填 clv；派生层被删不是事故，重算即可。
--   ⇒ 这条分界以后建任何新表都要先问一句："删了能不能重算出来？" 能 → 学 model；不能 → 学 raw。
-- 表空间：model.pred_fixture/pred_market 每场都存 9×9 矩阵（jsonb，几 KB/行），是这里唯一会长的 ⇒ ts_snap。
-- 跑法：
--   install -m 0644 ~/league-v2/docs/db/infra_p0_5_model.sql /tmp/
--   sudo -u postgres psql -d league -v ON_ERROR_STOP=1 -f /tmp/infra_p0_5_model.sql
-- ============================================================================

-- 0) schema + 默认权限（必须先于建表，见 OMP-SKILL §9-13） ------------------------
CREATE SCHEMA IF NOT EXISTS model     AUTHORIZATION postgres;
CREATE SCHEMA IF NOT EXISTS analysis  AUTHORIZATION postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA model    GRANT SELECT ON TABLES TO league_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA model    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO league_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA analysis GRANT SELECT ON TABLES TO league_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA analysis GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO league_app;
-- ⚠️ **序列是独立对象，表权限不覆盖它**（实测踩到）：`bigserial`/`serial` 列的 nextval 需要
--    `USAGE`（或 `UPDATE`）**on the sequence**，只给表 INSERT 照样 42501。`GENERATED ... AS IDENTITY` 不受此影响
--    （身份序列由列拥有、随表授权）⇒ 本层新表一律用 identity，另把序列权限一并授全（防以后有人图省事写 serial）。
ALTER DEFAULT PRIVILEGES IN SCHEMA model    GRANT USAGE, SELECT ON SEQUENCES TO league_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA analysis GRANT USAGE, SELECT ON SEQUENCES TO league_app;
GRANT USAGE ON SCHEMA model    TO league_app, league_ro;
GRANT USAGE ON SCHEMA analysis TO league_app, league_ro;
-- ⚠️ league_ing **不进** model/analysis：装载进程不许写预测结果（防止两条写路径打架）
--    fact/stg/raw 的 SELECT 它已有，读事实够用了。

-- 1) 一次预测运行 ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model.pred_run (
    run_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_at     timestamptz NOT NULL DEFAULT now(),
    commit     text,                                  -- 代码 git rev（跑的是什么版本的模型）
    params     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    n_fixtures int         NOT NULL DEFAULT 0,
    note       text
);
COMMENT ON TABLE model.pred_run IS '一次模型运行（λ + 矩阵 + 派生概率的批次头）；重跑＝新 run_id，旧 run 由 app 自行 DELETE 清理';
COMMENT ON COLUMN model.pred_run.params IS '训练/推断超参留痕（rho 口径、MAX_GOALS_MC、窗口长度等），复盘必需';

-- 2) 每场的底座矩阵（λ 与 9×9 联合分布） -----------------------------------------
CREATE TABLE IF NOT EXISTS model.pred_fixture (
    run_id       bigint  NOT NULL REFERENCES model.pred_run(run_id) ON DELETE CASCADE,
    fixture_id   bigint  NOT NULL REFERENCES fact.fixture(fixture_id),
    lambda_home  numeric NOT NULL CHECK (lambda_home > 0),
    lambda_away  numeric NOT NULL CHECK (lambda_away > 0),
    matrix       jsonb   NOT NULL,                    -- 8×8/9×9 联合矩阵（derive 层的输入，不是输出）
    elo          jsonb,
    features     jsonb,
    PRIMARY KEY (run_id, fixture_id)
) TABLESPACE ts_snap;
COMMENT ON COLUMN model.pred_fixture.matrix IS '未归一/已归一皆可，但 derive.grid.dc_grid 期望与 _dc_pmf_grid 同口径；重算即可复现 ⇒ 存原始 9×9';

-- 3) 派生层输出：每玩法每选项概率（与 fact.jc_offer 同构，可直接 JOIN 对照） -------
CREATE TABLE IF NOT EXISTS model.pred_market (
    run_id      bigint NOT NULL REFERENCES model.pred_run(run_id) ON DELETE CASCADE,
    fixture_id  bigint NOT NULL REFERENCES fact.fixture(fixture_id),
    play_type   text   NOT NULL,                      -- had/hhad/crs/ttg/jqc（haf 未注册 ⇒ 不会出现）
    option_code text NOT NULL,                       -- 'home'/'0:1'/'7+'/'-1away'…derive.registry 产出的键
    p           numeric NOT NULL CHECK (p >= 0 AND p <= 1),
    p_ai_ref    numeric,                             -- AI 参考值：只展示，**绝不进 EV**
    PRIMARY KEY (run_id, fixture_id, play_type, option_code)
) TABLESPACE ts_snap;
COMMENT ON TABLE model.pred_market IS 'derive_registry 的落库面；p_ai_ref 与 p 严格分离，UI 展示带 ai_ref 标记';

-- 4) 回测明细（逐玩法逐选项的命中与 CLV） ----------------------------------------
CREATE TABLE IF NOT EXISTS analysis.backtest_market (
    fixture_id  bigint   NOT NULL REFERENCES fact.fixture(fixture_id),
    play_type   text     NOT NULL,
    option_code text     NOT NULL,
    p_pred      numeric  NOT NULL,
    outcome     smallint NOT NULL CHECK (outcome IN (0, 1)),   -- 该选项是否命中（由 fact.fixture_result 判）
    clv         numeric,                               -- ln(p_pred / p_close)，无收盘则为 NULL（不许造 0）
    src_run     bigint   NOT NULL,
    PRIMARY KEY (fixture_id, play_type, option_code, src_run)
);
COMMENT ON TABLE analysis.backtest_market IS '回测逐行明细；CLV 是价值验证核心指标，NULL＝无收盘数据 ≠ 0';

-- 5) 串关 EV 报告（无票单 UI，纯报告；legs 里带每腿 SP/p/EV） ---------------------
CREATE TABLE IF NOT EXISTS analysis.ev_report (
    report_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    made_at    timestamptz NOT NULL DEFAULT now(),
    legs       jsonb       NOT NULL,
    p_parlay   numeric,
    ev         numeric,
    kelly      numeric,
    corr_adj   numeric,                                -- 同场相关性折减（设计 §EV 段）
    note       text
);

-- 6) 只读辅助视图 ----------------------------------------------------------------
CREATE OR REPLACE VIEW model.v_run_summary AS
SELECT r.run_id, r.run_at, r.commit, r.n_fixtures, r.note,
       (SELECT count(*) FROM model.pred_fixture f WHERE f.run_id = r.run_id)  AS n_fixture,
       (SELECT count(*) FROM model.pred_market m WHERE m.run_id = r.run_id)   AS n_market,
       (SELECT count(*) FROM model.pred_market m WHERE m.run_id = r.run_id
          AND m.play_type = 'haf')                                            AS n_haf_illegal,
       (SELECT jsonb_object_agg(x.play_type, x.cnt)
          FROM (SELECT m.play_type, count(*) AS cnt FROM model.pred_market m
                 WHERE m.run_id = r.run_id GROUP BY 1) x)                     AS by_play
  FROM model.pred_run r;
COMMENT ON VIEW model.v_run_summary IS '每个 run 的规模与分玩法条数（n_haf_illegal 必须恒为 0：haf 未注册，出现即派生层被绕过）';

-- 6b) 把历史遗留的 bigserial 改造成 identity（表空才能安全改；DO 块保证幂等） ----------
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema='analysis' AND table_name='ev_report' AND column_name='report_id'
                  AND column_default LIKE 'nextval%') THEN
        ALTER TABLE analysis.ev_report ALTER COLUMN report_id DROP DEFAULT;
        ALTER TABLE analysis.ev_report ALTER COLUMN report_id ADD GENERATED ALWAYS AS IDENTITY;
        RAISE NOTICE 'analysis.ev_report.report_id 已从 bigserial 改为 IDENTITY';
    END IF;
END $$;

-- 7) 存量补授（幂等） -------------------------------------------------------------
GRANT USAGE ON SCHEMA model    TO league_app, league_ro;
GRANT USAGE ON SCHEMA analysis TO league_app, league_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA model    TO league_app;
GRANT SELECT ON ALL TABLES IN SCHEMA model    TO league_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analysis TO league_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA model    TO league_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analysis TO league_app;
GRANT SELECT ON ALL TABLES IN SCHEMA analysis TO league_ro;

-- 8) 验证：对象清单 + 三向权限矩阵 -------------------------------------------------
SELECT n.nspname AS schema, c.relname AS obj, c.relkind AS kind, c.relpersistence::text AS "persistence",
       pg_tablespace.spcname AS ts
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_tablespace ON pg_tablespace.oid = c.reltablespace
 WHERE n.nspname IN ('model','analysis') AND c.relname NOT LIKE 'pg_%'
 ORDER BY 1, 2;
-- 矩阵（脚本外手工复跑，全部必须符合预期）：
--   league_app  : model/analysis 表 INSERT/UPDATE/DELETE/SELECT 全允许
--   league_ro   : 只 SELECT（写必须 InsufficientPrivilege）
--   league_ing  : 连 SELECT 都不该有（它不参与预测链路；Usage 都没授 ⇒ Relation not exist 级拒绝）
--   任何角色对 model/analysis 均无 TRUNCATE（DELETE 够用，TRUNCATE 会连带清掉别人正在跑的 run）
