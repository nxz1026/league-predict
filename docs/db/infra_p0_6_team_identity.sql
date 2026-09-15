-- ============================================================================
-- P0-TEAMKEY1（DDL 部分，队长执行）：俱乐部身份从"译文名"改成"源 id"
-- 起因（真跑 P0-MODEL1 才暴露，单测全绿看不见）：
--   ref.team 原唯一键 = UNIQUE(sport, name_cn)，而 name_cn = core.i18n.to_cn(源队名串)。
--   两件事叠加就出事：① API-Football **跨赛季会改队名拼写**（"Vfl Bochum"→"VfL Bochum"、"Bayern Munich"→"Bayern München"）；
--   ② to_cn 是**按字符串查词典**，换了串就可能翻不出来 ⇒ 保留英文原名。
--   ⇒ 同一家俱乐部（AF team id 完全相同）被插成两行：id 157 = {拜仁慕尼黑, Bayern München}、163 门兴、176 波鸿、180 海登海姆。
--   后果：按 (league, season) 拟合时"上一季没这支队"⇒ 德甲 2024 季 306 场只写出 132 场预测（跳过 57%）。
-- 本脚本三件事：合重复行（赢家=有中文名者，否则 team_id 小者）→ 加两列**存储生成列**（af_id/fd_id，下游 join 与索引都走它们）
--   → 建 partial unique **防复发**。⚠️ 索引一建，旧的"按名字 upsert"代码立刻会在改名时撞唯一键——这是**故意的**（响比不响好），
--      必须与代码单 P0-TEAMKEY1 同一轮交付（OMP-SKILL §9-27）。
-- 跑法：
--   install -m 0644 ~/league-v2/docs/db/infra_p0_6_team_identity.sql /tmp/
--   sudo -u postgres psql -d league -v ON_ERROR_STOP=1 -f /tmp/infra_p0_6_team_identity.sql
-- ============================================================================

BEGIN;

-- 0) 备份：合并前的原貌（可整表还原；只留 postgres 可读，league_app/ro/ing 都不给）
CREATE TABLE IF NOT EXISTS ref.team_pre_p0_6_backup (LIKE ref.team INCLUDING DEFAULTS);
INSERT INTO ref.team_pre_p0_6_backup SELECT * FROM ref.team
 WHERE NOT EXISTS (SELECT 1 FROM ref.team_pre_p0_6_backup b WHERE b.team_id = ref.team.team_id);
CREATE TABLE IF NOT EXISTS ref.team_merge_map (
    winner_id bigint NOT NULL, loser_id bigint NOT NULL, src_key text NOT NULL, src_id text NOT NULL, merged_at timestamptz NOT NULL DEFAULT now());

-- 1) 挑赢家：同一 AF id 的多行里，name_cn 含中日韩字形者优先（那是我们想要的展示名），否则取 team_id 最小
DROP TABLE IF EXISTS tmp_winner;
CREATE TEMP TABLE tmp_winner AS
SELECT g.src_key AS src_key, g.src_id AS src_id,
       COALESCE(
         (SELECT t.team_id FROM ref.team t
           WHERE t.aliases ->> g.src_id = g.src_id AND t.sport = g.sport AND t.name_cn ~ '[一-鿿]'
           ORDER BY t.team_id LIMIT 1),
         min(t.team_id))                                AS winner_id,
       array_agg(t.team_id ORDER BY t.team_id)          AS all_ids
  FROM (SELECT 'api_football' AS src_key, sport, aliases->>'api_football' AS src_id
          FROM ref.team WHERE aliases ? 'api_football' GROUP BY 1, 2, 3
         UNION ALL
        SELECT 'football_data', sport, aliases->>'football_data'
          FROM ref.team WHERE aliases ? 'football_data' GROUP BY 1, 2, 3) g
  JOIN ref.team t ON t.sport = g.sport AND t.aliases ->> g.src_key = g.src_id   -- ⚠️ 键名取 src_key、值比 src_id（写成 ->> g.src_id 会永远连不上）
 GROUP BY g.src_key, g.sport, g.src_id
HAVING count(*) > 1;

INSERT INTO ref.team_merge_map (winner_id, loser_id, src_key, src_id)
SELECT w.winner_id, x.id, w.src_key, w.src_id FROM tmp_winner w, unnest(w.all_ids) AS x(id)
 WHERE x.id <> w.winner_id;

