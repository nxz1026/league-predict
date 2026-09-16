-- ============================================================================
-- ✅ 已执行：2026-09-17 19:2x，用户批复原话「执行」⇒ 单个事务 BEGIN…COMMIT 原子落地（15 UPDATE + 6 INSERT + 回填 UPDATE 10）。
--    回执：西甲 0/9 → 9/9、ref.team 122→128、sporttery 键=21、jc_id 非空=21、序列 120505→120511。
--    2026-09-17 19:3x 补幂等：6 条 INSERT 原先没有守卫（重跑会被 partial unique (sport,jc_id) 打断），现已改 not exists ⇒ 整份脚本可反复执行。
-- 生成：队长 2026-09-17 17:35。批复依据 = 用户 17:3x 原话「池子开始可以大，后面可以收缩」
--        ⇒ 已选定 **方案 A**（按封闭清单把池子补大，后续再收缩），见
--        `docs/project/待审-竞彩球队对照.md` 的 A/B/C 三选一。
-- 生成方式：**全部数据来自本库自己**（`fact.jc_match` 的竞彩官方中文名 + `ref.team` 现有 122 行），
--        没有用任何外部接口、没有消耗配额、没有一个名字是我猜的。
--
-- 结构约定（从库现查，非假设）：
--   · `ref.team.jc_id` 是 **GENERATED ALWAYS AS STORED**，由 `aliases->>'sporttery'` 生成
--     （`infra_p0_8_jc_tables.sql:23-25`，正则要求纯数字串 ⇒ sporttery 必须存成 JSON **字符串** `"171"`）
--     ⇒ INSERT 时**不许**列 jc_id，UPDATE 时只改 aliases；
--   · `partial unique (sport, jc_id)` ⇒ 同一官方 id 塞进两队会被索引直接拒绝（天然防撞）；
--   · `team_id` 是 **identity GENERATED ALWAYS**（序列 `ref.team_team_id_seq`）；表内 min=57 / max=10119，
--     但**序列 last_value 已是 120311**（历史上被推进过、值未回写）⇒ 新增行**不指定 team_id，交给 identity 自动分配**
--     （实际执行时取到 120506~120511，序列 120505→120511 恰好 +6）。我 17:38 试过手填 `10120`，报
--     `cannot insert a non-DEFAULT value into column "team_id"`（GENERATED ALWAYS 必须 OVERRIDING SYSTEM VALUE）；
--     而强行 OVERRIDING 再 setval 会把序列往回拨，风险更大 ⇒ **让序列自增，最省事也最不会撞号**。
-- ============================================================================

-- ---------------------------------------------------------------- 0) 执行前只读核对
--    预期输出：存在=15 / sporttery已占用=0 / jc_id非空=0 / 待回填=9
select '目标 team_id 均存在: '||count(*) from ref.team where team_id in (2356,2343,2355,2351,2340,2353,2337,2350,2338,2342,2344,2347,60,65,58);
select 'sporttery 已占用: '||count(*) from ref.team where aliases ? 'sporttery';
select 'jc_id 非空: '||count(jc_id) from ref.team;
select '待回填 jc_match(西甲): '||count(*) from fact.jc_match where league_id=62 and (home_team_id is null or away_team_id is null);

-- ---------------------------------------------------------------- 1) 西甲 12 条（11 逐字唯一 + 1 译名合并）
--    唯一 11 支：`jc_match.home_cn/away_cn` 与 `ref.team.name_cn` 做 NFKC + 去「队/俱乐部」+ 去空格后**逐字相等**
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"30"')  where team_id = 2356 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 埃尔切        ← 官方名「埃尔切」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"401"') where team_id = 2343 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 巴塞罗那      ← 官方名「巴塞罗那」（abbr 巴萨）
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"505"') where team_id = 2355 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 皇家贝蒂斯    ← 官方名「皇家贝蒂斯」（abbr 贝蒂斯）
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"506"') where team_id = 2351 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 毕尔巴鄂竞技  ← 官方名「毕尔巴鄂竞技」（abbr 毕尔巴鄂）
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"510"') where team_id = 2340 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 西班牙人      ← 官方名「西班牙人」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"511"') where team_id = 2353 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 赫塔费        ← 官方名「赫塔费」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"534"') where team_id = 2337 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 奥萨苏纳      ← 官方名「奥萨苏纳」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"664"') where team_id = 2350 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 皇家马德里    ← 官方名「皇家马德里」（abbr 皇马）
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"677"') where team_id = 2338 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 塞维利亚      ← 官方名「塞维利亚」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"679"') where team_id = 2342 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 比利亚雷亚尔  ← 官方名「比利亚雷亚尔」（abbr 比利亚雷）
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"849"') where team_id = 2344 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 巴列卡诺      ← 官方名「巴列卡诺」
-- ◻ 译名合并 1 支（**同队两译名**，全场相似度 0.75 也是最高）：官方「巴伦西亚」= 我方「瓦伦西亚」
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"678"') where team_id = 2347 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 瓦伦西亚 → 巴伦西亚
--    ↑ 这条与另外 11 条不同：它靠"同队两译名"判断，不是逐字相等。**不认就删掉这 1 行**。

