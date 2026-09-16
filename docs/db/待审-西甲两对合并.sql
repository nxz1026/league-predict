-- ============================================================================
-- 待审：西甲两对重复行合并（竞彩侧 sporttery 键并入 AF 侧行）
-- ============================================================================
-- ⚠️ 本文件**不自动执行**，等人工点头后手工运行：
--     sudo -n -u postgres psql -d league -f docs/db/待审-西甲两对合并.sql
--
-- 工单：tickets/P0-TEAMMIX1.txt
-- 依据：2026-09-16 真盘核验（C 决策已接受 4 支降级队缺口，本文件只处理有 AF 行的 2 对）
--
-- 【为什么要做】
--   西甲 9 场只有 3 场两边都有 AF 历史；6 场缺一侧，其中 4 支是真降级（无历史），
--   2 支的 AF 行**早就在库**（Atletico Madrid 被 fact.fixture 引用 114 次）。
--   合并后这 2 场的历史特征立刻可用，一分钱不花。
--
-- 【合并方向】winner = 持 af_id 的 AF 行（历史挂在那），loser = 我插的 sporttery 行。
--   ⚠️ 与 P0-TEAMMIX1 原方案 1 相反——原方案写「winner = 持 sporttery 键那一行」是错的：
--   预测通过 fact.fixture 连历史，Atletico Madrid 被引用 114 次、马德里竞技 0 次，
--   winner 必须是 AF 行，否则合并后 join 还是打不到历史。
--
-- 【三个实测约束（决定这份 SQL 的写法）】
--   1. af_id / fd_id / jc_id 都是**生成列**（从 aliases 派生）⇒ 改 aliases 即生效，不用单独 set。
--   2. ref.team 有 4 个**部分唯一索引**（不是 pg_constraint 项，`pg_constraint` 查询看不到——
--      我踩过这个坑）：
--        team_jc_key   UNIQUE (sport, jc_id) WHERE jc_id IS NOT NULL
--        team_af_key   UNIQUE (sport, af_id) WHERE af_id IS NOT NULL
--        team_fd_key   UNIQUE (sport, fd_id) WHERE fd_id IS NOT NULL
--        team_sport_name_cn_key UNIQUE (sport, name_cn)
--      ⇒ **必须先摘 loser 的 sporttery 键，再加到 winner**。顺序反了会撞 team_jc_key
--      （干跑实测：先加 winner → duplicate key (football,172) already exists）。
--   3. ref.team_merge_map 在 scripts/ web/ tests/ **零引用**（4 行先例全是死数据）
--      ⇒ 写进去只为审计留痕，别指望它影响 join。
--
-- 【不会碰的东西】
--   不改 fact.*（fact.jc_match 的 home/away_team_id 在**下一次 ingest** 自动重解析：
--     我的 jc_topic.py 热修已让 `_team()` 每轮入库自动解析，ON CONFLICT DO UPDATE 会覆盖回 winner）。
--   不删任何行（league_ing 无 DELETE 权限）。不 DDL。不动 scripts/core/。
-- ============================================================================

begin;

-- 0) 前置断言：四行必须都在，且键位如预期；不符立即 abort（不留下半成品）
do $$
declare
  bad text;
begin
  if not exists (select 1 from ref.team where team_id=2354 and af_id=530
                 and not (aliases ? 'sporttery')) then
    bad := bad || 'row 2354 (Atletico Madrid) 不是预期状态；';
  end if;
  if not exists (select 1 from ref.team where team_id=120507 and jc_id=172 and af_id is null) then
    bad := bad || 'row 120507 (马德里竞技) 不是预期状态；';
  end if;
  if not exists (select 1 from ref.team where team_id=3114 and af_id=542
                 and not (aliases ? 'sporttery')) then
    bad := bad || 'row 3114 (Alaves) 不是预期状态；';
  end if;
  if not exists (select 1 from ref.team where team_id=120506 and jc_id=171 and af_id is null) then
    bad := bad || 'row 120506 (阿拉维斯) 不是预期状态；';
  end if;
  if bad <> '' then raise exception '前置断言失败：%s', trim(trailing '；' from bad); end if;
end $$;

-- 1) loser 中性化：摘掉 sporttery 键（幂等：已摘则 no-op）
--    ⚠️ 必须在第 2 步之前：顺序反了撞 team_jc_key（见顶部约束 2）
update ref.team set aliases = aliases - 'sporttery'
 where team_id = 120507 and aliases ? 'sporttery';

update ref.team set aliases = aliases - 'sporttery'
 where team_id = 120506 and aliases ? 'sporttery';

-- 2) winner 挂 sporttery 键（幂等：已持有则 no-op）
update ref.team set aliases = aliases || '{"sporttery":"172"}'::jsonb
 where team_id = 2354 and not (aliases ? 'sporttery');

update ref.team set aliases = aliases || '{"sporttery":"171"}'::jsonb
 where team_id = 3114 and not (aliases ? 'sporttery');

-- 3) 留痕（仅审计；代码零引用，不影响 join）
insert into ref.team_merge_map(winner_id, loser_id, src_key, src_id, merged_at)
select 2354, 120507, 'sporttery', '172', now()
 where not exists (select 1 from ref.team_merge_map m where m.loser_id = 120507)
union all
select 3114, 120506, 'sporttery', '171', now()
 where not exists (select 1 from ref.team_merge_map m where m.loser_id = 120506);

-- 4) 验收查询 A：四行最终状态
--    期望 2354 = af530 fd78 jc172 三键齐；3114 = af542 fd263 jc171 三键齐；
--    120507 / 120506 只剩空壳（三键全 NULL），成为无害孤儿行。
select 'A) 四行状态' as check_, team_id, name_cn, af_id, fd_id, jc_id, aliases::text
  from ref.team where team_id in (2354, 3114, 120506, 120507) order by team_id;

-- 5) 验收查询 B：jc_id 不再重复（本应 0 行）
select 'B) 重复 jc_id（应空）' as check_, jc_id, count(*)
  from ref.team where jc_id is not null group by jc_id having count(*) > 1;

-- 6) 验收查询 C：下一步（本文件不执行）
--    bash ~/bin/jc-ingest-run.sh
--    然后确认 fact.jc_match 里 sporttery 171/172 的行指向 winner：
--      select home_sporttery_id, home_team_id, away_sporttery_id, away_team_id
--        from fact.jc_match
--       where home_sporttery_id in (171,172) or away_sporttery_id in (171,172);
--      期望 home/away_team_id ∈ {2354, 3114}，不再是 {120506, 120507}。

commit;
