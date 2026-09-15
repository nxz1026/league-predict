-- ============================================================
-- P0-infra ①：角色 / 表空间 / 建库（对 postgres 库执行）
-- 定稿 2026-09-15（队长，NDORACLE 本机 PG 18.6）
-- 范围红线（OMP-SKILL §6）：只到 ref/stg/ops；fact/model/analysis 与 v.market_full
--   等国内机 JSONL 契约冻结（schema v1.1 正式版）后再建。
-- 与 docs/db/schema_v2_draft.sql 的差异（全部为落地必要）：
--   A 口令不写字面量：由 psql -v ing_pw/app_pw/ro_pw 注入（草案里是 '***' 占位）
--   B 表空间路径改 Ubuntu 布局：草案写的 /var/lib/pgsql/18/... 是 RHEL 路径，本机 PGDATA=/var/lib/postgresql/18/main
--   C 三角色加 CONNECTION LIMIT，防 ingest 泄漏打满 max_connections
--   D 草案未写 CONNECT 授权细节：这里显式 REVOKE PUBLIC + 只授三角色
-- ============================================================
\set ON_ERROR_STOP on

CREATE ROLE league_ing LOGIN PASSWORD :'ing_pw' VALID UNTIL '2027-06-30' CONNECTION LIMIT 5;
CREATE ROLE league_app LOGIN PASSWORD :'app_pw' VALID UNTIL '2027-06-30' CONNECTION LIMIT 20;
CREATE ROLE league_ro  LOGIN PASSWORD :'ro_pw'  VALID UNTIL '2027-06-30' CONNECTION LIMIT 3;

-- 表空间：单盘无性能收益，价值在未来挪盘/备份粒度（草案 §表空间原意）。
-- ts_snap 先建不先用（fact.line_snapshot 分区表落地时启用），避免届时全表 ALTER。
CREATE TABLESPACE ts_snap LOCATION '/var/lib/postgresql/18/tablespaces/ts_snap';
CREATE TABLESPACE ts_stg  LOCATION '/var/lib/postgresql/18/tablespaces/ts_stg';

CREATE DATABASE league OWNER league_app ENCODING 'UTF8' TEMPLATE template0;

REVOKE ALL ON DATABASE league FROM PUBLIC;
GRANT CONNECT ON DATABASE league TO league_ing, league_app, league_ro;
