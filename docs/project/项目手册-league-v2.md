# league-v2 · 会话压缩与实施包（2026-09-15 交接版）

> 本目录是"体彩全玩法覆盖"项目的**决策与工单基线**，由海外 DSH 会话（nd-dsh 机）压缩生成。
> 你在本机（NDORACLE）的操作方式见 `OMP-SKILL.md`；所有应用代码**一行都还没写**，本包 = 设计终稿。

## 0. 进度快照（队长每次落盘后更新 · 最后更新 2026-09-16 07:44 北京）
- **竞彩数据通路已打通**：真包 → `fact.jc_match/jc_offer/jc_result` **第一次进库并幂等复跑**
  · 旧包 3 批 = `17 场 / 170 盘口行 / 15 赛果`（`gap 8 条`）· 5 批混包 = `17 / 250 / 15`、`fact.jc_offer` = `250/17/4`
  · 机检全绿：`omp-ast-check` 0 违规、`jc-cols-check` 三表 ✔、`jc-fk-audit` 16 条外键全可满足、pytest **428 passed**
- **★ 看板已可用（08:37）**：`http://127.0.0.1:8077/static/jc.html`（我已替你起好服务；账号 `admin` / 口令见 `web/config.py` 的开发占位值，
  仅 127.0.0.1 有效）。三块面板：场次×盘口（40 行 = 最新营业日 8 场 × 5 玩法，`?day=2026-09-15` → 45 行）、
  基线指标（**4 行逐字对平已发布基线**：had 0.6270/acc 0.4772、crs 0.9405、ttg 0.8350、jqc 1.4536=两侧合算、`clv_filled` 全 0）、
  传统足彩期次（**空是正确**——2e 未装）。看板栈 commit **`11282d9`** 已 push；详细说明见晨间报告 §13。
- commit：**`9abb32b`**（装载层三文件 + 项目文档/DDL/工单纳入版本控制）→ **`7e5e13c`**（工单与晨报），均已 push `origin/v2`
- 国内机 v1.2 回传**独立复算 PASS**：新到 2 批、`.done` 已变**清单**、380/380 行 `src_hash` 一致 ⇒ 契约侧正式推进到 **v1.3（清单）**
- 篮彩：`jclq_result` **23 行真包**到手，`fact.jbq_match/jbq_offer/jbq_result` 三表已建（`docs/db/infra_p0_10_jbq_tables.sql`）
- **在跑/排队（全部 Agnes，一次一单）**：`P0-DASH1a`（看板数据层，07:42 派）→ `P0-COLLECT2o`（`.done` 清单优先装载，工单已备）
  → `P0-DASH1b`（router + 页面）→ `P0-COLLECT2e`（传统足彩五表）→ `P0-STORE2`（篮彩解析+写入）→ `CALIB1` → `CLV1`
- **已知未决（需要用户/国内机）**：① `.done` 第三列级联哈希算法定义；② 西甲/英超中文队名核对放行（`P0-JCALIGN1` 的 seed）；
  ③ 中超 AF `leagueId`（免费档无法做 id 发现，实测 `idLeague/idCountry/league=142` 全部拒绝）；④ NBA/CBA `leagueId`（休赛期无盘，真包只有亚运男篮/女篮世界杯）

## 1. 项目一句话
把 league-predict（五大联赛预测引擎）升级为覆盖中国体彩全玩法的分析系统：
竞彩足球 6 玩法 ×6 联赛（英超/西甲/意甲/德甲/法甲/中超）+ 传统足彩 4 玩法（14场/任9/6场半全场/4场进球）+ 篮彩 3 玩法 ×NBA/CBA + 数字彩 4 种（大乐透/排3/排5/七星彩，定位=管理/组合数学/EV/回测，**不预测**）。❌ 北单已排除。

## 2. 决策日志（用户逐条确认，不得推翻）
| # | 决策 |
|---|---|
| D1 | AI(LLM) 可产出参考数字，展示必须带 `ai_ref` 来源标签，**不进 EV/CLV 计算链** |
| D2 | 博彩盘口数据为最高优先（"非常重要"）：开盘+临场两时点快照，**只抓竞彩开售场**（免费配额约束），Pinnacle 加权去水=市场真概率，CLV=核心评价指标 |
| D3 | 不到万不得已不用爬虫；官方数据靠国内采集机走 webapi JSON 接口（非爬虫） |
| D4 | 官方数据通路：**国内机采集器 → rsync-over-ssh → 本机 /srv/league-staging/incoming → 本机 ingest 入库 PG**。国内机零 DB 凭据，oracle 建专用受限账号 league |
| D5 | 数据底座=本机 PostgreSQL 18.6（127.0.0.1:5432，peer；当前无 league 库，干净）；**FastAPI Cloud 退役**，最终部署=本机 Nginx（已有 /stock/ /dashboard/ /resume/ 先例，加 /league/）；Web 迁移后置，数据/算法先行 |
| D6 | 免费档先行：API-Football 历史只到 2022–2024（实测报文"Free plans do not have access to this season, try from 2022 to 2024"），慢回填 2–3 周；证明确需再付 $19/月 |
| D7 | 代码规范硬红线：**新文件 ≤100 行、函数 AST ≤50 行**；core 模型内核冻结不改（只 import）；web/ 冻结（不写新功能）；采集器独立新小 repo（`league-collector`，国内侧拥有，契约仅 JSONL+.done） |
| D8 | 仓库策略：**在 league-predict 原 repo 演进**（7,700 行可复用资产含 215 绿测试基线），main=v1 线上，`v2` 分支推进 P0–P4 |
| D9 | **配额/收费型外部数据源默认关闭、功能保留**，开关统一走配置层（`LEAGUE_SOURCE_<SRC>=on/off`、`LEAGUE_QUOTA_CAP_<SRC>=N`、`--allow-paid` 单次放行；`.env` 覆盖、真实 env 优先）。**关闭必须零副作用**：不发请求、不落 `raw.*`、不记 `ops.quota_ledger`。用户 2026-09-15 原话：「要省着用，功能留着，默认关闭」。<br>连带效果：D2 里的境外盘口（Pinnacle / The Odds API）降级为**可选校验通道**（P0-MARKET2 默认不派）——2026-09-15 探针核对确认**竞彩官方 10 分钟快照即收盘盘口**（`oddsList[].updateDate/updateTime`），CLV/EV 走免费官方源即可，见 `docs/探针核对报告-v1.1-20260915.md` |

## 3. 已实测的关键事实（全部真实请求验证）

- **07:55 API-Football 的两个纠正（推翻我此前写进文档的结论）**：
  ① 基址是 **`v3.football.api-sports.io`**（我 07:52 误用 `api.api-football.com` 去试，DNS 直接解析失败，白白当成"域名出事"）；
  ② `/leagues` 的过滤器是 **`id=<单个整数>`**，**不是 `idLeague=`** —— 实测 `?id=136&season=2023` → 正常返回（136 = 意甲 **Serie B**，覆盖 `{}`），
     而 `?idLeague=142` 才报 "The idLeague field do not exist"。⇒ **我上一版"免费档完全无法做 id 发现"的结论下重了**：
     免费档能做的是"已知 id 一次确认"，不能做的是"按国家/名称批量搜"（`id=` **不接受逗号列表** ⇒ 扫描要一个 id 一次请求）。
  ③ `?code=CSL&season=2023` → **HTTP 200 但 `response` 为空**（不是错误）⇒ `CSL` 不是它的代码；**继续猜代码不划算**（每次 1 个配额、且空结果无信息）。
  ⇒ 结论不变但理由更正：**中超的 AF leagueId 需要你从 api-football 面板/文档给一个数**（拿到后我 1 个请求确认、当天就能接进采集）。
- **07:54 我自己写错的 SQL 被自己的验收抓到**（第 3 次队长侧规格错，前两次是 2f 的目录口径与 E8 的 FK）：
  DASH1a 的 `backtest_summary` 我写了 `sum(if_clv)`，而 **PostgreSQL 没有 `sum(boolean)`** ⇒ `psycopg.errors.UndefinedFunction`，
  更要紧的是 `_fetch()` 那层"任何异常降级成 `[]`"**把这个错吞成了"面板没数据"** —— 这正是我担心的静默失效模式。
  ⇒ 修法（进 `P0-DASH1b` ①）：`count(*) filter (where if_clv)`；并**保留**降级但额外 `logger.error("jc_view 面板降级 …")` 让它在日志里必须可见。
  ⇒ **教训**：`except Exception → 返回空` 这种"页面不 5xx"的写法，必须配一条**面板级健康信号**，否则我写的验收只会看到"空但没错"。

