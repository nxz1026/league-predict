-- ============================================================================
-- P0-TEAMKEY1 的收尾（队长执行，纯 SQL，幂等）：把 FD 队 id 从"孤儿行"搬到证据所属的 AF 行
-- 背景：P0-TEAMKEY1 已把身份键改成源 id（af_id/fd_id + partial unique）。coder 复跑真库时发现还有 38 个 FD 队 id
--   被"只有 fd_id、没有 af_id、且 fact 从不引用"的孤儿行占着（它们是 FACT1 时代 FD 直接插 fixture 留下的残迹）。
--   于是 upsert_fixtures 的 FD 侧只能 warn 并如实报数（stats.fd_id_taken，实测 2116 次（场,队）事件被挡），
--   既不放宽索引也不造新行 —— 处置正确，但**去重本身属数据侧，归队长**（见其报告 §8）。
-- 证据（不靠队名猜）：fact.fixture.source_ids->>'football_data' ＝ 两源同一场的锚点（FACT2/FACT3 已核对，99.3% 对齐、
--   方向经 home_away_swapped 判据保证）；raw.fd_raw 的 match 里给出该场的 FD home/away team id；
--   该 fixture 的 home_team_id/away_team_id 就是 AF 行。⇒ 每个 FD 队 id 应当挂在哪个 AF 行，是**算出来的**。
-- 实测（队长 /tmp/fdmerge_evidence.py）：证据覆盖 110 个 FD 队 id，其中 72 个已正确挂在目标行；
--   38 个"占用冲突"= 孤儿行持有；一 id 指多行的冲突 **0 个** ⇒ 可安全搬。
-- 跑法：install -m 0644 ~/league-v2/docs/db/infra_p0_7_fd_id_move.sql /tmp/
--       sudo -u postgres psql -d league -v ON_ERROR_STOP=1 -f /tmp/infra_p0_7_fd_id_move.sql
-- ============================================================================

BEGIN;

-- 1) 证据表：fd_team_id → 应归属的 af_team_id（两侧各一条，取每侧的证据集合）
DROP TABLE IF EXISTS tmp_fd_ev;
CREATE TEMP TABLE tmp_fd_ev AS
WITH m AS (
    SELECT (r.body -> 'matches') AS arr FROM raw.fd_raw r WHERE r.http_status = 200
), e AS (
    SELECT (x -> 'homeTeam' ->> 'id')::bigint AS fd_team, f.home_team_id AS af_team
      FROM m, jsonb_array_elements(m.arr) x
      JOIN fact.fixture f ON f.source_ids ->> 'football_data' = x ->> 'id'
     UNION ALL
    SELECT (x -> 'awayTeam' ->> 'id')::bigint, f.away_team_id
      FROM m, jsonb_array_elements(m.arr) x
      JOIN fact.fixture f ON f.source_ids ->> 'football_data' = x ->> 'id'
)
SELECT fd_team, count(DISTINCT af_team) AS n_target, min(af_team) AS af_team
  FROM e WHERE fd_team IS NOT NULL AND af_team IS NOT NULL GROUP BY fd_team;

-- 2) 硬闸：一个 FD id 只能指向一个 AF 行，否则整脚本中止（宁可不搬）
DO $$
DECLARE bad int;
BEGIN
    SELECT count(*) INTO bad FROM tmp_fd_ev WHERE n_target > 1;   -- 列名是 fd_team/n_target/af_team
    IF bad > 0 THEN
        RAISE EXCEPTION '证据不一致：有 % 个 FD 队 id 指向多个 AF 行，拒绝合并', bad;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS ref.team_fd_move_map (
    fd_id bigint PRIMARY KEY, holder_row bigint, target_row bigint, target_name_cn text, made_at timestamptz NOT NULL DEFAULT now());

