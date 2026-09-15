-- ============================================================
-- league-predict 数据库设计 v2（PG 18 @ oracle，127.0.0.1）——设计草案，未执行
-- 原则：官方口径(sporttery 国内机)与国际盘口(海外API)双源；快照只追加不改写；
--       国内机→oracle 交付物为 JSONL 文件，入库由 oracle 侧 ingest 完成（国内机零 DB 凭据）
-- ============================================================

-- ---------- 角色（仅本机连接：listen 保持 127.0.0.1）----------
CREATE ROLE league_ing  LOGIN PASSWORD '***' VALID UNTIL '2027-06-30';  -- 入库进程
CREATE ROLE league_app  LOGIN PASSWORD '***' VALID UNTIL '2027-06-30';  -- web+模型
CREATE ROLE league_ro   LOGIN PASSWORD '***' VALID UNTIL '2027-06-30';  -- 人工分析

-- ---------- 表空间（当前单盘，价值=未来挪盘/备份粒度；见文档§容量测算）----------
CREATE TABLESPACE ts_snap LOCATION '/var/lib/pgsql/18/tablespaces/ts_snap';   -- 盘口快照类
CREATE TABLESPACE ts_stg  LOCATION '/var/lib/pgsql/18/tablespaces/ts_stg';    -- 国内机装载区
-- 其余表用 pg_default。

CREATE DATABASE league OWNER league_app;

-- ============ ref 参考层 ============
CREATE SCHEMA ref;
CREATE TABLE ref.league (
  league_key   text PRIMARY KEY,          -- epl/laliga/…/csl/cl/wc/nba/cba
  cn_name      text NOT NULL,
  sport        text NOT NULL CHECK (sport IN ('football','basketball')),
  scope        text NOT NULL CHECK (scope IN ('regular','irregular')),  -- 世界杯/欧冠等=irregular
  window_from  date, window_to date,      -- 开关制：irregular 的激活窗口
  ids          jsonb NOT NULL DEFAULT '{}', -- {api_football:39, football_data:'PL', espn:'…', sporttery:'…'}
  updated_at   timestamptz DEFAULT now()
);
CREATE TABLE ref.team (
  team_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sport     text NOT NULL,
  name_cn   text NOT NULL,
  aliases   jsonb NOT NULL DEFAULT '{}',   -- {api_football:"Man City", sporttery:"曼城", …}
  UNIQUE (sport, name_cn)
);
CREATE TABLE ref.jc_match_num (             -- 竞彩场次编号（周三001…）
  jc_match_id  text PRIMARY KEY,            -- '20260915-w3-001' 规范化
  display_num  text NOT NULL,               -- '周三001'
  fixture_id   bigint,                      -- 关联 fact.fixture（国内机只给队名，ingest 按 alias+时间窗对齐；对齐失败置 NULL 待人工）
  sell_date    date NOT NULL,
  play_types   text[] NOT NULL               -- 当日开售玩法 ['had','hhad','crs','ttg','haf']
);
CREATE TABLE ref.jc_issue (                 -- 传统足彩奖期
  issue_no   text PRIMARY KEY,              -- 如 '26125'
  game       text CHECK (game IN ('14c','rq','bqc','jqc')),  -- 胜负彩/任9/半全场6/进球4
  matches    jsonb NOT NULL,                -- [{seq,home,away,kickoff,league},…14或9或6或4场]
  sales_from timestamptz, sales_to timestamptz, draw_at timestamptz,
  status     text NOT NULL DEFAULT 'onsale' -- onsale/drawn/void
);

-- ============ fact 事实层 ============
CREATE SCHEMA fact;
CREATE TABLE fact.fixture (
  fixture_id  bigint PRIMARY KEY,
  league_key  text REFERENCES ref.league,
  kickoff_at  timestamptz NOT NULL,
  home_team_id bigint REFERENCES ref.team, away_team_id bigint REFERENCES ref.team,
  source_ids  jsonb NOT NULL DEFAULT '{}',
  status      text NOT NULL DEFAULT 'scheduled',
  jc          boolean NOT NULL DEFAULT false   -- 是否竞彩开售场
);
CREATE INDEX ON fact.fixture (kickoff_at) ;
CREATE INDEX ON fact.fixture (league_key, kickoff_at);

