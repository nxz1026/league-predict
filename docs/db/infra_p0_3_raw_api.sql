-- ============================================================================
-- P0-infra 追加：API 原始响应落地块 raw.af_raw / raw.fd_raw
-- 目的：把"P0-backfill 2022-2024 慢回填（API-Football 免费档 100 req/天，要跑 2-3 周）"与
--       "国内机 JSONL 契约冻结"解耦——回填先落原始块（不解析），fact.* 等契约冻结后一次性长出来。
--
-- 【为什么是独立 schema `raw`，不塞进 stg】（2026-09-15 实测踩出来的）
--   `tests/test_collector_contract.py` 断言 **stg 表集合必须恰等于国内机七 topic 契约**
--   （sorted(tables) == 七表；这条断言是契约守卫，不是障碍）。第一版把 af_raw/fd_raw 建在 stg 里
--   → 该用例立刻红：**测试没错，是我建错了地方**。语义上这两块也不是"采集机装载区"：
--   没有 line/src_hash 的 JSONL 契约、不可重放、生命周期完全不同 ⇒ 独立 schema。
--   附带好处：躲开 p0_2 里 `ALTER DEFAULT PRIVILEGES IN SCHEMA stg GRANT … TRUNCATE TO league_ing`
--   的继承陷阱（放 stg 会自动继承 TRUNCATE，还得额外 REVOKE）。
--
-- 【三条硬规矩】
--   1. **必须 LOGGED**（relpersistence='p'）：stg 那 7 张是 UNLOGGED（重启清空），免费配额换来的响应不可重放。
--   2. **league_ing 只给 INSERT + SELECT**：不给 UPDATE/DELETE/TRUNCATE（raw 的唯一写路径就是追加；
--      `raw` 的默认权限里**不含 TRUNCATE**，别照抄 stg 那段）。
--   3. 幂等键 `params_hash UNIQUE` = sha256(endpoint + 规范化参数串)；quota_ledger 之外再加一层"同请求不重跑"。
--
-- 跑法（幂等可重跑；两条实测坑都写在这）：
--   install -m 0644 ~/league-v2/docs/db/infra_p0_3_raw_api.sql /tmp/
--   sudo -u postgres psql -d league -v ON_ERROR_STOP=1 -f /tmp/infra_p0_3_raw_api.sql
--   · /home/ubuntu 是 0750，postgres OS 用户进不来 → `-f ~/…` 直接 Permission denied（`-f /dev/stdin` 也不行）
--   · 别把 psql 接 `| head`（SIGPIPE 会中途截断而 rc 仍是 0，见 OMP-SKILL §9-12）
-- ============================================================================

-- 0) 清理第一版误建在 stg 的同名块（空表，无数据风险；不存在则跳过） ----------------
DROP TABLE IF EXISTS stg.af_raw;
DROP TABLE IF EXISTS stg.fd_raw;

-- 1) schema + 默认权限（顺序铁律：默认权限必须**先于**建表，见 §9-13） ----------------
CREATE SCHEMA IF NOT EXISTS raw AUTHORIZATION postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO league_app, league_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT INSERT, SELECT ON TABLES TO league_ing;
GRANT USAGE ON SCHEMA raw TO league_ing, league_app, league_ro;

