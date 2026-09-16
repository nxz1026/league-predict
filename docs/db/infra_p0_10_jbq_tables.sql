-- infra P0-10 · 竞彩篮球三表（`fact.jbq_match` / `fact.jbq_offer` / `fact.jbq_result`）
-- ⚠️ **本文件是 2026-09-17 10:36 由队长从**运行中的库**反向重建的（`pg_dump --schema-only -t fact.jbq_*`，去掉 \restrict/SET/注释行）：
--    STORE1 当年执行过一版 DDL 但那**份文件从未进过 git** ⇒ 属于队长错账（见 `docs/project/OMP派工手册.md` §9-65）：
--    "建了表没留 DDL 文档"= 环境不可重建。现已按库内实况补回，并逐列核对：
--      `fact.jbq_match` 22 列 / PK(match_id) / 2 条 FK→ref.team / is_current 默认 true
--      `fact.jbq_offer` 9 列 / PK(match_id, play_type, snap_ts) / `snap_ts` 是 **text**（不是 timestamptz：篮彩快照戳直接沿用对方给的字符串，形状待开售真包核验）
--      `fact.jbq_result` 30 列 / PK(match_id) / 四玩法块摊平（mnl/hdc/hilo/wnm 各 5 列）+ `raw_blocks` jsonb
--    重建验证（队长 10:40 做：**滚动事务里建完就 rollback，零残留**）：把本文件 `fact.` 换成临时 schema 重放 ⇒ **表 3 / 约束 19 / 列 61**，
--      与运行库逐项相同（`22 + 9 + 30 = 61`，`fact` schema 下 jbq 约束也是 19）⇒ 本文件**可以当真**（不是"看着像"）。
--    重放语义：**全新环境直接 -f**；已存在的环境会报 `already exists` ⇒ 正常（与 p0_1..p0_8 同一约定，forward-only 不回头改）。
-- ⚠️ 三份"待核验"事实（**别当已确认**）：① 篮彩开售包 `jclq_offer` 至今每批都是 `.empty` ⇒ `jbq_offer` 的列形状**没被真包验证过**；
--    ② `jbq_result` 无半场数据（22 键实测无该键）；③ 队名映射同竞彩足球 ⇒ 在 `aliases->>'sporttery'` 补齐之前 `home/away_team_id` 会一直是 NULL。
-- 授权（与 jc_* 三表完全一致）：`league_ro`/`league_app` 只读，`league_ing` 可 SELECT/INSERT/UPDATE、**故意没有 DELETE**
--   （缺档一律用 `#MISSING` 记录行表达，不靠删；要删只能超级用户 ⇒ 见 `~/bin/jc-false-gaps.py`）。

CREATE TABLE fact.jbq_match (
    match_id bigint NOT NULL,
    match_num text,
    match_num_str text,
    league_id integer,
    league_cn text,
    league_abbr text,
    home_cn text,
    away_cn text,
    home_sporttery_id bigint,
    away_sporttery_id bigint,
    home_team_id integer,
    away_team_id integer,
    match_date date,
    match_time text,
    kickoff_bj timestamp with time zone,
    status integer,
    pool_status text,
    is_current boolean DEFAULT true NOT NULL,
    src_hash text NOT NULL,
    src_file text NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone
);
COMMENT ON TABLE fact.jbq_match IS '竞彩篮球场次（源：jclq_result 真包 23 行 + 今后 jclq_offer 开售包）；一场一行，upsert 取最新';
CREATE TABLE fact.jbq_offer (
    match_id bigint NOT NULL,
    play_type text NOT NULL,
    snap_ts text NOT NULL,
    pool_code text,
    goal_line numeric(6,2),
    options jsonb,
    odds_history jsonb,
    src_hash text NOT NULL,
    src_file text NOT NULL
);
COMMENT ON TABLE fact.jbq_offer IS '竞彩篮球盘口快照序列：(场次,玩法,快照) 一行；封盘前最后一条 = 篮彩收盘价（CLV 用）。**形状待开售真包核验**';
CREATE TABLE fact.jbq_result (
    match_id bigint NOT NULL,
    final_score text,
    ft_h integer,
    ft_a integer,
    status integer,
    pool_status text,
    betting_single smallint,
    mnl_combination text,
    mnl_desc text,
    mnl_result_status text,
    mnl_odds numeric(8,3),
    hdc_line numeric(6,2),
    hdc_combination text,
    hdc_desc text,
    hdc_result_status text,
    hdc_odds numeric(8,3),
    hilo_line numeric(6,2),
    hilo_combination text,
    hilo_desc text,
    hilo_result_status text,
    hilo_odds numeric(8,3),
    wnm_combination text,
    wnm_desc text,
    wnm_result_status text,
    wnm_odds numeric(8,3),
    raw_blocks jsonb,
    src_hash text NOT NULL,
    src_file text NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone
);
COMMENT ON TABLE fact.jbq_result IS '竞彩篮球官方赛果（源：jclq_result，一场一行、四玩法块摊平）；**无半场数据**（22 键实测无该键）';
ALTER TABLE ONLY fact.jbq_match
    ADD CONSTRAINT jbq_match_pkey PRIMARY KEY (match_id);
ALTER TABLE ONLY fact.jbq_offer
    ADD CONSTRAINT jbq_offer_pkey PRIMARY KEY (match_id, play_type, snap_ts);
ALTER TABLE ONLY fact.jbq_result
    ADD CONSTRAINT jbq_result_pkey PRIMARY KEY (match_id);
ALTER TABLE ONLY fact.jbq_match
    ADD CONSTRAINT jbq_match_away_team_id_fkey FOREIGN KEY (away_team_id) REFERENCES ref.team(team_id);
ALTER TABLE ONLY fact.jbq_match
    ADD CONSTRAINT jbq_match_home_team_id_fkey FOREIGN KEY (home_team_id) REFERENCES ref.team(team_id);

grant select on fact.jbq_match, fact.jbq_offer, fact.jbq_result to league_ro, league_app;
grant select, insert, update on fact.jbq_match, fact.jbq_offer, fact.jbq_result to league_ing;