- football-data.org 免费：FINISHED 场次含 `score.halfTime`（英超 380/380 ✅）→ 半全场模型有粮
- API-Football：/odds?date 免费有盘（当日 10 场 ✅）；season 限 2022–2024；100 req/天
- The Odds API：免费 500 credits/月，全市场（NBA 让分/大小够用；CBA 盘口覆盖待 probe）
- webapi.sporttery.cn：**海外 IP 实测被挡**（HTTP 567 + 反爬页）→ 必须国内机采集
- 传统足彩 4 玩法 2026 年在售（官方奖期公告实查）；北单在售但无合法接口（已排除）
- 本 repo 模型输出含：DC 比分矩阵(0-8)、方向星级、大小球 2.5、BTTS、xG、26维ML特征、蒙特卡洛
- 仓库现状：scripts/core 4,619 行（复用≈95%）、bball 495、tests 2,605（≈70%保）、web+static 2,231（退役）

### 3.1 本机（NDORACLE）2026-09-15 复测增补
- 代码仓 = `https://github.com/nxz1026/league-predict`；克隆在 `~/league-v2/repo`（origin/main `60e3201`），**工作分支 `v2` 已从 main 建好并 checkout**（本地分支，未推送；建/切分支是队长人工动作，工单里禁 git）
- **测试基线（2026-09-15 四次工单后）**：`python -m pytest tests -q` → **270 passed / 11.5s**（演进 215 → +8 store → +4 quota → +19 derive1 → +20 derive2 → +4 原子性回归锁）；快档 `--ignore=tests/web` → **196 passed / 3.9s**；web 档 74 passed
- ⚠️ 跑测试会真写 tracked 的 `predictions/ai_scores.json`（`tests/web/test_m6_ai_enrich.py`），审 diff 前须 `git restore` 该文件；`.omp-logs/` 已加进 `.gitignore`（**未 commit**）
- 🔴 **重大更正（推翻内核 v1 注释）**：`scripts/core/data/fetch.py:276` 写"免费计划不支持 season 过滤"是**错的**。实测免费档
  `GET /fixtures?league=39&season=2024` → `errors=[]`、`paging.total=1`、**380 场一次返回**、全 FT、**`score.halftime` 380/380 非空**；
  另测 `140/2022`→380 场 HT380、`78/2023`→308 场 HT308。⇒ **五联赛×三赛季全量回填只要 15 次请求**（不是按日抓的 2-3 周），
  且**半场数据一次到位 → P1 halftime 模型（半全场/6场半全场）的数据前提提前解除**。内核那句注释不许改（core 冻结），但所有排期按本条更正走
- 本机直连两源均通（无需代理）：AF `GET /odds?date=2026-09-15` → 200 / 10 场；FD `GET /v4/competitions/PL/matches?season=2024&status=FINISHED` → 380 场、**halfTime 非空 380/380** ✅
- ⚠️ AF 免费档**不回传** `X-RateLimit-Requests-*` 头 → 服务端剩余配额读不到，**`ops.quota_ledger` 本地账本是强制项**；当日真实余额已入账：`api_football 4/100`、`football_data 2/30`（队长手工探测所耗）
- ✅ DB 追加（解回填卡点）：独立 schema **`raw.af_raw` / `raw.fd_raw`**（LOGGED + `params_hash` 幂等唯一键 + `league_ing` 只 INSERT/SELECT，TRUNCATE/UPDATE/DELETE 实测全拒）
- OMP 派工器冒烟通过：SMOKE1 端到端 26s / 1 次成功 / 哨兵齐 / `git status` 空（详见 OMP-SKILL §1、§7）
- ✅ **篮彩 key 已补（2026-09-15 人工）**：变量名 **`NBA_API_KEY`**，位置在 **`/home/ubuntu/.env`（机器级）**，
  ⚠️ 两处不一致必须记住：① v1 代码读的是 `ODDS_API_KEY`（`scripts/bball/run.py:113`）；② `core/constants.py` 的 dotenv 只加载 `repo/.env`。
  ⇒ 开篮彩工单时：把 `NBA_API_KEY` 以 **repo/.env 追加**（600、已 gitignore，值不外泄）或让新代码优先读 `NBA_API_KEY`（回落 `ODDS_API_KEY`），二选一，别改 v1 冻结文件

## 4. 文件地图
```
~/league-v2/
  README.md                ← 本文件（会话压缩+决策）
  OMP-SKILL.md             ← OMP 派工操作技能（本机工单怎么发、怎么验收）
  docs/
    玩法覆盖分析报告-20260915.md          （v1 全量分析）
    玩法覆盖分析报告-20260915-v2增补.md   （范围/架构变更）
    框架设计-全玩法覆盖-v2-20260915.md    （40 新文件模块图+配额预算+工单拆分）
    实施计划-全玩法覆盖-20260915.md       （P0–P4 排期+每阶段验收）
    国内采集机实施文档-v1.md              （给国内 AI 的 Prompt，probe-first）
    db/schema_v2_draft.sql               （PG18 六层 schema 设计草案，含 … 伪代码，不可直接跑）
    db/infra_p0_1_roles_db.sql           （✅ 2026-09-15 已执行：角色/表空间/建库）
    db/infra_p0_2_schemas.sql            （✅ 2026-09-15 已执行：ref/stg/ops 14 表 + 最小权限）
    db/infra_p0_3_raw_api.sql            （✅ 2026-09-15 已执行：独立 raw schema，LOGGED 原始落地块，回填解耦用）
    db/infra_p0_4_fact_core.sql          （✅ 2026-09-15 已执行：fact.fixture + fact.fixture_result + v_result_conflict + ref.league seed）
    db/pg_hba_league_snippet.txt         （✅ 已插入并 reload：league 三角色只许连 league 库）
    infra/README-infra.md                （P0-infra 交付说明 + 复跑验收命令 + 三条 DB 红线 + §5 raw 块）
    infra/league-rsync-shell.sh          （已装 /usr/local/bin：collector 账号 rsync-only 受限 shell）
  repo/                    ← league-predict 克隆（v2 工作区）
    scripts/store/  pg.py upsert_official.py                ← P0-STORE1（OMP 交付，已验收）
    scripts/ingest/ collector_pull.py quota.py              ← P0-STORE1/1b（1c 在修事务边界）
    scripts/derive/ grid.py totals.py scores31.py goals4.py
                handicap.py registry.py                    ← P0-DERIVE1/2（OMP 交付，已验收）
    tests/test_{store_idempotency,collector_contract,quota,derive_grid,derive_buckets,derive_handicap,derive_registry}.py
    .omp-logs/               ← 派单日志/哨兵/report（已 gitignore，**已验收单的 .done 不许删**）
  ~/tickets/                 ← 工单正文（P0-STORE1/1b/1c、P0-DERIVE1/2、P0-HYGIENE…）
  ~/bin/omp-ast-check.py     ← 队长机检工具（≤100行/≤50行/≤120列/psycopg越界/DEBUG走私；禁 coder 改）
  ~/bin/league-accept.sh     ← 队长一条龙验收（哨兵→pytest→机检→冻结区自伤→PG 留痕；禁 coder 改）
```

## 5. 机器拓扑
| 机器 | 主机名 | 角色 |
|---|---|---|
| 海外 DSH（设计会话） | nd-dsh | 设计/调度端，会话来源 |
| **本机（操作端）** | NDORACLE | OMP coder + PostgreSQL 18.6 + 未来的 ingest/nginx |
| mimir | HermesND | ~~旧部署机~~ **2026-09-15 起退出流程：不取 key、不派工、不部署** |

**开工前的 key（已改为本机，2026-09-15 实测落地）**：数据源 key 在**本机 `/home/ubuntu/.env`**（不再 `ssh mimir`）。
注意变量名要对齐代码：`/home/ubuntu/.env` 里是 `API_FOOTBALL_API_KEY`，而 `scripts/core` 读的是 **`API_FOOTBALL_KEY`**；
已按代码名写入 `~/league-v2/repo/.env`（chmod 600，`.gitignore` 已忽略），`FOOTBALL_DATA_API_KEY` 同名照搬。
**缺口**：`ODDS_API_KEY`（The Odds API / 篮彩）在 `/home/ubuntu/.env` 里**不存在**，需人工补。
不要在工单/日志里回显任何 key。详见 `OMP-SKILL.md §8`。

## 5.9 用户 2026-09-16 06:35 定的三件事（覆盖此前我的"要不要扩联赛"提问）
- **D10 联赛范围＝封闭清单，不许自行扩张**：
  · 竞彩足球：**英超 / 西甲 / 意甲 / 德甲 / 法甲 / 中超**（前 5 个已有；**新增 = 中超**，AF 需查 leagueId，配额按 D9 省着用）
  · 竞彩篮球：**NBA / CBA**（⇒ 篮彩从"§5.5 未冻结"转正：要真包、要 `fact.jbq_*` DDL、要解析层）
  · 数字彩：**大乐透 / 排列3 / 排列5 / 七星彩** ⇒ 只做开奖对照（`fact.lottery_draw` 已覆盖），**红线不变：不进任何模型、不预测**
  ⇒ 英冠 / 荷甲 / 英联赛杯 / 解放者杯 / 亚冠精英 **明确不做**（夜里我提的"扩联赛"问题作废）。
