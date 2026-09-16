-- ⚠️⚠️ **未批准的草案，别执行**（D3：球队对照必须人工点头；文件名带「待审」就是这个意思）
-- 生成：队长 2026-09-16 自动匹配（规则见 docs/project/待审-竞彩球队对照.md：NFKC 归一 + 去「队/俱乐部」+ 去空格后**逐字相等**）
-- 写入目标 = `ref.team.aliases->>'sporttery'`（官方 teamId，**数字串**）；
--   `ref.team.jc_id` 是由它生成的 STORED 生成列（见 `infra_p0_8` 第 20-27 行），另有 partial unique `(sport, jc_id)`
--   ⇒ **同一个官方 id 不可能塞进两支队**（冲突会被索引直接拒绝），所以这份草案可以反复执行（幂等：`and not (aliases ? 'sporttery')`）。
-- 共 8 支队，**全部是唯一命中**（疑似与缺池的一律没写进来，等你在《待审》文档里点）：
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"11"') where team_id = 60 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 利物浦  ← 官方名「利物浦」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"30"') where team_id = 2356 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 埃尔切  ← 官方名「埃尔切」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"677"') where team_id = 2338 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 塞维利亚  ← 官方名「塞维利亚」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"534"') where team_id = 2337 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 奥萨苏纳  ← 官方名「奥萨苏纳」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"849"') where team_id = 2344 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 巴列卡诺  ← 官方名「巴列卡诺」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"19"') where team_id = 65 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 热刺  ← 官方名「热刺」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"510"') where team_id = 2340 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 西班牙人  ← 官方名「西班牙人」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"1"') where team_id = 58 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 阿森纳  ← 官方名「阿森纳」

-- ▼ 批准后必须**回填已入库场次**（生成列不会替你改 `fact.jc_match` 里的历史 NULL）：
--   update fact.jc_match m set home_team_id = h.team_id, away_team_id = a.team_id
--     from ref.team h, ref.team a
--    where h.jc_id = m.home_sporttery_id and a.jc_id = m.away_sporttery_id
--      and (m.home_team_id is null or m.away_team_id is null);
-- ▲ 执行前后各跑一次、两行结果都要贴进验收：
--   select count(*) filter (where aliases ? 'sporttery') as 有对照, count(*) as 总队 from ref.team;
--   select count(*) as 还差几场 from fact.jc_match where home_team_id is null or away_team_id is null;