-- 3) 待办 = 证据指向目标行，且当前 fd_id 被"无 af_id、无引用"的孤儿行占着
DROP TABLE IF EXISTS tmp_fd_move;
CREATE TEMP TABLE tmp_fd_move AS
SELECT ev.fd_team AS fd_id, h.team_id AS holder_row, ev.af_team AS target_row, h.name_cn AS holder_name, t.name_cn AS target_name  -- ⚠️ holder 只能取 h（持 fd_id 的孤儿）：t 是被引用的目标行，写反了就会删到被 fact 引用的行（我第一版就踩了，FK 救场）
  FROM tmp_fd_ev ev
  JOIN ref.team h        ON h.fd_id = ev.fd_team                 -- 当前持有者
  JOIN ref.team t        ON t.team_id = ev.af_team             -- 证据所属的 AF 行
 WHERE h.af_id IS NULL                                          -- 孤儿：只有 FD 身份
   AND t.team_id <> h.team_id
   AND t.fd_id IS NULL                                          -- 目标行还没有 fd_id（有且相同则无需动）
   AND NOT EXISTS (SELECT 1 FROM fact.fixture f
                    WHERE f.home_team_id = h.team_id OR f.away_team_id = h.team_id);

INSERT INTO ref.team_fd_move_map (fd_id, holder_row, target_row, target_name_cn)
SELECT fd_id, holder_row, target_row, target_name FROM tmp_fd_move ON CONFLICT (fd_id) DO NOTHING;

-- 3b) 人读一遍：搬的是哪 38 家（holder=FD 孤儿行名 / target=AF 行名，应为同一俱乐部）
SELECT fd_id, holder_row, holder_name, target_row, target_name FROM tmp_fd_move ORDER BY holder_name LIMIT 40;

-- 4) 先删孤儿（释放 team_fd_key），再把 id 并进目标行 —— 顺序反了会撞 partial unique
DELETE FROM ref.team t WHERE t.team_id IN (SELECT holder_row FROM tmp_fd_move);
UPDATE ref.team t SET aliases = t.aliases || jsonb_build_object('football_data', m.fd_id)
  FROM ref.team_fd_move_map m WHERE t.team_id = m.target_row AND t.fd_id IS DISTINCT FROM m.fd_id;

COMMIT;

-- 5) 验证（全部应为预期值）
SELECT (SELECT count(*) FROM ref.team)                                    AS team_rows,      -- 预期 160-38 = 122
       (SELECT count(*) FROM ref.team WHERE af_id IS NOT NULL)            AS with_af,        -- 预期 122（行行有 AF 身份）
       (SELECT count(*) FROM ref.team WHERE fd_id IS NOT NULL)            AS with_fd,        -- 预期 110 不变（只是换了行持有）
       (SELECT count(*) FROM ref.team WHERE fd_id IS NOT NULL AND af_id IS NULL) AS fd_only, -- 预期 0
       (SELECT count(*) FROM (SELECT fd_id FROM ref.team WHERE fd_id IS NOT NULL GROUP BY 1 HAVING count(*)>1) d) AS dup_fd, -- 0
       (SELECT count(*) FROM (SELECT af_id FROM ref.team WHERE af_id IS NOT NULL GROUP BY 1 HAVING count(*)>1) d) AS dup_af, -- 0
       (SELECT count(*) FROM ref.team t WHERE NOT EXISTS (SELECT 1 FROM fact.fixture f
          WHERE f.home_team_id=t.team_id OR f.away_team_id=t.team_id))    AS orphans,        -- 预期 0
       (SELECT count(*) FROM fact.fixture)                                AS fixtures,       -- 5341 不变
       (SELECT count(*) FROM ref.team_fd_move_map)                        AS moved;          -- 38
SELECT indexname FROM pg_indexes WHERE tablename='team' AND schemaname='ref' ORDER BY 1;

-- 手工复验（搬完必须全部成立）：
--   · Burnley：select team_id,name_cn,af_id,fd_id from ref.team where fd_id=328;   → 应是 AF 行 817，且 af_id 非空
--   · 再跑一次本脚本：应 0 行待办、team_rows 不变（幂等）
--   · 重跑 upsert_fixtures（回滚事务里）：ops.ingest_log / logger 里 fd_id_taken 应归 0