- **D11 交付界面 = dashboard**：用户明说"等 dashboard 做了我再看" ⇒ 后续验收产物要能在页面上看（`web/` 是冻结区，
  开 DASH 单时队长须在验收脚本里对该单**显式放行 `web/` + `static/`**，其余冻结规则不动）。
- **D12 模型**：用户明确"**目前都派工给 Agnes**" ⇒ 不换默认模型；工单一律用"**禁止阅读 + 材料全内联 + 单次长超时**"格式（§9-52）。

## 6. 下一步（按序，均待你放行）
0. ~~取 key~~ ✅ **已完成（改为本机）**：`~/league-v2/repo/.env` 已按代码变量名落地 AF+FD 两把 key（chmod 600，git 干净）；OMP 派工链路冒烟 ✅
1. ~~环境~~ ✅ **P0-env 已完成（2026-09-15）**：旧写法 `python3 -m venv` 在本机**跑不通**（Ubuntu 26.04 缺 python3-venv/ensurepip），改用 `uv venv ~/.venvs/league --python 3.14` + `uv pip install --python ~/.venvs/league/bin/python -r requirements.txt -r requirements-web.txt pip`；基线 **215 passed / 11.7s**（已填死，不再是"≈"），快档 141 passed；`v2` 分支已建并 checkout
2. ~~P0-infra~~ ✅ **已完成（2026-09-15，队长本机自干，非工单）**：
   - PG：`league` 库 + 三角色 `league_ing/app/ro`（最小权限，实测矩阵过）+ 表空间 `ts_snap/ts_stg`；schema **只建 ref(4表)/stg(7表,UNLOGGED)/ops(3表)**，fact/model/analysis 与 `v.market_full` 等国家内机契约冻结（草案里的 `…` 伪代码本轮补齐为 `line/src_hash/loaded_at/src_file` 四列，新增 `ops.file_arrival` 供新鲜度报警）。可执行版：`docs/db/infra_p0_1_roles_db.sql` + `docs/db/infra_p0_2_schemas.sql`（原 `schema_v2_draft.sql` 保留为设计草案，不可直接跑）
   - 跨库隔离走 **pg_hba**（不是对象级 REVOKE——撤不掉 PUBLIC 的隐式 CONNECT）：`docs/db/pg_hba_league_snippet.txt`，原文件备份 `pg_hba.conf.bak-p0infra`；**没动 `longkonglong`（在跑的另一项目）**
   - OS：账号 `league`（key-only）+ `/srv/league-staging/{incoming,done,bad}`；受限 shell `docs/infra/league-rsync-shell.sh` 已装到 `/usr/local/bin/league-rsync-shell`；**sshd_config 未改**（用 login shell + authorized_keys 的 `command=` 限制，风险更低）
   - E2E 实测：一次性密钥跑通 `rsync JSONL+.done → incoming`，同时交互 shell / scp / 越界写 / `;` `|` `$()` 走私全被拒；密钥与测试文件已清（详单 `docs/infra/README-infra.md`）
   - ⚠️ 仍待：**国内机 pubkey**（拿到后追加 `command=...,restrict` 到 `/srv/league-staging/.ssh/authorized_keys`，现 0 字节）+ 新鲜度监控接 Dashboard（要写代码，走工单）
3. **国内机**：把 docs/国内采集机实施文档-v1.md 交给国内 AI → ✅ **probe_pack 已回传并核对、契约冻结 v1.1**（13 次探针全 200）→ ✅ **15:30Z 他们已按 `回传-契约v1.1指令.md` 的 5 处必改全部实现并上线**，3 批真包 450 行已在 `oracle:/srv/league-staging/incoming/cn-collector/`（＝本机目录，我直读）→ ✅ 队长验收 **PASS**、契约升 **v1.2** → ▶ **待人工转达 `docs/回传-验收v1.1第1批.md`**（B 节 4 项必改 + E 节 10 行官网核对表，我这 IP 被 567 挡）→ P0-COLLECT2 放行（真包驱动）
4. ~~store 层~~ ✅ **P0-STORE1 + 1b 已完成（2026-09-15，OMP 工单，各 try1 一发过）**：
   - 交付：`scripts/store/pg.py`(56) `upsert_official.py`(89)、`scripts/ingest/collector_pull.py`(99) `quota.py`(54)、`tests/test_store_idempotency.py`(92) `test_collector_contract.py`(100) `test_quota.py`(84)
   - 链路：`incoming/<host>/<topic>/<file>.jsonl + .done` → 逐行校验（非法行进 `ops.ingest_log.rejected` 不静默吞）→ `stg.*`（`ON CONFLICT (src_hash) DO NOTHING` 幂等）→ `ops.ingest_log` + `ops.file_arrival` → 归档 `done/`、`bad/`、未知 topic 进 `bad/_unknown/`
   - **逐文件独立事务 + 先 commit 后移文件**（1b 修的真缺陷：批量共用事务时"文件已 move 而 DB 回滚"＝无痕丢数据）
   - 基线随之 **215→227 passed**（全量 11.3s）/ **141→153**（快档）；`league_ing` 无 DELETE ⇒ 测试一律单事务收尾 ROLLBACK，实测 14 表零留痕
   - 队长工具（禁 coder 改，发单前留 md5 快照）：`~/bin/omp-ast-check.py`（≤100 行/≤50 行/≤120 列/psycopg 越界/DEBUG 走私，AST 实现）、`~/bin/league-accept.sh <TAG> <路径…>`（哨兵→pytest→机检→冻结区自伤→PG 留痕 一条龙）
   - **遗留（P0-STORE1c 待发）**：`main()` 的"提交后才归档"目前**碰巧**成立——它依赖"进内层 `conn.transaction()` 时连接仍是 IDLE"；一旦有人在 run() 前先执行一条语句（如 `pg_advisory_lock` 防并发），内层退化成 SAVEPOINT，kill 时照样丢数据。1c = 去掉 `write_conn` 外层 + IDLE 断言 + 零 DB 的 stub 顺序回归锁（工单已写好 `~/tickets/P0-STORE1c.txt`）
   - **已接受的契约偏离**：幂等键 `src_hash` 由装载侧按规范化对象重算（64 位 hex），不采信采集机原始字节 sha256（细节与理由见 OMP-SKILL.md §9-18）→ 契约 v1.1 冻结时回头统一
5. **P0-DERIVE**（工单）：derive 纯函数层，**零 DB / 零网络 / 零新依赖**（本机没装 numpy，内核本身纯 stdlib，保持一致）
   - ✅ **P0-DERIVE1 已完成（2026-09-15，OMP 工单，try1 一发过，9 分钟）**：`scripts/derive/grid.py`(42) `totals.py`(15) `scores31.py`(41) `goals4.py`(16) + `tests/test_derive_grid.py`(77) `test_derive_buckets.py`(100) → 基线 **227→246 passed**
     · `grid.dc_grid()` 包内核私有 `_dc_pmf_grid` 并**强制归一化**（内核 9×9 原始和 0.999972083662318，不归一每场漏 2.8e-5 概率；`dixon_coles_match_probs()` 因 round(4)+top12 截断**不可当派生输入**）
     · 玩法口径钉死：总进球 8 档（`"0"…"6","7+"`，`7+`=h+a≥7 全并）；**竞彩官方 31 比分**=12 命名胜+`胜其它`/4 命名平+`平其它`/12 命名负+`负其它`；`goals4` 给两队各自 8 档（行和/列和）
     · 测试质量高：81 格**逐格反查覆盖性**用两组互不相同的权重 + 测试内**独立重写**一份官方映射对账（不是"拿实现验实现"）；`rho=0 ⇔ 独立泊松外积` 这条**不依赖内核**的 oracle 已落地（实测最大偏差 0.0）
     · **队长第三路径复算通过**：我自己另写一份 tau/pmf，`totals` 8 档与 `scores31` 31 桶与 derive 输出**逐值相等、最大偏差 0.0**
     · 遗留小 nit（**不追，记档**）：`grid._validate` 把 `p<=0` 一律判非法 ⇒ 含**结构性 0 格**的稀疏矩阵过不了 `renormalize`；DC 实际永不为 0 故无影响，等 P1-HALFTIME 顺手动 derive 时一并放宽（改行为要连他们那条"零也被拒"的测试一起改，不值一单）
   - ✅ **P0-DERIVE2 已完成（2026-09-15，OMP 工单，try1 一发过，3 分钟）**：`scripts/derive/handicap.py`(32) `registry.py`(37) + 两个测试（71/74 行）→ 基线 **246→266 passed**（快档 **192**）
     · `handicap.probs(grid,line)`：线加**主队**（`line<0`＝主让，与竞彩"主-1"同口径）；`line` 强校验 `int`（`1.0`/`True` 一律 TypeError，bool 不许当 1 混进来）
     · `registry` 只注册 `had/hhad/crs/ttg/jqc` 五键；**`haf` 缺席即 KeyError**（"未实现，勿用 0.0 占位"），`hhad` 缺 line → TypeError（不许悄悄当 0）
     · 队长独立复算**逐值相等**：`dc_grid(1.5,0.8,0.2,8)` 的 line 0/-1/-2/+1 主胜 = `0.562667 / 0.277783 / 0.112401 / 0.775771`（与工单黄金值偏差 0）；结构不变式 `home(+1)=home₀+draw₀`、`away(-1)=away₀+draw₀` 实测偏差 0.0
   - `halftime.py` 属 **P1**（要等 FD halfTime 回填与 HT 模型），本阶段不建
