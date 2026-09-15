-- ============================================================================
-- P0-infra 追加：fact 层"国际源两张表"（fixture + fixture_result）+ ref.league seed
-- 为什么只建这两张：它们的数据形态由 **AF/FD 实测报文**决定（队长 2026-09-15 已核：
--   `/fixtures?league=39&season=2024` → 380 场、`score.halftime` 380/380 非空），
--   与"国内机 JSONL 契约"无关；而 fact.jc_offer / fact.jc_result / fact.lottery_draw
--   的字段要等国内机 probe 回传冻结契约 v1.1 才能定 ⇒ 那三张继续不建（契约守卫见
--   tests/test_collector_contract.py，它只钉 stg 七表）。
-- 表空间：本阶段数据量 ~4.5k 场 ⇒ 用 pg_default（ts_snap 留给 fact.line_snapshot 的海量快照）。
-- 跑法（同 p0_3，两条实测坑）：
--   install -m 0644 ~/league-v2/docs/db/infra_p0_4_fact_core.sql /tmp/
--   sudo -u postgres psql -d league -v ON_ERROR_STOP=1 -f /tmp/infra_p0_4_fact_core.sql
-- ============================================================================

-- 0) schema（若已存在跳过）+ 默认权限必须在建表之前 --------------------------------
CREATE SCHEMA IF NOT EXISTS fact AUTHORIZATION postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA fact GRANT SELECT ON TABLES TO league_app, league_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA fact GRANT SELECT, INSERT, UPDATE ON TABLES TO league_ing;
GRANT USAGE ON SCHEMA fact TO league_ing, league_app, league_ro;

-- 1) fact.fixture：一场比赛的不变事实（id 以 API-Football fixture.id 为权威） -------
CREATE TABLE IF NOT EXISTS fact.fixture (
    fixture_id    bigint        PRIMARY KEY,          -- = AF fixture.id（权威）；FD 的 id 进 source_ids
    league_key    text          NOT NULL REFERENCES ref.league(league_key),
    season        int           NOT NULL,             -- 欧洲赛季用起始年（2024-25 季 = 2024）
    round         text,                               -- AF league.round，如 "Regular Season - 1"
    kickoff_at    timestamptz   NOT NULL,
    home_team_id  bigint        REFERENCES ref.team(team_id),
    away_team_id  bigint        REFERENCES ref.team(team_id),
    status        text          NOT NULL DEFAULT 'scheduled'
                  CHECK (status IN ('scheduled','pending','timed','postponed','canceled',
                                    'interrupted','abandoned','exended','defaulted',
                                    'ft','aet','pen','unknown')),
    venue         text,
    source_ids    jsonb         NOT NULL DEFAULT '{}'::jsonb,   -- {"api_football":1208021,"football_data":419123}
    jc            boolean       NOT NULL DEFAULT false,         -- 竞彩是否开售（国内机到货后才置真）
    updated_at    timestamptz   NOT NULL DEFAULT now()
);
COMMENT ON TABLE fact.fixture IS '比赛不变事实（国际源）。多源 id 全进 source_ids，冲突不改主键口径';
CREATE INDEX IF NOT EXISTS fixture_kickoff_idx  ON fact.fixture (kickoff_at);
CREATE INDEX IF NOT EXISTS fixture_league_season_idx ON fact.fixture (league_key, season);
CREATE INDEX IF NOT EXISTS fixture_home_idx     ON fact.fixture (home_team_id);
CREATE INDEX IF NOT EXISTS fixture_away_idx     ON fact.fixture (away_team_id);

-- 2) fact.fixture_result：赛果**多源并存**（每源一行，不互相覆盖） ------------------
CREATE TABLE IF NOT EXISTS fact.fixture_result (
    fixture_id   bigint       NOT NULL REFERENCES fact.fixture(fixture_id),
    source       text         NOT NULL,               -- 'api_football' | 'football_data' | 以后 'sporttery'
    ft_h         smallint,
    ft_a         smallint,
    ht_h         smallint,                            -- P1 半全场模型的数据前提，可空（未回填时）
    ht_a         smallint,
    elapsed_ht   int,                                 -- AF fixture.periods.first / elapsed 辅助核验
    status       text,
    confirmed_at timestamptz,
    raw          jsonb        NOT NULL DEFAULT '{}'::jsonb,   -- 该场原始节点（解析出错时不必回头再请求）
    PRIMARY KEY (fixture_id, source)
);
COMMENT ON TABLE fact.fixture_result IS '赛果多源并存：同一场每源一行，PK(fixture_id,source)；分歧由视图暴露，装载侧不做"谁覆盖谁"';
CREATE INDEX IF NOT EXISTS fixture_result_source_idx ON fact.fixture_result (source);