CREATE TABLE fact.fixture_result (          -- 赛果多源并存（国际/官方各一行，ingest 冲突即报警）
  fixture_id bigint, source text,           -- 'api_football'|'football_data'|'sporttery'
  ft_h smallint, ft_a smallint, ht_h smallint, ht_a smallint,
  confirmed_at timestamptz,
  PRIMARY KEY (fixture_id, source)
);

CREATE TABLE fact.line_snapshot (           -- 国际博彩盘口时序（开盘/临场两时点+手动加采）
  id         bigint GENERATED ALWAYS AS IDENTITY,
  captured_at timestamptz NOT NULL,
  fixture_id bigint NOT NULL,
  bookmaker  text NOT NULL,                 -- pinnacle/bet365/…（33家白名单）
  market     text NOT NULL CHECK (market IN ('1x2','ah','ou')),
  line       numeric,                       -- 1x2 为 NULL；ah/ou 有盘口线
  p_home numeric, p_draw numeric, p_away numeric,  -- 去水后概率（1x2 三项；两向用 home/away）
  odds_home numeric, odds_draw numeric, odds_away numeric, -- 原水（含返奖率）
  phase      text NOT NULL CHECK (phase IN ('open','mid','close'))
) PARTITION BY RANGE (captured_at);         -- 按月分区，保留24月
-- 分区模板：CREATE TABLE fact.line_snapshot_y2026m09 PARTITION OF fact.line_snapshot FOR VALUES …;
CREATE INDEX ON fact.line_snapshot (fixture_id, market, phase);

CREATE TABLE fact.jc_offer (                -- 竞彩官方盘口/固定奖金/单关标记（国内机 JSONL 装载）
  id          bigint GENERATED ALWAYS AS IDENTITY,
  snap_ts     timestamptz NOT NULL,          -- 接口内更新时间戳（非本地 now）
  jc_match_id text NOT NULL,
  play_type   text NOT NULL,                 -- had/hhad/crs/ttg/haf + 过关 combo
  line        text,                          -- 让球线/大小分线
  options     jsonb NOT NULL,                -- {"home":1.85,"draw":3.40,"away":4.20} 或比分54格等
  single      boolean NOT NULL DEFAULT false,-- 单关资格！
  raw_hash    text NOT NULL                  -- 源行 sha256，幂等去重
) PARTITION BY RANGE (snap_ts);              -- 按月分区
CREATE UNIQUE INDEX ON fact.jc_offer (jc_match_id, play_type, line, snap_ts);

CREATE TABLE fact.jc_result (               -- 竞彩/传统 官方开奖与奖级（国内机装载）
  key        text PRIMARY KEY,               -- 'jc:20260915-w3-001' 或 'issue:26125'
  kind       text NOT NULL,
  result     jsonb NOT NULL,                 -- 比分/开奖号
  prize      jsonb,                          -- [{tier,winners,pool}…]（传统足彩奖级+滚存）
  sales      numeric,                        -- 期销量（奖级预估用）
  drawn_at   timestamptz
);

CREATE TABLE fact.lottery_draw (            -- 数字彩：大乐透/排3/排5/七星彩
  game     text NOT NULL,                   -- dlt/pl3/pl5/qxc
  issue_no text NOT NULL,
  draw_date date NOT NULL,
  numbers  jsonb NOT NULL,                  -- {"front":[…],"back":[…]}/位序数组
  prize    jsonb,                           -- 官方奖级注数奖金
  sales    numeric,
  PRIMARY KEY (game, issue_no)
);