6. **P0-backfill**（✅ 2026-09-15 真数据已入库：`raw` 两块共 25 个成功块）
   - ✅ **原"fact 层未建"卡点已解**：独立 schema `raw.af_raw` / `raw.fd_raw`（LOGGED + `params_hash` 幂等 + 只追加）
     · 幂等键已从表级 `UNIQUE(params_hash)` 改为 **partial unique `WHERE http_status=200`**（实测：同 hash 连插 3 条 429 全留证、200 只留 1 条）
       ——因为"失败也落块 + 表级唯一"会让一次 429 **永久毒化**该请求；改完后旧写法 `ON CONFLICT (params_hash) DO NOTHING` 当场抛 `InvalidColumnReference`，故必须配套改代码（见下）
   - ✅ **P0-BACKFILL1 已验收**（`api_get.py`90 / `run_backfill.py`88 / 两个测试 99+100 行）：281 passed / 207 快档 / 机检 0 违规；
     并用**代理绊线**（`https_proxy` 指向死端口仍 11 passed）证明测试**零真联网**；`--plan` 正确打印 30 条计划 + 两源剩余配额
   - 🔴 **队长真跑暴露 P0（这是本次流程最有价值的一次执行）**：`--execute --source af --limit 20` 发出 15 条、日志逐条"落块 HTTP 200"×10 + `HTTP 429`×5，
     **结果 `raw.af_raw` 0 行、`ops.quota_ledger` 0 格** —— 15 次真请求无痕蒸发。PQtrace 取证：`BEGIN×2 SAVEPOINT×4 RELEASE×4 COMMIT×0`
     · 根因＝**§9-19 那个坑的第二实例**：`pg.connect()` 非 autocommit，`cached()`/`remaining()` 的第一条 SELECT 已开隐式事务
       ⇒ 之后的 `with conn.transaction():` **静默降级成 SAVEPOINT** ⇒ 永不提交 ⇒ 关连接全回滚
     · 次因＝**AF 免费档除 100/天还有 10/分钟**（连发第 11 条起全 429），编排层没有跨源限速、也没有"429 即收工"
     · 账本已诚实补记：无痕跑掉的 10 次成功请求手工入账 ⇒ 今日 `api_football 14/100`、`football_data 2/30`
     · 教训（已写进 OMP-SKILL §9-25/26/27）：**STORE1c 明明已经给 `collector_pull` 装了 IDLE 守卫，但没升格成全局不变式**；
       以及 **CLI 写路径的验收必须含一次真跑 + "落库行数 == 发出请求数"对账**，光看单测绿＝没验
   - ✅ **P0-BACKFILL1b 已交付并验收**（09:52 交付，try1，286 passed/212 快档/机检 0 违规）：
     `main()` 里 `conn.autocommit = True` + `fetch()` 前置守卫（**非 autocommit 直调 → RuntimeError，假 transport 计数 0，一次请求都不发**）、
     `fetch` 返回 `(status, body)`、两源统一 `PAUSE_S=7`、429 即收工、收尾自审「发出 N / 落块 M / 命中 K」
     · **协议级复证**（同一 PQtrace 假 transport 夹具，跑完手工清 `season=2099` 取证行）：修复前 `BEGIN×2 SAVEPOINT×4 RELEASE×4 COMMIT×0`
       → 修复后 `BEGIN×4 SAVEPOINT×0 RELEASE×0 COMMIT×4`，且关连接后重连仍能看到 2 行 ⇒ **从"碰巧"变成"结构上不可能"**
   - ✅ **真回填已跑完（队长亲自执行，两源逐条对账）**：AF **15/15 全 200**（7s 限速后 429 归零），FD 10/15 200 + 5 个 403
     · **配额账本与落块数完全吻合**：`api_football 29/100`（14 手工探测+15）、`football_data 17/30`（2+15）⇒ "配额花了没落块"这类事故从此可被 `--plan`+账本双查
     · **数据规模（这是 P0 阶段真正的产出）**：AF **5341 场完赛，`score.halftime` 缺失 0 场**；FD 3502 场 `FINISHED`，`score.halfTime` 也 0 缺失
       → 五联赛 × 2022/2023/2024 全覆盖（2022 只有 AF 一个源：FD 免费档 `season=2022` 直接 **403 errorCode 403**，只给近两季）
       ⇒ **P1 半全场/6场半全场的模型数据前提当场成立**，不用再等任何外部条件
     · 字段大小写陷阱（已写进 FACT1 工单）：AF `halftime/fulltime` 全小写 + 状态 `FT/NS`；FD `halfTime/fullTime` 驼峰 + 状态 `FINISHED/SCHEDULED`；
       FD 顶层数组键是 **`matches`**（不是 `response`）；AF 是 `response`
   - ✅ **P0-FACT1 已交付**（10:17，try2——try1 被 OMP 侧 "Streaming edit preview failed" 吞掉，见 §9-30）：
     `store/parse_api.py` `upsert_fixtures.py` `upsert_results.py` `query.py` + 2 测试；真报文核字段、I1 在真数据上三连幂等、未翻译队名如实报 63/164
   - 🔴 **但队长复核查出"重复插场"**：**我上一单工单自相矛盾**（要求 FD id 进 `source_ids`，同时又写"本单不做跨源对齐"）
     ⇒ coder 只能把 3504 条 FD 场次各插成一行 fixture（**它自己在 report §4 如实交代了**），`fact.fixture` 一度 8845 行＝同一批比赛两份副本
     ⇒ 已用 postgres 权限清掉 FD-only 行（`DELETE` 3504 + 对应 result 3504），现回到 **5341 场纯 AF 权威 id**；
     `league_ing` 对 fact/ref 无 DELETE ⇒ "宁可不插、不可插错"从此写进铁律
   - ▶ **P0-FACT2 已备单待派**（`~/tickets/P0-FACT2.txt`）：`store/align.py`（(league_key,kickoff) 精确等值 + 队名规范化，
     主客互换/歧义一律不算命中）+ FD 不再建 fixture（只 `UPDATE source_ids`）+ 未对齐只进 `ops.ingest_log.rejected` + A1~A7 断言（**全部相对量，禁止假设表空**）
   - ✅ **P0-FACT2 已交付**（10:55，308 passed）：`store/align.py` 纯函数对齐 + FD 不再插场 + 未对齐只进 `ops.ingest_log.rejected`
     ⇒ 真跑：**`fact.fixture` 仍 5341 行**（A1 立住了），但**对齐率只有 12.9%**（453/3504）
   - 🔴 **对齐率低的根因是我工单里的两条错误指令**（coder 照做，数据不会骗人）：
     ① "同 (league, 开球时刻) 出现两条候选就判歧义" —— 我以为是病理现象，**其实一轮比赛集中开球是常态**（法甲 20:00 九场齐开）⇒ 1299 场被误杀；
     ② "队名 `normalize_team` 必须**相等**" —— 两源是**短名 vs 长名**（AF "Newcastle" / FD "Newcastle United FC"）⇒ 1730 场被误杀
   - ✅ **P0-FACT3 已交付**（11:10）：唯一性从"键唯一"改成**"配对唯一"**（候选列表 + token 子集 + 显式同义表 `TEAM_SYNONYMS`，禁编辑距离）
     ⇒ 真跑：**对齐率 12.9% → 99.3%**（3481/3504，未对齐 23 场全是两源开球时刻真不一致的 `no_time`）；`fact.fixture` 仍 5341 ✅
   - 🎯 **多源核对首次真正兑现**：3481 场双源里 **2 场比分分歧**，两场都花 AF `/fixtures/events` 逐事件**当场裁定 AF 正确**
     （佛罗伦萨 3-0 国米：进球 59/68/89 ⇒ HT 必 0:0，FD 把全场抄进半场；柏林联合：进球 23'/33' ⇒ FT 1:1，FD 记成 0:2）
     ⇒ 标注口径已写进设计文档 **§6**（fixture 身份与比分/半场一律 AF 权威，FD 只交叉核对，分歧率 0.06% 必须可列出）
   - 🔴 **同类 bug 第三次发作**（这次在 fact 测试里）：`test_upsert_from_raw.py` 断言 `unmatched_fd(conn) == []`，
     而 `unmatched_fd` 读的是"最新一条留痕"⇒ 我真跑生产装载落下 3051 条真实未对齐后，该用例当场转红（**派单时表是空的，"碰巧"绿**）
     ⇒ 深层病因：**`run()` 不把"本批未对齐数"返回，测试被迫读全局状态**；已派 **P0-FACT3b**（作用域过滤 + 返回值带计数 + 专钉此坑的回归用例）
   - ✅ **P0-MODEL1 已交付**（11:53，try1，18 分钟）：`scripts/model/fit.py`（固定点拟合攻防强度，纯函数）+ `walk.py`（**上一季拟合 → 当季预测**，防泄漏写成守卫）+ 12 条用例
     · 黄金值我先用**独立参考实现**算好再写进工单：黄金 1 两队对称（atk=1/def=0.5/γ=1）；**黄金 2 是方向敏感往返试验**
       （用已知 atk/def/γ 生成 λ 当"进球数"喂回拟合 ⇒ 必须原样恢复；γ 放错分母在对称数据上**完全看不出来**，只有这种往返能抓到）；
       真数据用**一阶条件** `Σλ主 == Σ实际主队进球`（实测差 1.14e-13）
     · coder 三处**如实申报的偏差**都被我复核过：γ 不进迭代（进迭代则黄金 2 收敛到 1.0、黄金 1 发散）；停机阈值从 1e-12 收到 1e-15；
       `jqc` 因 PK 只有 `(run,fixture,play,option)` 而只落了主队侧 8 档（客队边际可从已存的 9×9 矩阵重算，无信息损失）⇒ 补两侧需加侧别前缀，记进 MODEL2
  - 🔴 **真跑 10 个 walk run 抓到身份键的 P0 级病**（测试全绿也看不见，因为测试里的队名是我自己写的常量）：
     `ref.team` 唯一键是 `(sport, name_cn)`，而 `name_cn = to_cn(源队名串)` —— **AF 跨赛季改队名拼写**（`Vfl Bochum`→`VfL Bochum`、`Bayern Munich`→`Bayern München`）
     + **to_cn 换串就翻不出来** ⇒ 同一家俱乐部（AF id 完全相同）插成两行（157 拜仁 / 163 门兴 / 176 波鸿 / 180 海登海姆各两行）
     ⇒ 拟合时"上一季没这支队" ⇒ **德甲 2024 季 306 场只写出 132 场预测（跳过 57%）**，其余联赛跳过的是真升班马
     ⇒ 队长已执行 `docs/db/infra_p0_6_team_identity.sql`：合并 4 家重复（164→160 行，原貌备份 `ref.team_pre_p0_6_backup`、映射 `ref.team_merge_map`）
       + 新增**存储生成列** `af_id`/`fd_id`（从 aliases 生成）+ `partial unique (sport, af_id)` / `(sport, fd_id)` ⇒ 身份从此认 id，`name_cn` 退回展示用
     ⇒ 索引一上，`tests -q` 当场 1 红（`test_align` 两个文件共用哨兵 AF team id 却给不同队名 ⇒ 老"按 name upsert"插第二行）——
       **正是索引该抓的错**；已派 **P0-TEAMKEY1** 改"按源 id 认队"（§9-27 的规矩：改 DDL 必须同一轮带代码单）
     ⚠️ 我自己写 DDL 时也炸了两次，都已把教训写进 SQL 注释：① `aliases ->> g.src_id` 把值当键名用 ⇒ 永远连不上（`SELECT 0`）；
        ② **`jsonb_object_agg` 在空集上返回 NULL，`jsonb || NULL` 也是 NULL ⇒ 把 `aliases` 整个洗成 null**（非空约束救了我，事务回滚，库里零污染）