-- 3) 分歧暴露视图（"ingest 冲突即报警"的落点；只读，装载账号不碰） ------------------
CREATE OR REPLACE VIEW fact.v_result_conflict AS
SELECT fixture_id,
       count(*)                                   AS n_sources,
       bool_or(ft_is_null)                        AS all_ft_null,
       (count(DISTINCT ft_pair) <> 1)             AS ft_differs,
       (count(DISTINCT ht_pair) FILTER (WHERE ht_pair IS NOT NULL) > 1) AS ht_differs,
       jsonb_object_agg(source, jsonb_build_object('ft', ft_pair, 'ht', ht_pair)) AS per_source
  FROM (SELECT fixture_id, source,
                CASE WHEN ft_h IS NULL AND ft_a IS NULL THEN NULL
                     ELSE ft_h || ':' || ft_a END AS ft_pair,
                CASE WHEN ft_h IS NULL AND ft_a IS NULL THEN TRUE ELSE FALSE END AS ft_is_null,
                CASE WHEN ht_h IS NULL AND ht_a IS NULL THEN NULL
                     ELSE ht_h || ':' || ht_a END AS ht_pair
          FROM fact.fixture_result) s
 GROUP BY fixture_id
HAVING (count(*) > 1 AND count(DISTINCT ft_pair) <> 1)
    OR (count(DISTINCT ht_pair) FILTER (WHERE ht_pair IS NOT NULL) > 1);
COMMENT ON VIEW fact.v_result_conflict IS '两源 FT/HT 不一致的场次（回填后第一件要看的事）';

-- 4) ref.league seed：五联赛 + 两源 id（队长实测值，非猜测） -----------------------
-- AF: /fixtures?league= 用 id；FD: /v4/competitions/{CODE}/matches 用 code（v4 口径）
-- 注意 ref.league.scope 有 CHECK：只允许 'regular' / 'irregular'（语义 = **竞彩开售范围**：
-- 固定开售联赛 vs 临时开售杯赛，见草案 §ref.league 与 P3"开关制赛事窗口"），不是"联赛/杯赛"分类。
-- 五大战联赛 = 固定开售 ⇒ scope='regular'；开售窗口 window_from/window_to 留给 P3 填。
INSERT INTO ref.league (league_key, cn_name, sport, scope, window_from, window_to, ids) VALUES
    ('epl',        '英超', 'football', 'regular', NULL, NULL, '{"api_football":39,  "football_data":"PL"}'),
    ('laliga',     '西甲', 'football', 'regular', NULL, NULL, '{"api_football":140, "football_data":"PD"}'),
    ('bundesliga', '德甲', 'football', 'regular', NULL, NULL, '{"api_football":78,  "football_data":"BL1"}'),
    ('seriea',     '意甲', 'football', 'regular', NULL, NULL, '{"api_football":135, "football_data":"SA"}'),
    ('ligue1',     '法甲', 'football', 'regular', NULL, NULL, '{"api_football":61,  "football_data":"FL1"}')
ON CONFLICT (league_key) DO UPDATE
   SET cn_name = EXCLUDED.cn_name, sport = EXCLUDED.sport, scope = EXCLUDED.scope,
       ids = ref.league.ids || EXCLUDED.ids, updated_at = now();

-- 5) 存量补授（幂等） --------------------------------------------------------------
GRANT SELECT ON ALL TABLES IN SCHEMA fact TO league_app, league_ro;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA fact TO league_ing;

-- 6) 验证 ---------------------------------------------------------------------------
SELECT table_schema||'.'||table_name AS obj, table_type,
       (SELECT string_agg(privilege_type, '/' ORDER BY privilege_type)
          FROM information_schema.role_table_grants
         WHERE table_schema=f.table_schema AND table_name=f.table_name AND grantee='league_ing') AS to_ing,
       (SELECT string_agg(privilege_type, '/' ORDER BY privilege_type)
          FROM information_schema.role_table_grants
         WHERE table_schema=f.table_schema AND table_name=f.table_name AND grantee='league_app')  AS to_app
  FROM information_schema.tables f
 WHERE table_schema='fact' ORDER BY 1;
SELECT league_key, ids FROM ref.league ORDER BY 1;