-- ============ model 预测层 ============
CREATE SCHEMA model;
CREATE TABLE model.pred_run (
  run_id bigserial PRIMARY KEY, run_at timestamptz DEFAULT now(),
  commit text, params jsonb, n_fixtures int, note text
);
CREATE TABLE model.pred_fixture (
  run_id bigint REFERENCES model.pred_run, fixture_id bigint,
  lambda_home numeric, lambda_away numeric,
  matrix jsonb NOT NULL,                    -- 0-8球联合矩阵(派生一切的基础底座)
  elo jsonb, features jsonb,                -- 可解释留痕（26维向量）
  PRIMARY KEY (run_id, fixture_id)
);
CREATE TABLE model.pred_market (            -- 派生层输出：每玩法每选项概率（与 fact.jc_offer 同构可 JOIN）
  run_id bigint, fixture_id bigint, play_type text, option_code text,
  p numeric NOT NULL, p_ai_ref numeric,     -- AI 参考值放这（展示带 ai_ref 标记，不进 EV）
  PRIMARY KEY (run_id, fixture_id, play_type, option_code)
);

-- ============ analysis 评估层 ============
CREATE SCHEMA analysis;
CREATE TABLE analysis.backtest_market (
  fixture_id bigint, play_type text, option_code text,
  p_pred numeric, outcome smallint,          -- 0/1 命中
  clv numeric,                                -- 模型概率 vs 收盘去水的差（价值验证核心指标）
  src_run bigint, PRIMARY KEY (fixture_id, play_type, option_code, src_run)
);
CREATE TABLE analysis.ev_report (            -- 串关 EV 报告（无票单 UI，纯报告）
  report_id bigserial PRIMARY KEY, made_at timestamptz DEFAULT now(),
  legs jsonb NOT NULL,                        -- [{jc_match_id,play_type,option,sp,p,ev}…]
  p_parlay numeric, ev numeric, kelly numeric, corr_adj numeric,
  note text
);

-- ============ stg 国内机装载区（JSONL 原样落位，ingest 校验后入正式表）============
CREATE SCHEMA stg;
CREATE TABLE stg.jczq_offer    (line jsonb, loaded_at timestamptz DEFAULT now(), src_file text);
CREATE TABLE stg.jczq_result   (line jsonb, loaded_at timestamptz DEFAULT now(), src_file text);
CREATE TABLE stg.jc_issue      (line jsonb, …);
CREATE TABLE stg.jc_issue_result (line jsonb, …);
CREATE TABLE stg.jclq_offer    (line jsonb, …);
CREATE TABLE stg.jclq_result   (line jsonb, …);
CREATE TABLE stg.lottery_draw  (line jsonb, …);
-- 全部 UNLOGGED（staging 可重放），ts_stg 表空间；ingest 完成即清空当日批。

-- ============ ops 运行留痕 ============
CREATE SCHEMA ops;
CREATE TABLE ops.ingest_log (
  id bigserial PRIMARY KEY, topic text, src_file text, rows_in int, rows_ups int,
  rejected jsonb, ok boolean, at timestamptz DEFAULT now()
);
CREATE TABLE ops.quota_ledger (day date, source text, used int, cap int, PRIMARY KEY(day, source));

-- ============ 视图（口径统一入口）============
CREATE VIEW v.market_full AS   -- 任意一场的：官方SP × 国际收盘 × 模型概率 三方对照
  SELECT f.fixture_id, f.kickoff_at, o.play_type, o.options AS jc_options, o.single,
         s.p_home AS close_home, s.p_away AS close_away, m.p AS p_model
  FROM fact.fixture f
  JOIN fact.jc_offer o ON …     -- latest snap per match/play_type
  JOIN fact.line_snapshot s ON … -- phase='close', bookmaker='pinnacle'
  JOIN model.pred_market m ON …  -- latest run
;
-- v.matrix_totals / v.matrix_handicap / v.matrix_halftime：矩阵边际化的 SQL 兜底实现（与 derive/ 对账用）