-- 2) 把输家的 aliases 并进赢家（同键同值，赢家为准；输家独有的键补进来）
-- ⚠️ jsonb_object_agg 在**空集**上返回 NULL，`jsonb || NULL` 也是 NULL ⇒ 会把 aliases 整个洗成 null（我第一次跑就炸在这）
--    赢家已含输家全部键时子查询就是空集，所以 COALESCE 是必需的，不是装饰。
UPDATE ref.team t
   SET aliases = t.aliases || COALESCE((SELECT jsonb_object_agg(k, v)
                                 FROM ref.team l, jsonb_each_text(l.aliases) AS e(k, v)
                                WHERE l.team_id = m.loser_id
                                  AND NOT (t.aliases ? k)), '{}'::jsonb)
  FROM ref.team_merge_map m
 WHERE t.team_id = m.winner_id;

-- 3) 重指 fact.fixture 的两处外键（这是全库唯一引用 ref.team 的地方；fact.fixture_result 不含队列）
UPDATE fact.fixture f SET home_team_id = m.winner_id
  FROM ref.team_merge_map m WHERE f.home_team_id = m.loser_id;
UPDATE fact.fixture f SET away_team_id = m.winner_id
  FROM ref.team_merge_map m WHERE f.away_team_id = m.loser_id;

-- 4) 删输家（此刻应已无任何引用；用 NOT EXISTS 兜一层，防误删）
DELETE FROM ref.team t
 WHERE t.team_id IN (SELECT loser_id FROM ref.team_merge_map)
   AND NOT EXISTS (SELECT 1 FROM fact.fixture f WHERE f.home_team_id = t.team_id OR f.away_team_id = t.team_id);

COMMIT;

-- 5) 存储生成列：下游一律用 af_id / fd_id 认队，name_cn 退回"展示用"
ALTER TABLE ref.team ADD COLUMN IF NOT EXISTS af_id bigint GENERATED ALWAYS AS
  (CASE WHEN aliases ? 'api_football' AND (aliases->>'api_football') ~ '^[0-9]+$'
        THEN (aliases->>'api_football')::bigint END) STORED;
ALTER TABLE ref.team ADD COLUMN IF NOT EXISTS fd_id bigint GENERATED ALWAYS AS
  (CASE WHEN aliases ? 'football_data' AND (aliases->>'football_data') ~ '^[0-9]+$'
        THEN (aliases->>'football_data')::bigint END) STORED;
COMMENT ON COLUMN ref.team.af_id IS 'API-Football team id（**俱乐部身份的真正主键**）；从 aliases 生成，不手填。name_cn 只是展示名，源站改名不能产生新行';
COMMENT ON COLUMN ref.team.fd_id IS 'football-data team id，同上';

-- 6) 防复发：同一 sport 内，一个源 id 只能有一行（partial：没这个键的行不受约束）
CREATE UNIQUE INDEX IF NOT EXISTS team_af_key ON ref.team (sport, af_id) WHERE af_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS team_fd_key ON ref.team (sport, fd_id) WHERE fd_id IS NOT NULL;

-- 7) 验证
SELECT (SELECT count(*) FROM ref.team)                              AS team_rows,
       (SELECT count(*) FROM ref.team_pre_p0_6_backup)              AS backup_rows,
       (SELECT count(*) FROM ref.team_merge_map)                    AS merged_losers,
       (SELECT count(*) FROM (SELECT af_id FROM ref.team WHERE af_id IS NOT NULL GROUP BY 1 HAVING count(*)>1) d) AS af_dup_left,
       (SELECT count(*) FROM fact.fixture)                          AS fixtures,
       (SELECT count(*) FROM ref.team t WHERE NOT EXISTS
          (SELECT 1 FROM fact.fixture f WHERE f.home_team_id=t.team_id OR f.away_team_id=t.team_id)) AS orphan_teams;
SELECT src_id, winner_id, loser_id FROM ref.team_merge_map ORDER BY src_id::int;
-- 手工复验（必须全部符合预期）：
--   · 拜仁只剩一行且 af_id=157：select team_id,name_cn,aliases from ref.team where af_id=157;
--   · 旧代码路径撞键会响（模拟改名插入）：
--     insert into ref.team (sport,name_cn,aliases) values ('football','Bayern Munich Test',{"api_football":157}::jsonb); → 预期 unique 违反