-- ---------------------------------------------------------------- 2) 英超 3 条（承自上一版草案，09-15 场次）
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"11"') where team_id = 60 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 利物浦
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"19"') where team_id = 65 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 热刺
update ref.team set aliases = jsonb_set(coalesce(aliases,'{}'::jsonb), '{sporttery}', '"1"')  where team_id = 58 and not (coalesce(aliases,'{}'::jsonb) ? 'sporttery');  -- 阿森纳

-- ---------------------------------------------------------------- 3) 缺池 6 支：INSERT 新队（team_id 交给 identity；带 not exists 守卫 ⇒ 可反复执行）
--    名字**逐字取自** `fact.jc_match.home_cn`（竞彩官方全名），不是猜的；abbr 取自 `away_abbr/home_abbr`。
--    ⚠️ `af_id` 一律留 NULL（见文件末"缺口"说明）——没有 AF id 就没有历史比赛可供训练，
--      这 6 支队参与的场次**对齐得上、但预测只有联赛先验**，不能当"已经能预测"。
insert into ref.team (sport, name_cn, aliases) select 'football','阿拉维斯', '{"sporttery":"171"}' where not exists (select 1 from ref.team where sport='football' and aliases ? 'sporttery' and (aliases->>'sporttery')='171');
insert into ref.team (sport, name_cn, aliases) select 'football','马德里竞技', '{"sporttery":"172"}' where not exists (select 1 from ref.team where sport='football' and aliases ? 'sporttery' and (aliases->>'sporttery')='172');
insert into ref.team (sport, name_cn, aliases) select 'football','莱万特', '{"sporttery":"33"}' where not exists (select 1 from ref.team where sport='football' and aliases ? 'sporttery' and (aliases->>'sporttery')='33');
insert into ref.team (sport, name_cn, aliases) select 'football','拉科鲁尼亚', '{"sporttery":"509"}' where not exists (select 1 from ref.team where sport='football' and aliases ? 'sporttery' and (aliases->>'sporttery')='509');
insert into ref.team (sport, name_cn, aliases) select 'football','马拉加', '{"sporttery":"512"}' where not exists (select 1 from ref.team where sport='football' and aliases ? 'sporttery' and (aliases->>'sporttery')='512');
insert into ref.team (sport, name_cn, aliases) select 'football','桑坦德竞技', '{"sporttery":"676"}' where not exists (select 1 from ref.team where sport='football' and aliases ? 'sporttery' and (aliases->>'sporttery')='676');

-- ---------------------------------------------------------------- 4) 回填已入库的 36 场（生成列不会替你回填历史行）
--    幂等：`where ... is null` 只补空的；对不上的（清单外/缺池）留 NULL —— 那部分本来就不预测。
update fact.jc_match m set
  home_team_id = h.team_id, away_team_id = a.team_id
from ref.team h, ref.team a
where h.jc_id = m.home_sporttery_id and a.jc_id = m.away_sporttery_id
  and h.jc_id is not null and a.jc_id is not null
  and (m.home_team_id is null or m.away_team_id is null);

-- ---------------------------------------------------------------- 5) 执行后验收（预期见注释）
-- select count(*) from ref.team where aliases ? 'sporttery';          -- 21
-- select count(*) from fact.jc_match where home_team_id is not null and away_team_id is not null;  -- 西甲 9 场里 ≥ 3
-- select league_cn, count(*), sum((home_team_id is null)::int), sum((away_team_id is null)::int)
--   from fact.jc_match group by 1 order by 1;                         -- 看清"对齐率"

-- ============================================================================
-- 缺口（必须说清，别当"补完就能预测 9/9"）
-- ① 新插的 6 支 **`af_id` 是 NULL** ⇒ 没有 API-Football 历史比赛，
--    模型对它们**没有球队特征**（只能靠联赛先验）。要补必须走一次"AF 官方 id ↔ 竞彩中文名"人工对照，
--    我不做自动猜测合并（D3）。
-- ② 英超/意甲/德甲/法甲/中超/CBA/NBA 的池子**这一版没做**：今天 `fact.jc_match` 里这些联赛在清单内
--    **一场都没有**，我手上没有它们"已在用接口里出现过的官方中文名"，凭空造名字就是猜。
--    建议：**等下一批开售真包进来，按 171/172 同样的"从 jc_match 现查官方名"流程增量补**
--    （每批 135 场，通常 1–2 天就能覆盖到英超/意甲），而不是现在烧配额去拉整季名单。
-- ③ 清单外联赛（欧罗巴/解放者杯/亚冠精英/亚运/荷甲/巴甲/英冠…）共 27 场**故意不建映射**
--    ——按 06:35 的封闭清单它们只入库当走势资料，永不进模型（"池子先大后收缩"里"先大"的部分就是这批）。
-- ============================================================================
