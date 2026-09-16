-- infra P0-11 · 盘口全历史表（契约 v1.4 / 端点 getOddsHistoryV1）
-- 队长 2026-09-17 09:25 北京。依据 = 国内机 09:12 回传的两份真样本（**逐字段实测，不是猜的形状**）：
--   odds_history_sample/finished_卡塔尔亚vs韩国亚__2041482.jsonl  → had 6 版 / hhad 8 版 / crs 5 版 / ttg 5 版 / haf 5 版
--   odds_history_sample/onsale_柏太阳神__2041495.jsonl            → 每个玩法各 1 版（官方对未开售场次**不回填历史**）
--   合计 34 个"价格版"；同 (match_id, play_type, updateDate+updateTime) **无撞键** ⇒ PK 用它；数组顺序**严格"新→旧"**（实测单调）。
-- 为什么新开一张表而不是用 fact.jc_offer.odds_history（该列已存在、当前恒 NULL）：
--   ① CLV 要的是"逐版一行"，塞进 jsonb 就只能全表展开才能比水位；② 一行一版可加 CHECK/索引、可增量 upsert；
--   ③ jc_offer 的粒度是"某次抓取的那一版"（snap_ts），与"官方给的历史第 k 版"是两个时间轴，混在一张表必然口径打架。
--   ⇒ `odds_history` 这列**保留但继续留空**（不删列，forward-only），注释里写明"已废弃，见本表"。

create table if not exists fact.jc_odds_history (
  match_id        bigint        not null,               -- = payload.matchId（与 fact.jc_match.match_id 同一 ID 空间）
  play_type       text          not null,               -- 与 jc_offer 同一词表：had/hhad/crs/ttg/haf（注意 hafuList ⇒ 'haf'）
  update_ts       timestamptz   not null,               -- updateDate + updateTime，**北京时区显式换算**（官方给的是本地墙钟）
  seq_no          int           not null,               -- 0 = 该玩法最新一版（官方数组新→旧，实测单调）
  goal_line       text,                                 -- 原样字符串（hhad 形如 "+2"；其它玩法是空串 ⇒ 存 NULL）
  goal_line_value numeric(6,2),                         -- 解析后的让球线，**解不出就 NULL，不许猜**
  odds            jsonb         not null,               -- 该版原始对象全量（含每个选项的 *f 升降箭头：1 升 / 0 平 / -1 降）
  is_first        boolean       not null default false, -- 该玩法**最早**一版（≈开盘水）
  is_close        boolean       not null default false, -- 该玩法**最新**一版且比赛已完场（≈封盘水 ⇒ CLV 的对照基准）
  league_id       integer,                              -- payload.leagueId（原样留痕，便于日后按联赛收窄范围）
  src_hash        text          not null,
  src_file        text          not null,
  first_seen_at   timestamptz   not null default now(),
  last_seen_at    timestamptz   not null default now(),
  primary key (match_id, play_type, update_ts),
  constraint jc_odds_history_play_type check (play_type in ('had','hhad','crs','ttg','haf')),
  constraint jc_odds_history_odds_object check (jsonb_typeof(odds) = 'object'),
  constraint jc_odds_history_seq_no_check check (seq_no >= 0)
);

-- 无外键（**故意**，§9-50）：两份样本的 matchId 2041482 / 2041495 都不在 `fact.jc_match`（我们只有 17 场），
-- 且用户 06:35 定的联赛封闭清单之外那些场次**本来就不该被预测** ⇒ 先只留痕不建 FK；
-- 等真包跑起来**实测覆盖率 = 100%** 之后再 forward-only 追加 FK（与 jbq_result 同一处置）。
-- 唯一保留的读侧索引：CLV / 走势都按"某玩法某一时刻前后的版本"取数。
create index if not exists jc_odds_history_play_ts_idx on fact.jc_odds_history (play_type, update_ts desc);
create index if not exists jc_odds_history_close_idx   on fact.jc_odds_history (is_close, match_id) where is_close;

comment on table  fact.jc_odds_history is '竞彩足球**盘口全历史**（官方 getOddsHistoryV1，一次请求拿回某场整条走势）；一行 = 一个玩法的一个价格版';
comment on column fact.jc_odds_history.seq_no    is '0=最新一版；max(seq_no)=最早一版（≈开盘）。数组顺序实测严格新→旧';
comment on column fact.jc_odds_history.is_close  is '该玩法最新版且比赛已完场 ⇒ 封盘水近似；真 CLV = 我方下注水 vs 本版';
comment on column fact.jc_odds_history.odds      is '原始该版对象全量（含 *f 箭头），宁可不插不可插错：不裁字段、不改名';
comment on column fact.jc_offer.odds_history     is '已废弃：全历史改存 fact.jc_odds_history（逐版一行），本列**永久留 NULL**';

grant select on fact.jc_odds_history to league_ro, league_app;
grant select, insert, update on fact.jc_odds_history to league_ing;