- ✅ **P0-TEAMKEY1 已交付并收尾**（13:20Z，try1，12 分钟；`ff7651f` 已推 origin/v2）：认队改成**源 id 优先**（新 `scripts/store/team_identity.py`），
    `392 passed / 零 SKIPPED`，机检 0 违规。队长收尾（`docs/db/infra_p0_7_fd_id_move.sql`）：按"两源同一场锚点"把 **38 个 FD 队 id 从孤儿行搬回证据所属的 AF 行**
    （`raw.fd_raw` 的 match → `fact.fixture.source_ids->>'football_data'` → 该场 home/away_team_id；证据覆盖 110 个 FD 队 id，其中 72 个本就挂对、38 个被 FACT1 时代的孤儿行占着，
    一 id 指多行的冲突 **0** ⇒ 才敢搬）⇒ `ref.team` **122 行，行行有 af_id，孤儿 0、重复 0**。样例：`fd_id 82`「赫塔菲」→ AF 行「赫塔费」（**一个字的音译差**，靠 id 而不是靠名字对上的）。
  - 🔴 **真跑又抓出 v1 内核一个潜伏缺陷**（P0-MODEL2 在治）：`core/model/poisson.py::tau_correction` 的 τ(1,1)=1−ρ·λ_h·λ_a（ρ=`DC_RHO`=0.2 是**正值**，与 Dixon-Coles 原文的参数化不同），
    λ_h·λ_a ≥ 5 时 τ 变负 ⇒ 内核 **warn 后 `max(0.0, τ)`** ⇒ P(1:1) 变成**精确 0**；v2 的 `derive/grid.py::renormalize` 要求每格 >0 ⇒ bundesliga 2024 真跑当场 `ValueError`。
    现场只有 **2/2562 场 = 0.08%**（拜仁 3.78 λ vs 霍芬海姆）；v1 自己的消费端用 `p > 0.0001` **静默丢格**，所以这个洞在 v1 里从来不响。
    ⇒ 处置：**不动冻结内核**，在 v2 包装层做 **ρ 可达域收缩** `rho_eff = min(rho, (1-floor)/(λ_hλ_a))`（不触发时逐格与原来相等），并把 `rho_eff` 记进 `pred_fixture.features`。
  - ✅ **国内采集机探针包已核对，§5 契约冻结到 v1.1**（`docs/探针核对报告-v1.1-20260915.md` + 实施文档 §5 全量重写）：13 次探针**全 HTTP 200、无一被 WAF 拦**。四条当场解锁：
    ① **`hhad` 让球线在竞彩盘口里**（`hhad.goalLine="-1"`/`goalLineValue="-1.00"`）⇒ 让球玩法可算；
    ② **盘口时间序列免费**（每场 `oddsList[]` 自带 `updateDate/updateTime`，10 分钟快照即成序列）⇒ **CLV/EV 不用花 The Odds API 配额**；
    ③ **官方半场比分**在 `jczq_result.sectionsNo1`（全场是 `sectionsNo999`）⇒ 判奖不再依赖 AF 的 halftime；
    ④ **传统足彩四个玩法号定死**：`90`=胜负游戏(14场)、`900129`=**任选9场（候选 14 场，不是只给 9 场）**、`98`=**6场半全场**（`haf` 的数据源！）、`94`=4场进球(4场)；
       且**期号跨玩法会重号** ⇒ 幂等键必须 `(game_num, issue_no)` 两列。
    另有两条"必须按官方原样存"的取证：`crs` 块去旗标 **31 个选项与 `derive/scores31.py` 的 `KEYS` 逐键相等**（官方口径零偏差）；
    `jc_issue_result` 的 `result` 三玩法形态不同（`"3"` / `"3＋,1"`（全角加号）/ `"3,3"` 半场,全场）⇒ **判奖用官方串，不自己重算**。
    ⚠️ 未冻结一项：`jclq_offer` 探针窗口内**篮彩确实无开售**（NBA/CBA 休赛期，`value` 只有 `vtoolsConfig`），10 月开售窗口复探。
   - ✅ **P0-MODEL2 已交付并验收**（13:46Z；try1 中途死于 OMP 流式编辑 §9-30，resilient 包装自动起 try2 完成；`3edf03a` 已推）：
     ① `derive/grid.py` 新增 `admissible_rho(λ_h,λ_a,rho,floor=1e-3) = min(rho, (1-floor)/(λ_hλ_a))`，`dc_grid` 内部先收缩再喂内核，
        `_validate` 严格性原样保留，**冻结内核不动**；② 未见队（当季升班马）改走 **atk=def=1.0 联盟平均先验**（不再整场跳过），
        两侧来源写进 `pred_fixture.features.fallback`，run 返回值与 params 加 `n_fallback`（已知偏差：升班马弱于平均 ⇒ 主场 λ 偏高）；
     ③ `jqc` 每队侧 0/1/2/**3+** 四档（`goals4` 的 '3'+'4' 归并），`option_code` 加 `h:`/`a:` 侧别前缀 ⇒ 解掉 MODEL1 申报的"两侧同键被 PK 静默吞"偏差。
     ⇒ 队长独立清空重跑 10 run（run_id 264-273）：**写 3504（原 2452）｜ 跳 0（原 1052）｜ 兜底 942 ｜ ρ 收缩 2（都是拜仁）｜
        `pred_market` 175200 = 3504×(3+31+8+8)**，每场选项数 crs31/had3/ttg8/jqc8，`n_haf_illegal` 0。
   - ✅ **P0-BACKTEST1 已交付并验收**（14:00Z try1；`8a45f0f` 已推）：`model/backtest.py`（多类 Brier ＝ 组内全选项 Σ(p−o)²、
        eps 显式回显的 log-loss、argmax 命中）写 `analysis.backtest_market`，**`clv` 全表 NULL**（没有收盘源就不造假，§2-D2 的 CLV 等国内机快照）。
        因 `query.py` 撞 100 行上限，三个只读函数原样搬进新 `store/selfcheck.py` ⇒ 队长逐字核对＝搬移零改动，16 处测试改动只是 import 路径、断言零放宽。
     ⇒ **第一批真实模型数字（队长独立重算，全量口径含 942 场兜底）**：
        had brier 0.6270 / ll 1.0444 / hit 0.4772 ｜ crs 0.9405 / 2.9963 / 0.1019 ｜ ttg 0.8350 / 1.8974 / 0.2012 ｜ jqc(按侧) 0.7268 / 1.3378 / 0.3399
     ⇒ **结论（写死，防止以后自己美化）：判别力是实的（hit 全面远超随机），但概率标定只剩 3~6% 优势**（Brier/ll 离均匀基线很近）
        ⇒ 现在这些 p **不许直接进 EV/Kelly**；下一单 **P0-CALIB1**（工单已备 `~/tickets/P0-CALIB1.txt`：可靠性分箱 + ECE + leave-one-run-out 温度缩放，禁在同一批数据上又拟合又报告）。
        分组对照：四玩法**兜底组全部差于拟合组**（had −4.72pp、jqc −3.87pp、crs −0.87pp、ttg −0.66pp）。基线 **405 passed**。
     🔴 验收抓到一次**报告口径病**：coder 报告 §1 的四个 hit_rate 用的是**拟合场分组**（2412/3504），全量低 1.3pp ⇒ 代码没错、是标题挑了组，
        已写 OMP-SKILL **§9-37**（对外报的单一数字必须先给全量，分组维度越多越容易无意中挑出好看的那组）。
   - ✅ **P0-CONFIG1 已交付并验收**（14:18Z try1；`e02c304` 已推）：把用户决定 **D9「功能留着、默认关闭」** 落成代码——新 `scripts/config.py`（97 行，零依赖）
     · 默认表 `api_football on/100`、`football_data on/30`、**`odds_api off/0/paid/key=NBA_API_KEY`**；`LEAGUE_SOURCE_<SRC>` / `LEAGUE_QUOTA_CAP_<SRC>` 可覆盖，
      **非法值 ValueError 不猜**；`spend_allowed()` 的报错点名"是哪个 env 变量说了算"
     · `spend_allowed` 是 `api_get.fetch()` 的**函数第一句**（早于缓存/key/任何写库）⇒ 真库实测关闭态 **`raw 17→17`、`ledger 2→2 行`、今日 `used 31→31`**（零副作用）
     · `quota.charge/remaining` 的 cap 缺省不再写死 100，改从 config 取（补掉"忘传就按 100 烧"）；`--plan` 顶部打印策略表；新增 `.env.example`（无真 key，`.env` 仍未入库）
     · coder 反过来纠了我两处工单错误 ⇒ 见 **§9-38**（派单前对新文件路径做三项预检：同名 / 我自己的冻结正则 / CLI 的 `PYTHONPATH=scripts` 跑法）。基线 **416 passed**
   - ✅ **契约 v1.1 的真实测试夹具已入库**（`50ec8aa`）：`tests/fixtures/collector_v11/*.jsonl`（77 行，由 `docs/db/make_collector_fixtures.py` 从探针包真实响应生成，
        payload 与官方**逐字节同形**：含 `取消` / `3＋,1` 全角加号 / `"12,387"` / `"---"` / `"国  安"` 全角空格 / `lotterySaleEndtime` 少字母拼写）
     ⇒ 生成时顺带三处修正/取证：① **§5.0 勘误**（真实 P0001 失败体**有** `value` 键、值为 `null`；产出不便 ⇒ 不升版本号）；
        ② **补判空口径**（`errorCode="0"` 且 `value={}` 是"成功但空"⇒ 按 §7 产 `.empty`，既不产数据行也不产 error 行）；
        ③ `crs` 块结构精确钉死 = **66 键**（31 选项〔28 具体比分 + `s1sh/s1sd/s1sa`〕× 2 个 `*f` 旗标 + 4 元键）；7星彩 `stakeAmount="---"` 反过来证明"金额一律字符串"是对的
   - 🔴 **P0-COLLECT1 已交付但被拒收（14:52Z try1，19 分钟）**：功能全对——`426 passed`（+10 用例）、
        T2 实测 `fact.jc_*` 八表**仍全 0 行**（本单一行都不该写 fact）、`src_hash` 篡改一行即进 `rejected`、`kind=error` 行确实落 stg、
        逐条对我给的夹具期望值复算一致（crs 66 键、hhad 线 `("-1",-1.00)×6`、2 行"取消"、期号重号证据、`3＋,1` 全角未被动过）。
        **拒收的唯一原因是硬红线**：`parse_collector.py` 234 行、`test_collector_contract.py` 121、`test_parse_collector.py` 149（>100）
        ——无函数超限、无 print、无 psycopg 越界、无禁依赖；coder 在报告 §4 **主动申报并给出两个选项**（拆分 / 申请例外授权放宽）。
     ⇒ **队长裁决：不放红线**（D7 是用户确认的硬约束），走**纯机械拆分单 P0-COLLECT1b**（`~/tickets/P0-COLLECT1b.txt`，**待用户放行**）：
        逐字搬移禁改逻辑、import 单向、测试语义零放宽、拆完必须仍 426 passed 且 `fact.jc_*` 全 0。
     ⇒ 同一份报告 §2 老实列出**契约 §5 有 5 处"夹具无法证实 / 无落点"**（它没自行扩契约，这条纪律值回来了），队长逐条裁决：
        ① `jclq_offer` 未冻结 ⇒ 解析层直接 `raise` 点名 §5.5，**维持**（等 10 月复探）；
        ② `jclq_result` 形态已冻结但**没有篮球落点表** ⇒ 裁"暂不建表、停留 stg"，但注意 **stg 是 UNLOGGED，重启即空**
           ⇒ 重放来源是 `done/` 里归档的原始 JSONL（这条已写进裁决，别误以为 stg 是持久层）；
        ③ 我上一版夹具**用白名单裁掉了官方键** ⇒ coder 无法证实"不落的那几个列表"——**是我的错不是它的错**，
           已把生成器改成"保留官方全部非玩法键"（40 键/场，含 `isHide/isHot/poolList`），重跑它的测试仍 426 passed（`faae5fa` 已推）；
        ④ 传统足彩**明细子表**（`jc_issue_match` / `jc_issue_prize`）确实无 parse 落点 ⇒ **归到 COLLECT2 单里定义**（本单只产 `jc_issue_draw` 主行）；
        ⑤ `jczq_offer` 一个 payload 天然落**两张**表（`jc_match` + `jc_offer`）⇒ **批准第 5 个返回键 `match`**，
           但要求写进 docstring 并有断言钉住（COLLECT2 必须两张表都写，不许只落一半）。
     🔴 **用户 14:35Z 指示：P0-COLLECT2（写 `fact.jc_*` 八表）暂不派**，等国内机按 v1.1 出的正式包到位；`fact` 八表 DDL 已执行（`docs/db/infra_p0_8_jc_tables.sql`）随时可接

    - ✅ **15:02Z 用户切换 OMP 默认模型 → `Agnes/agnes-3.0-flash`**（此前 P0 全部工单由 `deepseek/deepseek-flash` 完成——**证据是逐条数 `~/.omp/agent/sessions/**/*.jsonl` 里的 `model`**，不是读 config；`agent.db.model_usage.last_used_at` 不可信）。
         派工器不带 `-m`，改 config 即换工人 ⇒ 新工人第一单派**零设计自由度**的机械拆分单当试金石（15:10Z 派 P0-COLLECT1b）。Skill 里 LinBlue/DeepSeek-V4-Flash-0.1 的过时描述按用户指示删除，§9-39 新增"工人身份要查证据"。
    - ✅ **15:25Z 国内机 v1.1 首批真包验收完成 → 契约升 v1.2**：`oracle` **就是本机**（NDORACLE），包直接落在
         `/srv/league-staging/incoming/cn-collector/`（我无 league 组成员身份，读它一律 `sg league -c '…'`）。三批 450 行：
         `14-40-02Z` 227 行 / `15-03-45Z` 85 / `15-16-32Z` 138。**结论：PASS 可入库**——
         ① `src_hash` **450/450 复算一致**（官方式），"零清洗"成立；② 外壳 9 键（比 §5.0 冻结的 8 键多 `fetched_at`）；
         ③ 用工作树里的 `parse_line` 跑真包 **450/450 零异常**（对照：夹具 77 行里有 2 行 `jclq_result` 按裁决 `raise`）；
         ④ `jczq_offer` 恰 17 场 × 5 块；`block` 值域 `had/hhad/crs/ttg/hafu`（解析器已把 `hafu`→DDL 的 `haf`，**没有 CHECK 冲突**，我一度以为会炸）；
         ⑤ `lottery_draw` 120 行 = 4 玩法 × 30 期（`85`大乐透 / `35`排列3 / **`350133`排列5** / `04`7星彩），身份对 `(gameNum,drawNum)` **零重号**。
      ⇒ **真包里挖出的 5 条硬事实（直接改后续工单，全部有行号级证据）**：
         1. **两批之间"变化的 6 行"价格一字未动，变的只是 `*f` 升降盘箭头归零**（`1/-1 → 0`）⇒ 盘口时序**只认价格键**，`*f`/`updateTime` 是噪声；真实变价是稀疏事件 ⇒ 10 分钟档必须上（且只上 offer 两 topic）；
         2. **`oddsHistory` 自带 5 条带时间戳的历史价** ⇒ 即使我方快照断档也能回填最近 5 个变盘点，**CLV 第一版可先吃它**（不必等积累）；
         3. **同一身份跨批内容会变**（`lottery_draw` 120 期里 30 期变了：`prizeLevelList` 结构整体换形 + `lotterySaleEndTimeUnix` 由 `0` 变 `{}` **同键类型翻转**）⇒ COLLECT2 的 fact 写入**必须 `ON CONFLICT DO UPDATE`（最新 snap_ts 胜）**，而现有 stg 是 `DO NOTHING`（按 hash 幂等，两版都留在 stg，正好是重放素材）；类型容错一律"存原文 + 解析失败进 notes"；
         4. **`jc_issue.matchList` 就是 14 场对阵（带 `gmMatchId`/`matchNum`/两队全名简称/`startTime`/`leagueId`）**，`jc_issue_result` 带 `gameKey` + `matchList`(含 `czHalfScore/czScore/result/h/d/a`) + `prizeLevelList` **但本期未开奖 ⇒ 全空串/长度 0**
            ⇒ `fact.jc_issue_match` / `fact.jc_issue_prize` 的字段映射现在有真依据了；奖级列表**会随开奖整体变化**，而 `league_ing` 在 fact **没有 DELETE** ⇒ 只能 upsert + "标记失效"，不得假删；
         5. **两批缺 topic**（15:03 只给 offer 两 topic；15:16 缺 `jczq_offer`/`jc_issue`/`jclq_offer`）、**`.done` 早于文件落齐** ⇒ 已提为契约红线；远端 ingest **必须把"批内 topic 缺席"记成 gap 而不是"无变化"**（这条进 COLLECT2 的 T 项）。
      ⇒ 交付物：`docs/回传-验收v1.1第1批.md`（A 通过项 / B 必改 4 项 / C 请他们自查"让球线在 `options` 不在顶层"+ 键数口径 22/26 / **D 为什么 10 分钟要紧** / **E 10 行核对表**——我这 `webapi.sporttery.cn` **直连 HTTP 567 反爬**，无法自证与官网一致，只能请国内机在官网肉眼核）。
      ⇒ 契约文档改动（v1.1→**v1.2**，三处）：§5.0 承认 9 键并钉死 `fetched_at` 三条限制；§5.1 endpoint 钉死 `getMatchCalculatorV1.qry?channel=c`（探针用的 `getMatchListV1` 多 18 键，**我的旧夹具因此不代表生产**）+ 让球线只在 `options`；§7 两条红线提级。要求回写 `contract_version=v1.2`。
      ▶ **P0-COLLECT2 的堵点解除**（用户 15:3xZ「国内采集也做了很多了，可以继续了」）：工单改为**真包驱动**（450 行 / 3 批幂等回放 + 上述 5 条事实），但顺序上先让 COLLECT1b 过验收、再由队长用真包重建夹具，最后才派 COLLECT2。
    - ✅ **v1.2 夹具已重建**（`docs/db/make_collector_fixtures_v12.py` → 142 行，暂存 `/tmp/fixv12`，等 COLLECT1b 验收后才拷进 `tests/fixtures/`）：
         `jczq_offer` 91（85 全量 + 6 行跨批变化）/ `jczq_result` 15 / `jc_issue` 4 / `jc_issue_result` 6（真包 3 未开奖 + 旧探针 3 已开奖）/
         `lottery_draw` 22（4 玩法各 1 + 6 行跨批变化 + 12 旧探针）/ `jclq_result` 2 / `errors` 2。**外壳故意保留两态**（真包 9 键 123 行、旧探针 8 键 19 行）
         ⇒ 解析层**不得要求 `fetched_at` 存在**（这条写进 PROVENANCE 当回归样本）。自检：142 行 `src_hash` 全对、`parse_line` 除 2 行 `jclq_result` 按裁决 raise 外零异常。
    - 🔶 **P0-COLLECT1b（新工人 Agnes 首单）20:00→00:58Z 两次都到点被杀（rc=124，各 40 分钟），但活其实干完了**：
         队长**独立复核三条全绿**——① `jc-move-check`（新写的验收工具 `~/bin/jc-move-check.py`）证明 18/18 个顶层函数**逐字一致、零新增定义**；
         ② **行为金标**：拆分前我把 `parse_collector.py` 连同 77 行夹具跑出的输出存成 `/tmp/golden_digest.json`，拆分后重跑**逐键完全相同（零漂移）**；
         ③ `omp-ast-check` 对 5 个 parse 文件 0 违规（78/41/50/33/79 行，全部达标）。
         **但测试没收尾**：`test_collector_contract.py` 仍 105 行、`test_collector_v11.py:93` 121 列，且它在拆一条用例时**顺手加了金标里没有的 `report["ok"] is True`**
         ⇒ 全量 **427 passed / 1 failed（KeyError: 'ok'）**。⇒ 结论：**scripts/ 那半边我按证据收下，tests/ 那半边退**，开微单 **P0-COLLECT1c** 只修 3 处点名问题（01:02Z 派，1800s）。
         同时抓到我自己两处流程错：验收路径写成整个 `tests` → 把 19 条 v1 遗留大文件算成本单违规（§9-43）；
         对"一拆二"的用例只比了名字没比语义 → 现在补上**语句级集合比对**（金标 5 条有效语句在两半并集里都能找到 ⇒ 只多不许少，多的那条恰好是坏的）。
    - 📝 夜里写好的三张工单（都在 `~/tickets/`）：**P0-COLLECT2**（真包 → `fact.jc_*`，含我独立算出的**逐表 oracle 行数**：jc_match 17 / jc_offer 170 / jc_result 15 / jc_issue **7** / jc_issue_draw 3 / jc_issue_match **62** / **jc_issue_prize 0**（真包 `prizeLevelList` 全空）/ lottery_draw 120）；
         **P0-CLV1**（官方快照当收盘价，去噪只比价格键；允许"可算样本=0"但必须原样报）；**P0-JCALIGN1**（竞彩简称 ↔ `ref.team.aliases.sporttery`，三档匹配阶梯、严禁编辑距离/音译，**错配一票否决整单**）。
    - 🔎 **顺手挖出的战略事实**（进晨间报告）：今晚 17 场在售里**西甲 7~8 场**（巴萨/马竞/皇马/莱万特/阿拉维斯…），而 `ref.league` 我们**就有 `laliga`** ⇒ 竞彩盘口和我们的模型概率**第一次可能真连上**；
         但 `select count(*) filter (where aliases ? 'sporttery') from ref.team` **= 0**、`ref.jc_match_num` **0 行** ⇒ 全堵在对齐上（所以 JCALIGN1 排进夜里队列）。
         反面：在售还有 英冠/荷甲/解放者杯/亚冠精英（全北现代、柏太阳神、阿布艾因…）**我们一个都没有** ⇒ 要不要扩联赛源，是明早要用户定的第二个大问题。
    - ✅ **01:30Z 提交并推送 `ed5fc21`**（P0-COLLECT1 全家：解析层 + 拆分 + 测试收尾，验收 428 passed / 0 failed / ast 0 违规 / `fact.jc_*` 全 0）。
    - 🔧 **01:27Z 队长把真包夹具换进入工作树**（`tests/fixtures/collector_v11/**` = `/tmp/fixv12` 的 142 行，**未提交**，等 COLLECT2 把期望值改绿一起收）：
         换完立刻量到 **7 条"必然会红"的期望值漂移**（全是旧探针写死的数量：77→142、40/8→91/17、12→22、期头 26126→26127、`"5:1"` 锚点不存在、`取消` 中文串 0 命中），
         我**逐条算好真值写进 P0-COLLECT2 工单**（含 HHAD 让球线真实分布 `+1×7 / -1×8 / -2×1 / +2×1 / -3×1`），并钉死"这 7 处是期望值漂移、不是解析缺陷"——
         依据是我自己那 450 行真包过 `parse_line` **零异常**。工人工时最贵的就是自己全局找这种数。
    - 🧪 **DDL 预检**（01:15Z）：解析产出列 vs 八表列逐一比对，只两处对不上——`jc_match.home/away_team_id` ↔ 解析层 `home/away_sporttery_id`（映射写 loader，工单已点名）、
         `jc_issue_draw` 缺 `game_name` ⇒ 我**直接 ALTER 加列**（表 0 行，零风险；`docs/db/infra_p0_8_jc_tables.sql` 同步）；其余差集全是 `src_hash/src_file/first_seen_at/last_seen_at`
         元数据列 ⇒ loader 填，且 `src_hash` **填原始行的 hash**（子表行也一样，不许自算）。
    - 📌 钉一条给 CLV 单用的事实：真包 `jczq_result` **15 行里 0 行是字面「取消」**，未开/取消的真形态 = `sectionsNo999='' + matchResultStatus='1' + poolStatus='Close'`（实测 2 行）。
    - 📈 **18:35Z 把 CLV 的可行性一次量死**（已写进 `~/tickets/P0-CLV1.txt` 的 A/B 段）：真包 85 块里 **82 块自带 `oddsHistory`**（≤5 项变价史），**末项价格与现价相同 = 0/82** ⇒ 它是「被替换掉的旧价」，现价只在 `options`；末项距本次快照中位 **540 分钟**（范围 48~776）⇒ 官方一次请求白送约一天的变价轨迹。
      但这批快照是北京时间 22:35、最早开球 00:00 ⇒ **快照价 ≠ 收盘价**（早 1.4 小时）⇒ 结论：**真 CLV 必须等 ≥3 天 10 分钟档**；今天就地能算的是替代指标 **A 段 `analysis.jc_movement`**（n_changes / first→last / move_pct / **让球线是否变化**）。工单已拆成 A、B 两段，并硬性要求「可算样本 = 0 就原样报 0，不许拿变价史冒充 CLV」。
    - 🧱 另开小单 **P0-COLLECT3**（`~/tickets/P0-COLLECT3.txt`）：解析层现在**把 `oddsHistory` 整个丢掉**（`jc_offer` 产出列里没有它），而 `fact.jc_offer.odds_history jsonb` 我已 ALTER 并同步 DDL 文档 ⇒ 等 COLLECT2b 落地后派这张小单把它捞回来（不捞，A 段就没数据）。
    - 🔨 **19:09~20:34Z 数据通路四易其稿（诚实记录：前三单都超时）**：2b(40min 0 改动) → 2c(写死式：55 秒建文件、6 分钟修完 D1~D4、25 分钟仍停在 CLI 空壳) → 2d(把 2c 又拆半：只写竞彩三表 + 点名 D5/D6/D0；它把 `jc_write.py` 修到 100 行、D5 改成 `sql.SQL(clause)`、D0 改成 `len(dash)==4` ⇒ 428 仍全绿，**但 25 分钟又没写 loader**) → **2f（照图施工单：我把 7 个函数的签名/返回值/调用顺序/日志格式全部写死，工人只填实现）**。
      · **我抓到一颗运行时炸弹 D5**：`sql.Literal(clause)` 会把 WHERE 片段**当字符串值加引号**（实测 `sql.Literal(' WHERE 1=1').as_string(None)` → `'"' WHERE 1=1"'`）⇒ 拼出的 SQL 必语法错误，而**行数/AST 检查一点看不出来**；已把这条检查加进我自己的 `~/bin/omp-ast-check.py`（`sql.Literal(变量/SQL片段)` 直接判违规），并同步工具指纹清单。
      · 拆出来的 **2e** 专管传统足彩五表（FK 孤儿父行合成 + `is_current` + 类型容错，oracle 7/3/62/**0**/120）。
      · **2g（21:03Z，禁止读代码 + 材料全内联 + 2400s 单次）终于把 loader 写出来了**：107 行、批归属/幂等键/`_adaptd` 适配 `jc_write` 全都在，只是同样在 21:27 才落笔（**24 分钟纯思考，trace 里 5.3MB 全是 thought_chunk、0 工具调用**），到点没收尾。
      · **而且它当场测出我工单里的 mtime 口径是错的**：`stat` 实测包内 `.done` 与全部数据文件 mtime **完全相同**（15:38:26 = 我方解包时刻）⇒ 按 mtime 分批会把三批全塞进每批且**不报错**；它改用「文件名时间戳窗口 `(t_{i-1}, t_i]`」，我复核与三批真实分布**逐条吻合** ⇒ 已在回传文档 G 节改成实证版。
      · **21:45Z 派 2i**：机械拆分 `jc_read.py`（逐字搬 5 个函数，队长有比对工具）+ 修它自己留的一个静默丢数据的缺陷（`files_for_batch` 只取窗口内**最新**一个文件 ⇒ 将来 `__002` 分片会被丢）+ 真跑两遍出 count。
      · 结论（写进 skill §9-45/48/49）：**慢工人不是不能干，是不能"让它自己想办法"**——喂料越像图纸，它越能落地。

   - ▶ **P0-BACKFILL1c 在跑**：BACKFILL1 那 3 条用例**依赖真库存量**（"待取==30"/"发出3条"/"配额耗尽即抛"），真回填落块后当场转红 ——
     **这是我验收漏的**（当时 raw 是空的，断言"碰巧"成立）。修法是 stub `cached`/`remaining` 或用 `season=2099` 这类不可能存在的输入
   - ✅ fact 层已建（`docs/db/infra_p0_4_fact_core.sql`）：`fact.fixture` / `fact.fixture_result`（多源并存 PK(fixture_id,source)）/ `fact.v_result_conflict` / `ref.league` 五联赛 seed
     ⇒ 数据进 raw 后接 **P0-FACT1**（工单已备 `~/tickets/P0-FACT1.txt`：raw → ref.team/fact 解析 upsert，6 文件，强制"先看真报文再定字段"）