-- 2) 表（LOGGED；表空间仍用 ts_stg 以复用既有磁盘布局） ----------------------------
CREATE TABLE IF NOT EXISTS raw.af_raw (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    endpoint     text        NOT NULL,
    params       jsonb       NOT NULL,
    params_hash  text        NOT NULL,            -- 唯一性只作用于**成功块**，见下方 partial unique（429/5xx 不许挡住重试）
    http_status  int         NOT NULL,
    quota_cost   int         NOT NULL DEFAULT 1,
    body         jsonb       NOT NULL,
    captured_at  timestamptz NOT NULL DEFAULT now(),
    src_host     text        NOT NULL DEFAULT current_user
) USING heap TABLESPACE ts_stg;
COMMENT ON TABLE  raw.af_raw IS 'API-Football 原始响应落地块（LOGGED：免费档配额不可重放）；解析归 fact 层工单';
COMMENT ON COLUMN raw.af_raw.params_hash IS 'sha256(endpoint + 规范化参数串)：幂等键，同请求重跑不重复扣配额';
COMMENT ON COLUMN raw.af_raw.body IS '原始 response 整块（jsonb），不做加工；字段解释延后到 fact 层';
CREATE INDEX IF NOT EXISTS af_raw_endpoint_time_idx ON raw.af_raw (endpoint, captured_at) TABLESPACE ts_stg;
-- 幂等键的**部分唯一索引**：只有 http_status=200 的块占坑。
-- 为什么不用表级 UNIQUE(params_hash)（实测教训，2026-09-15）：免费档 AF 还有一条 **10 req/分钟** 限制，
-- 连发 15 条从第 11 条起全 429；"失败也落块"是对的（留证），但失败块若也占唯一键，
-- 这 5 个 league-season 就**永久取不到了**（重跑命中缓存直接跳过）。⇒ 失败块可重复追加，成功块唯一。
CREATE UNIQUE INDEX IF NOT EXISTS af_raw_hash_ok ON raw.af_raw (params_hash) WHERE http_status = 200;

-- LIKE … INCLUDING ALL 会连 af_raw 的 partial unique 一起复制（含索引定义），故 fd_raw 不再单独建 hash_ok
CREATE TABLE IF NOT EXISTS raw.fd_raw (LIKE raw.af_raw INCLUDING ALL) TABLESPACE ts_stg;
COMMENT ON TABLE  raw.fd_raw IS 'football-data.org v4 原始响应落地块（LOGGED）；结构 = raw.af_raw，解析归 fact 层工单';
COMMENT ON COLUMN raw.fd_raw.params_hash IS 'sha256(endpoint + 规范化参数串)：幂等键';
COMMENT ON COLUMN raw.fd_raw.body IS '原始 response 整块（jsonb）';
CREATE INDEX IF NOT EXISTS fd_raw_endpoint_time_idx ON raw.fd_raw (endpoint, captured_at) TABLESPACE ts_stg;

-- 存量迁移（第一版建的表级 UNIQUE 必须让位给 partial unique；DO 块保证幂等可重跑）
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname IN ('af_raw_params_hash_key','fd_raw_params_hash_key')
                                     AND connamespace = 'raw'::regnamespace) THEN
        ALTER TABLE raw.af_raw DROP CONSTRAINT IF EXISTS af_raw_params_hash_key;
        ALTER TABLE raw.fd_raw DROP CONSTRAINT IF EXISTS fd_raw_params_hash_key;
        RAISE NOTICE '已把 raw 两块的表级 UNIQUE(params_hash) 换成 partial unique (http_status=200)';
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS fd_raw_hash_ok ON raw.fd_raw (params_hash) WHERE http_status = 200;

-- 3) 存量补授（幂等，可重跑） --------------------------------------------------------
GRANT USAGE ON SCHEMA raw TO league_ing, league_app, league_ro;
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA raw TO league_ing;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO league_app, league_ro;

-- 4) 验证 ---------------------------------------------------------------------------
SELECT t.tabname, c.relpersistence::text AS should_be_p,
       COALESCE((SELECT string_agg(g.grantee || '=' || g.privs, ' | ')
                   FROM (SELECT grantee, string_agg(privilege_type, '/' ORDER BY privilege_type) AS privs
                           FROM information_schema.role_table_grants
                          WHERE table_schema = 'raw' AND table_name = t.tabname
                            AND grantee LIKE 'league\_%'
                          GROUP BY grantee) g), '(仅 owner)') AS grants
  FROM (VALUES ('af_raw'), ('fd_raw')) AS t(tabname)
  LEFT JOIN pg_class c ON c.relname = t.tabname
  LEFT JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'raw'
 ORDER BY t.tabname;
-- 脚本外必查两项：① league_ing 对 raw 表 TRUNCATE/UPDATE/DELETE 必须 permission denied；
--                 ② pytest tests/test_collector_contract.py -q 必须绿（stg 七表契约未被本追加破坏）。