7. **P0-market**（工单）：`devig.py` + `clv.py` + 两时点快照 ingest（依赖 ODDS key 或改走 API-Football `/odds?date`）
6. 悬而未决：CBA 盘口覆盖（probe 定）、sporttery 端点字段（probe 定）、欧冠36队 bracket 扩展（P3）、**ODDS_API_KEY 待人工补**、**`.gitignore` 加 `.omp-logs/` 一行**

## 7. 风险备忘
- sporttery 接口若需 token/签名 → 该 topic 降级"待议"，禁止逆向（采集文档 §4）
- FastAPI Cloud 线上看板在 Nginx 迁移完成前**不许下线**（退役时机=D5 的迁移工单当天）
- **git 政策（2026-09-15 用户改口）**：**"更新 readme，commit and push"** ⇒ 队长在每个工单验收后 `git add` 该单文件 + commit（message 带工单 TAG）+ **push `origin/v2`**；
- ✅ **已执行（2026-09-15 10:40Z）**：4 个 commit 推上 `origin/v2`（远端新分支，HEAD `ad450df`）：
  `150b449` P0-STORE1/1b/1c → `0db60b6` P0-DERIVE1/2 → `ea1f7d3` P0-BACKFILL1/1b/1c → `ad450df` P0-FACT1+README；
  push 前逐条扫过密钥（`git diff --cached` 命中 0）并确认 `.env`/`.omp-logs/` 不在树里；已 `git fetch` 建好 upstream，以后 `git push` 即可。
  仓库身份：`git config user.name/user.email` 按既有历史设为 `nxz1026 <nd0104@qq.com>`（**仅本仓库局部，没动全局**）。
  凭据：用 `/home/ubuntu/.env` 里的 `GITHUB_TOKEN_1` + 一次性 `GIT_ASKPASS` 脚本（token 不上命令行、不进 git config，脚本用后即删）。
  **工单里 coder 一律禁 git 一切子命令**（不变，防止它自己改历史）；`repo/.env`、`.omp-logs/`、`predictions/ai_scores.json` 之类运行期文件**绝不入册**（push 前必做密钥扫描，见 OMP-SKILL §5）
