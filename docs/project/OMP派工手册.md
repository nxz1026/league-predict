---
name: omp-ops-oracle
description: 在 NDORACLE 本机上驱动 OMP coder 干活的完整操作手册：后端选择、快问答、长任务派工器、工单六条、验收门禁、冒烟 SOP、已知坑。league-v2 所有代码工单必须按本文件模板下发。
---

# OMP 操作技能（oracle 本机版，2026-09-15 复测校准 v2）

> **2026-09-15 变更（用户指令）**：**mimir 不再参与任何步骤**——取 key、派工、验收全部在 NDORACLE 本机完成。
> 本文件所有数字都是**本机实跑**得到的，不是转抄；改脚本或换机器后先跑 §7 冒烟。
> 队长（你）纪律不变：**只写工单和验收，不替 coder 写应用代码**；一切自报结果必须独立复跑。

## 0. 何时用 OMP
- **用**：写/改应用代码、跨文件重构、需要本机 PG/环境/网络的工作、需要读大段代码的审核。
- **不用**：单文件查询、纯问答、≤1 万行数据处理（自己 bash/psql 干完更快）。
- **档位选择（实测后修正）**：本机 **ACP 比 API 快**（8s vs 23s），凡"要看文件/跑命令"的活直接上 `--acp`；
  只有"纯文本产出、不碰磁盘"才用档位A（快答/审文）。原先"≤20s 才自己干"的尺子按 ACP 重算。

## 1. 实测基线（2026-09-15，NDORACLE）
| 项 | 实测值 |
|---|---|
| `omp --version` | `omp/18.1.20`（本机 `~/.local/bin/omp`，aarch64） |
| ACP 模型 | `~/.omp/agent/config.yml` → `modelRoles.default`。**用户 2026-09-15 15:02 改为 `Agnes/agnes-3.0-flash`**（此前 P0 全部工单由 `deepseek/deepseek-flash` 完成）。派工器**不带** `-m`，改这一行即换工人 ⇒ 换模型当天验收加严（§9-39） |
| ACP 上下文/成本 | `size: 1000000`（1M）、used≈21k、**cost≈$0.0032/单工具调用轮** |
| 档位A 纯问答 | **23s** |
| 档位B 无工具 | **6s**；档位B 带 1 次 bash 工具调用 **8s** |
| 派工器端到端 | SMOKE1（建文件+写报告+写 .done）**26s，1 次成功，rc=0** |
| 权限自动批 | 生效：`session/request_permission` → 选中 `allow_once`（`--acp` 才有；默认 API 档无工具） |
| 冒烟后仓库 | `git status --porcelain` **空**（只读单确实没落盘改 repo） |
| 仍在（未修） | `--timeout` 在 ACP 路径**不生效**（`call_acp` 收了不用）→ 见 §2 外层 timeout |
| 仍在（未修） | `~/.omp/agent/hooks/heartbeat.ts` **不存在** → 派工器里 `pgrep -f "local/bin/[o]mp --hook"` 永远匹配不到，**孤儿清理是空转**；超时被杀后残留的 `omp acp` 子进程要人工/按 §3 的 pkill 兜底 |

## 1.1 环境与测试基线（**P0-env 已完成**，2026-09-15 本机实测）
- **venv**：`~/.venvs/league` = **python 3.14.4**。系统 `python3 -m venv` **建不出 pip**（Ubuntu 26.04 缺 `python3-venv`/ensurepip，实测报错 "You may need to use sudo… python3-venv"）→ **改用 uv 建**：
  ```bash
  uv venv ~/.venvs/league --python 3.14
  uv pip install --python ~/.venvs/league/bin/python -r requirements.txt -r requirements-web.txt pip
  ```
  已装：requests 2.34.2 / pyyaml 6.0.3 / **pytest 9.1.1** / pip 26.2.1（uv 建的 venv 默认**无 pip**，故显式装一个）+ web 全套（fastapi/uvicorn/pydantic/dotenv/loguru/apscheduler）。
- **测试基线（三条，数字随工单递增，2026-09-15 P0-STORE1c 后）**：
  | 命令 | 基线 | 用途 |
  |---|---|---|
  | `python -m pytest tests -q` | **378 passed / 12.0s**（v1 起点 215 → store/quota/derive 286 → FACT1 305 → FACT2/3 308 → MARKET1 378） | 全量，验收终判 |
  | `python -m pytest tests --ignore=tests/web -q` | **304 passed / 4.5s** | derive/store/market/ingest/model 迭代期快档 |
  | `python -m pytest tests/web -q` | 74 passed | 只在动 web 相关时跑 |
  - ⚠️ **全量的前提是装了 `requirements-web.txt`**：否则 `tests/web/` 5 个模块 import 失败 → `Interrupted: 5 errors during collection`，**一条用例都不跑**（看起来像"全红"，其实是环境缺依赖）。
  - ⚠️ **不能按单文件跑全部测试**：`python -m pytest tests/test_onside.py -q` 实测 `1 error`（`ModuleNotFoundError: core`，历史约定）。新增用例要么自己插 `sys.path`，要么只整体跑。
- **验收工具（队长自研，只读禁 coder 改）**：
  - `python3 ~/bin/omp-ast-check.py [路径…]` → 机检 ≤100 行/文件、≤50 行/函数、**≤120 列**（ruff line-length）、print/breakpoint/set_trace/pdb 走私、`psycopg` 越出 store+ingest、禁用依赖；不给参数就扫 git 改动+未跟踪 .py。**检测全走 AST**（第一版用正则，工具自己命中 `pdb|psycopg` 字符串误报自己，教训）。
  - `bash ~/bin/league-accept.sh <TAG> <新模块路径…>` → 一条龙：哨兵+报告 → 全量/快档 pytest → 机检 → print 残留 → 改动面与冻结区 → **`web/services/ai.py` 自伤残留检查** → PG 留痕检查；任一 FAIL 退码 1。
- **分支**：`v2` 已从 main(`60e3201`) 创建并 checkout；远端 origin 只有 main/quality/m7/web-dashboard，**v2 尚未推送**（§4 铁律①：推送由人工）。
- 旁证：`web/config.py:23 load_dotenv(BASE_DIR/".env")` → web 层也读 `repo/.env`；`constants.py` 那份读的是引擎层。两者同一个文件。

## 1.2 PG 与 collector 通路（**P0-infra 已完成**，2026-09-15 队长本机实施，非工单）
详单与验收命令见 **`~/league-v2/docs/infra/README-infra.md`**（唯一出处，别处不重复）。要点：
- 库 `league` + 三角色 `league_ing/league_app/league_ro`（口令 `~/.league-db/`，DSN 写进 `repo/.env`）；schema 只到 **ref(4表)/stg(7表,UNLOGGED)/ops(3表)** = 14 表，fact/model/analysis 等国内机契约冻结再建。
- **store 层依赖已就位**：venv 里 `psycopg[binary] 3.3.5`，三条 DSN 实测连通，写/幂等/拒写全过。
- collector 通路用一次性密钥**端到端实测通过**（rsync 推 JSONL+.done 落 `/srv/league-staging/incoming`；交互 shell / scp / 越界写 / 命令走私全拒），密钥已删；**待国内机 pubkey** 追加进 `/srv/league-staging/.ssh/authorized_keys`（现 0 字节）。
- 改 DB 前必读三条红线（默认权限顺序 / REVOKE 撤不掉 PUBLIC 隐式授权 / stg 只给 TRUNCATE 不给 DELETE）在 `README-infra.md §2`。

## 2. 两个档位（本机）
```bash
# 档位A：纯文本快答/审文（无工具，不落盘；~20s）
~/.local/bin/omp-call "把 docs/x.md 表格第三列改成…"

# 档位B：真执行（读写文件、跑命令；6–8s 起）——务必外层套 timeout！
timeout 1800 ~/.local/bin/omp-call --acp --cwd ~/league-v2/repo "任务全文"
```
- **`--acp` 的 `--timeout` 是摆设**，硬超时只由外层 `timeout` 提供；手跑裸 `omp-call --acp` = 可能挂死。
- 默认 cwd 是 `~/work`；league-v2 **一律显式 `--cwd ~/league-v2/repo`**。
- **同一仓库同时只开一单**：这是**人工纪律**，脚本的锁是 `/tmp/ompw-<TAG>.lock`，**只防同 TAG 重入，不防同仓库并发**（不同 TAG 会互踩文件）。发单前先 `pgrep -f "[o]mp-call --acp"` 确认场上只有一单。
- ACP 会话进程**绝不裸杀**（除非走 §3 的 EXHAUSTED 恢复）。

## 3. 长任务派工器（>30s 的工单全部走这个）
签名（`~/omp-resilient3.sh`，本机实测）：
```
bash ~/omp-resilient3.sh <TAG> <cwd> <单次超时秒> <maxtries默认30> <prompt文件> <哨兵词默认TASK_DONE>
# LOGDIR = ${OMP_LOGDIR:-<cwd>/.omp-logs}      ← 与 README 一致（脚本头注释里的 docs/web/logs 是旧的，忽略）
# 外层硬超时 = <单次超时秒>+90，重试间隔 sleep 20
```
标准发单流程：
```bash
mkdir -p ~/tickets ~/league-v2/repo/.omp-logs
# 1) 写工单（模板见 §4）
vi ~/tickets/<TAG>.txt
rm -f ~/league-v2/repo/.omp-logs/<TAG>.done          # 派前清标记（脚本自己也会清）
nohup setsid bash ~/omp-resilient3.sh <TAG> ~/league-v2/repo 2400 3 ~/tickets/<TAG>.txt TASK_DONE \
  >/dev/null 2>&1 </dev/null &
```
- **完成判定**（两条都要，缺一不可）：`.omp-logs/<TAG>.done` 含哨兵词 **且** 队长独立复跑 §5 验收命令。**rc=0 ≠ 成功**。
- 过程观测：`ls -t ~/league-v2/repo/.omp-logs/<TAG>_try*_*.log | head -1`；重试/耗时戳：`.omp-logs/<TAG>.attempts`（`try i rc=… / SUCCESS try=i / EXHAUSTED`）；参数戳：`.omp-logs/<TAG>.job`。
- 暂停某单：`touch ~/league-v2/repo/.omp-logs/<TAG>.paused`。
- EXHAUSTED 且无哨兵：`pkill -f '[o]mp-call --acp'` → `pgrep -f '[o]mp-call'` 归零 → 修工单重派（换 TAG 或清 .done）。
  **本机补充**：因 heartbeat hook 缺失，pkill 后还要 `pgrep -af 'local/bin/omp'` 逐个确认没有残留 `omp acp` 子进程（残留会白烧配额）。
- 看门狗 `~/omp-watchdog.sh` 存在但 **当前 crontab 未装**；要装：`(crontab -l 2>/dev/null; echo '* * * * * /home/ubuntu/omp-watchdog.sh >/dev/null 2>&1') | crontab -`——装前先看它管哪个 LOGDIR，别和别的项目抢。

## 4. 工单模板（六条铁律写死在每张工单里）
```
【项目】league-v2（规范见 ~/league-v2/README.md §2-D7，设计文档 ~/league-v2/docs/）
【任务】<锚点定位，一句话目标 + 涉及文件清单>
【铁律】
  ① 禁 git commit/push/checkout/restore/stash/reset（推送由队长人工做）
  ② 禁新增 print/DEBUG 残留；日志走既有 log 模块
  ③ 机械搬移禁改逻辑/数值/顺序
  ④ 用锚点定位描述改动点，不贴大段代码
  ⑤ 新文件 ≤100 行、函数 AST ≤50 行；只 import scripts/core 不改其文件；禁 pandas/sklearn/新依赖（白名单：psycopg[binary] 仅限 scripts/store/）
  ⑥ 完成后写 ~/league-v2/repo/.omp-logs/<TAG>.report.txt（改动清单+验收输出）并 echo TASK_DONE > .omp-logs/<TAG>.done
【验收】（队长用工具逐字复跑，2026-09-15 基线已填死）
  bash ~/bin/league-accept.sh <TAG> <新模块路径…>      # 一条龙：哨兵→pytest 281/207→机检→改动面→自伤→PG 留痕
  # 手工等价（工具不可用时）：
  #   source ~/.venvs/league/bin/activate && cd ~/league-v2/repo
  #   python -m pytest tests -q                          # 全量 = 281 passed（终判，零 FAILED）
  #   python -m pytest tests --ignore=tests/web -q       # 快档 = 207 passed
  #   python3 ~/bin/omp-ast-check.py scripts/<新模块> tests/<新用例>
```
> **派单纪律（队长自己的五条，2026-09-15 立）**
> 1. **禁删已验收单的 `.done`/report**：它们是审计证据。派单前只 `rm -f .omp-logs/<新TAG>.done`（我不小心删过 1b 的哨兵，report 还在，已在此记录）。
> 2. **例外授权要写在工单里**：`既有 tests 禁改` 这类铁律一旦本单需要破例（如 P0-HYGIENE 要改测试自己），必须在工单里用"【本单例外授权】"显式圈定文件集合并说明理由，否则 coder 会照铁律拒改或偷偷改。
> 3. **派单前必做**：确认仓库空闲（用 §9-17 的正确姿势，别用自匹配的 pgrep）+ `md5sum ~/bin/*.py ~/bin/*.sh > /tmp/captain-tools.md5` 工具快照，回来 `md5sum -c` 证明没人动验收器。
> 4. **「不许真联网」要用代理绊线自证**（本机 `unshare -rn` 是 Operation not permitted，别指望 namespace）：
>    `https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 python -m pytest tests/test_backfill_*.py -q`
>    —— urllib 会走这个死端口，**真发请求必炸、纯 stub 必绿**（BACKFILL1 实测 11 passed/0.31s）。
>    比"读代码相信他打了 monkeypatch"硬得多；凡是工单写"测试不许联网"的，验收都加这一步。
> 5. **复核必做"设计层"三问**（不是跑绿就算过）：① 这条保证是"必然"还是"碰巧"（STORE1b→1c 就是这么被抓出来的）？② 新逻辑有没有**只靠真库**才执行的测试路径（要落成零 DB 的 stub 用例）？③ 有没有跨进程状态（DB 事务 vs 文件系统）不一致？
> **口令与 DSN 纪律**：工单正文、report、trace 日志里都不许出现真实口令。验收时跑一遍泄漏扫描：
> 对每个口令/key 用 `grep -qF "$secret"` 扫 `.omp-logs/<TAG>.report.txt` + `<TAG>_try*.log`（可达 9MB）+ 全部新增文件。
> **注意**：`grep -c "postgresql://league"` 命中不等于泄漏（coder 可能已打码为 `***`）；只有真实口令串命中才算。
> **验收前必读的噪声**：任何 `pytest tests -q` 跑完，`git status` 必出现 `M predictions/ai_scores.json`
> （`tests/web/test_m6_ai_enrich.py` 经 `web/services/ai.py:20` 的 BASE_DIR 硬编码真实落盘，`LP_OUTPUT_DIR` 也隔离不掉）。
> 这是**基线噪声不是 coder 改动**：审 diff 前队长先 `git restore predictions/ai_scores.json`；
> 反之，若 coder 的 diff 里出现该文件的"顺手清理"，按 §5 无关回退**拒收**。
> 根治办法＝微工单 `P0-hygiene`（给该用例 monkeypatch `AI_SCORES_FILE` 到 tmp_path），待放行。

league-v2 专用附加验收：
- store 层：重复执行同一 CSV 装载两遍，`SELECT count(*)` 不变（幂等）
- derive 层：黄金用例手算对账（矩阵全边际和=1.0±1e-6；让球移位边界 0-0/-1 归负）
- ingest：非法行必须进 `ops.ingest_log.rejected`，不许静默吞
- PG 类工单：`sudo -u postgres psql -d league -c '\dt *.*'` 前后 diff 说明新建对象
- **key 类**：工单正文和日志里不许出现真实 key； coder 只许 `import` 读 env，不许打印 env。

## 5. 验收与防三诈（审 diff 必看）
```bash
cd ~/league-v2/repo && git diff --stat HEAD && git diff HEAD -- scripts/
```
- **删函数充"拆分"**：新文件行数少了但旧函数没等价体 → 拒收
- **DEBUG 走私**：diff 里出现 print/pdb/注释掉断言 → 拒收
- **checkout 回退**：diff 里出现与任务无关的文件回退 → 拒收
- **改队长工具蒙验收**：diff/日志里出现 `~/bin/omp-ast-check.py`、`~/bin/league-accept.sh` 的改动 → 直接拒收（发单时在铁律里写死"验收工具只读"，并留 `md5sum` 快照对照）
- **测试自伤残留**（本仓库真实存在）：`tests/web/test_m3_jobs.py:283 test_ai_broken_app_starts` 会**把 `_broken = 1 / 0` 真写进 tracked 的 `web/services/ai.py`** 再在 finally 还原；一旦 `timeout` 把整轮杀掉就会留脏（而 web/ 是 FastAPI Cloud 线上源码，D5 不许它挂）。验收必须查：
  `grep -c "_broken = 1 / 0" web/services/ai.py` = 0 **且** `git diff --quiet -- web/services/ai.py`
- 列宽红线：`pyproject.toml` 的 ruff `line-length=120`（P0-STORE1 就漏了 4 行 128/132 列，机检现已覆盖）
- 重构类工单必须有 golden 位级断言保护，红即拒收。
- 验收命令用 `&&` 硬链逐字跑（`grep -a FAILED` 计数=0 → `pytest -q` 尾行匹配），禁分号链、禁裸 `grep -c '215 passed'`（"2 failed, 215 passed" 会假绿）。

## 6. 发单顺序（当前：地基两件队长自干完，剩下全是 OMP 工单）
```
P0-env    ✅ 队长自干完：~/.venvs/league + 基线填死 + v2 分支建好 + psycopg 装好
P0-infra  ✅ 队长自干完：league 库 + ref/stg/ops 14 表 + 三角色最小权限 + pg_hba 跨库隔离
             + OS 账号 league/受限 rsync-only shell + /srv/league-staging（E2E 实测通过）
             → 详单与复跑命令：docs/infra/README-infra.md
P0-store1 ✅ OMP 交付并验收通过（2026-09-15，try1/1、7 分钟、≈$0.003）：
             store/pg.py 56 行、store/upsert_official.py 89、ingest/collector_pull.py 80、ingest/quota.py 54
             + tests/test_store_idempotency.py 92 / tests/test_collector_contract.py 100 → 基线 215→223、141→149
P0-store1b ✅ collector_pull 重写 99 行（逐文件事务 / 未知 topic 留 original / >120 列清零）+ test_quota.py 84
P0-store1c ✅ 事务边界加固：main() 改裸 pg.connect（不再被 write_conn 套成 SAVEPOINT）、_load() 进事务前断言
             conn.pgconn.transaction_status==IDLE 否则 RuntimeError、新增 tests/test_ingest_atomicity.py（**零 DB 假连接**，
             4 条用例在坏 DSN 下仍 pass＝真零库）、quota.py 只加 docstring（已有行的 cap 抬不动）
P0-derive1 ✅ scripts/derive/{grid,totals,scores31,goals4}.py + 19 条用例（_dc_pmf_grid 直接喂derive，禁 round/top-12；rho=0 等价独立 Poisson 当 oracle）
P0-derive2 ✅ handicap.py（线加主队、line 必须 int，True/1.0 全拒）+ registry.py（只注册 had/hhad/crs/ttg/jqc，**haf 缺席即 KeyError 不许占位**）
             黄金值队长独立复算逐值相等；⇒ 基线 215 → **286**（快档 141 → **212**）；此后 FACT1/2/3 与 MARKET1 把它推到 **378 / 304**
P0-raw+fact ✅ 队长 DB：p0_3 独立 `raw` schema（LOGGED + partial unique `(params_hash) WHERE http_status=200`）
             p0_4 `fact.fixture`/`fact.fixture_result`(PK(fixture_id,source) 多源并存)/`v_result_conflict`/ref.league seed
P0-backfill1  ✅ api_get.py + run_backfill.py（--plan 零 HTTP、代理绊线自证零网络）
P0-backfill1b ✅ **修 P0 无痕丢数据**（详见 README §6.6）：autocommit + 前置守卫 + 429 即收工 + PAUSE_S=7 + 自审三数
             ⇒ 真回填完成：AF 15/15 全 200、**5341 场完赛、halftime 缺失 0**；FD 10 块 200 + 5 块 403（免费档不给 2022）
P0-fact1   ▶ 在跑（10:01）：raw → ref.team / fact.fixture / fact.fixture_result（6 文件，第一动作＝用真报文核字段）
P0-market1 已备好待派（~/tickets/P0-MARKET1.txt）：market/{devig,clv}.py 纯数学 + 队长独立算好的黄金值
P0-hygiene 已备好待派（~/tickets/P0-HYGIENE.txt）：tests/conftest.py 快照护栏 + ai_scores.json 落盘改 tmp_path（含【本单例外授权】）
后续       ：P0-backtest（需先建 model.*/analysis.* 的 p0_5）→ P0-market2（AF /odds?date 近 6 月 ≈180 请求＝2 天配额）→ P1 halftime
```
每张 ≤100 行 × ≤8 文件；超界先回来找队长拆分，不许自行扩权。**派单前必做**：`pgrep -f "[o]mp-call --acp"` 确认仓库空闲 + `md5sum ~/bin/omp-ast-check.py ~/bin/league-accept.sh > /tmp/captain-tools.md5` 留工具快照。

## 7. 冒烟 SOP（首次上机 / 改过 omp-call 或派工器 / 换模型之后）
```bash
mkdir -p /home/ubuntu/omp-smoke && rm -rf /home/ubuntu/omp-smoke/*
setsid bash ~/omp-resilient3.sh SMOKE1 /home/ubuntu/omp-smoke 300 1 ~/tickets/SMOKE1.txt TASK_DONE
# 判据（本机 2026-09-15 实测 26s 通过）：
#   .omp-logs/SMOKE1.attempts 末行 = SUCCESS try=1
#   .omp-logs/SMOKE1.done = TASK_DONE ；report.txt 有改动清单+验收输出
#   cd ~/league-v2/repo && git status --porcelain 为空（没误伤仓库）
```
工单 `~/tickets/SMOKE1.txt` 要 coder：建 `hello.txt`（OMP_OK + 日期）、写 `<TAG>.report.txt`、真跑 `echo TASK_DONE > .omp-logs/<TAG>.done`、全程禁 git。
用**独立临时目录**跑冒烟，绝不在 repo 里试刀。

## 8. 数据源 key 与联网（替代旧"ssh mimir 取 key"）
- 代码仓库：`https://github.com/nxz1026/league-predict`，本机克隆 `~/league-v2/repo`（origin/main `60e3201`；**工作分支 = `v2`**，本地已 checkout，远端无 v2、未推送）。
- **key 出处（本机）**：`/home/ubuntu/.env`，含 `API_FOOTBALL_API_KEY`、`FOOTBALL_DATA_API_KEY`、`API_FOOTBALL_BASE_URL(=v3.football.api-sports.io)`。
- **变量名不一致（重要）**：`scripts/core` 实际读的是 `API_FOOTBALL_KEY`（`data/fetch.py:27,256`、`backtest.py:287`）与 `FOOTBALL_DATA_API_KEY`——**不是** `API_FOOTBALL_API_KEY`。
  已按代码名落地 `~/league-v2/repo/.env`（chmod 600，`.gitignore:18` 已忽略，`git status` 干净）。
  `API_FOOTBALL_BASE_URL` 代码用不到（host 硬编码在 fetch.py:233/279、backtest.py:225），无需注入。
- 加载机制：`scripts/core/constants.py:_load_dotenv()` 零依赖读 **`<repo>/.env`**（`LP_OUTPUT_DIR` 可改根），且**只填未设置的 env**（已有环境变量优先）→ 工单里临时换 key 用 `env API_FOOTBALL_KEY=… python …`，别改 .env。
- **缺口**：`ODDS_API_KEY`（The Odds API，`scripts/bball/run.py:113`）**不在 `/home/ubuntu/.env` 里** → 篮彩 NBA/CBA 盘口无法开跑；需人工补 key，或改走 API-Football `/odds?date`。
- **联网实测（本机直连，无需代理）**：
  - API-Football `GET /odds?date=2026-09-15` → HTTP 200、`errors={}`、`response` 10 场 ✅（免费 100 req/天）
  - football-data `GET /v4/competitions/PL/matches?season=2024&status=FINISHED` → 380 场、**halfTime 非空 380/380** ✅
  - ⚠️ 该免费档 **不回传** `X-RateLimit-Requests-*` 响应头 → **拿不到服务端剩余配额**，`ops.quota_ledger` 本地账本因此是**强制项**（P0-backfill 前置）。
  - 上述探测各耗 1 次配额，已计入当日预算。

## 8b. git 政策（2026-09-15 用户改口：队长可以 commit **and push**）
- **用户原话**："更新一下readme，commt and push" ⇒ 从"只 commit 不 push"升级为**验收即 commit、攒一段 push `origin/v2`**。
- **coder 侧铁律不变**：工单里**禁 git 一切子命令**（它一旦自己 commit，我就无法用 `git diff` 审它的改动面，三诈全瞎）。
- **每次 push 前必做三件事**（这条是硬闸，漏一件就是事故）：
  ```bash
  cd ~/league-v2/repo
  git status --short                                  # ① 逐条确认没有运行期文件（.env / .omp-logs/ / predictions/*.json / data/*/references/*.json）
  git diff --cached --name-only | xargs -r grep -lniE "(password|passwd|token|secret|api[_-]?key)[[:space:]]*[:=][[:space:]]*['\"]?[A-Za-z0-9$]{8,}"  # ② 密钥扫描，有输出就停
  source ~/.venvs/league/bin/activate && python -m pytest tests -q   # ③ 全量绿（基线见 §1.1）
  ```
- **push 用机器级 `GITHUB_TOKEN_1..3`（在 `/home/ubuntu/.env`，仓库里没有凭据）**，口令**绝不上命令行、绝不写进 git config**：
  ```bash
  printf '#!/bin/sh\ngrep -m1 "^%s=" /home/ubuntu/.env | cut -d= -f2-\n' GITHUB_TOKEN_1 > /tmp/git-ap.sh && chmod 700 /tmp/git-ap.sh
  GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/tmp/git-ap.sh git push https://x-access-token@github.com/nxz1026/league-predict.git v2
  rm -f /tmp/git-ap.sh    # 用后即删；token 不进 shell 历史、不进 URL 明文
  ```
- ✅ 2026-09-15 10:40Z 首推成功（`origin/v2` 新分支，HEAD `ad450df`），并已 `git fetch origin v2` + `git branch --set-upstream-to=origin/v2 v2`
  ⇒ **以后直接 `git push` 就行**（远端跟踪已建；push 仍需 askpass，因为凭据没落盘——这是刻意的）。
  ⚠️ 两个坑：① 别用 `grep -c` 接 `&&` 做扫描（0 命中时 grep 返回 1，**整条链断掉，commit 静默不发生**，我踩过）；
     ② 本仓库没配全局 git 身份，首次 commit 会 `Author identity unknown` ⇒ `git config user.name/email`（局部）按历史作者设。
  ```
- **篮彩 key 变量名是 `NBA_API_KEY`，且在机器级 `/home/ubuntu/.env`**（不在 `repo/.env`，而 `core/constants.py` 的 dotenv 只加载 `repo/.env`；
  且 v1 代码 `scripts/bball/run.py:113` 读的是 `ODDS_API_KEY`）⇒ 开篮彩单前必须先决定"追加进 repo/.env"还是"新代码优先读 NBA_API_KEY 并回落"，别改冻结的 v1 文件。

## 9. 已知坑（照抄旧文档会踩）
1. **`python3 -m venv` 在本机建不出 pip**（Ubuntu 26.04 缺 `python3-venv`/ensurepip）→ 一律用 `uv venv` + `uv pip install --python ~/.venvs/league/bin/python`（§1.1）。README 旧写法 `python3 -m venv … && pip install requests pyyaml pytest` **跑不通且不够**（还须装 `requirements-web.txt`）。
2. **缺 web 依赖时 `pytest tests -q` 不是"部分红"而是"全不跑"**：`Interrupted: 5 errors during collection`（fastapi/dotenv）。别把它当代码回归。
3. **跑测试会脏仓库**：`tests/web/test_m6_ai_enrich.py` 真写 tracked 的 `predictions/ai_scores.json`（+245 行），且 `LP_OUTPUT_DIR` 隔离不了（`web/services/ai.py:20` 用 BASE_DIR 硬编码）→ 审 diff 前先 `git restore predictions/ai_scores.json`（§4）。
4. **`.omp-logs/` 已被 `.gitignore` 收掉**（2026-09-15 队长加的一行，**尚未 commit**，等人工在 v2 上收）→ 派单日志不再污染 `git status` 判据。审 coder diff 时若见到 `.gitignore` 出现别的改动，按"与任务无关"处理。
5. `omp-call --acp` 不带外层 `timeout` 会**无限挂**（§2）。
6. heartbeat hook 缺失 → 派工器孤儿清理空转（§1、§3）。
7. 派工器锁按 TAG 不按仓库 → 同仓库多 TAG 会互踩（§2）。
8. ~~PG 无 league 库~~ ✅ 2026-09-15 已建（`league` + 三角色 + ref/stg/ops 14 表）；`longkonglong` 是**别的项目的库**，工单里禁止对它下手。
9. ~~`/srv/league-staging/incoming` 未创建~~ ✅ 已建（0750 `league:league`）。权限模型：`ubuntu` 已 `usermod -aG league`，**incoming 组只读、done/bad 组可写**（ingest 的读入+归档方向）。⚠️ **组成员变更要新登录会话才生效**，老会话（含 omp-call 派出去的 coder 子进程）没有 league 组 → 工单里必须把三个目录做成**参数**、测试一律传 tmp 目录；队长自己验真实目录要用 `sg league -c '…'` 或 `sudo ls`。
10. 本机时区：shell 是 **UTC**，派工器日志戳用 **Asia/Shanghai**（差 8h），对时别看错。
11. 现在是 **pytest 9.1.1**（不是 requirements 注释里的 ≥7.0）：目前 215 全绿；将来若出现 9.x 行为变更引起的红，先怀疑测试框架 API 再怀疑代码回归。
12. **`psql -f x.sql | head` 会静默截断脚本**：head 收够就退出 → psql 吃到 SIGPIPE 中途死掉，**而 `$?` 是 head 的 0**，看起来"rc=0 成功"其实后半截（授权段）根本没跑。跑 SQL 一律 `> /tmp/x.log 2>&1; echo rc=$?`，再 grep 日志。（2026-09-15 P0-infra 真踩：第一次建库后所有表 permission denied，就是这段没执行。）
13. **`ALTER DEFAULT PRIVILEGES` 不影响之前已建的对象** → 建库脚本必须「schema → 默认权限 → 建表 → 存量补授」四段排序。
14. **`REVOKE … FROM <role>` 撤不掉来自 PUBLIC 的隐式 CONNECT**（PG 权限取并集）→ 跨库隔离只能改 pg_hba（首条匹配即生效），且**别对别的库做 `REVOKE … FROM PUBLIC`**（`longkonglong` 是在跑的另一项目，会连带打死）。
15. **psycopg3 的 `with conn.transaction():` 正常退出是 COMMIT 不是 ROLLBACK** → 想"测完不留痕"必须显式 `conn.rollback()` 或抛异常。我自己在这里写下"（事务已回滚）"结果实际提交了 1 行，靠复跑 `count(*)` 才抓到——**队长的自报也一样要复跑**。
16. **文件系统动作不随 DB 事务回滚**（P0-STORE1 真缺陷，队长复核抓到、coder 自报没有）：一个事务吃整批文件 + 循环里 `shutil.move` → 第 2 个文件炸，第 1 个文件的 DB 写被回滚而原件已进 `done/` = **既没数据也没留痕**。规则：凡"写库 + 动文件"混在一起，必须**逐条目独立事务 + 先 commit 后 move**，异常只脏当前条目并继续（P0-STORE1b 在修）。
17. **`pgrep -f "[o]mp-…"` 会自匹配**：括号技巧只躲得过 pattern 字面量，躲不过我自己命令行里真实出现的串（`bash -c` 里带着 setsid 派工命令）→ 判"场上有没有单在跑"要用 `ps -eo pid,etimes,args | grep "omp-call --acp"`（排 grep 自身）或看 `.omp-logs/<TAG>.attempts` 末行。
18. **幂等键口径与采集契约有已接受的偏离**：契约 §5 定义 `src_hash` = 该行**原始 JSON 字节**的 sha256，而 store 侧只用它校验字段存在、**幂等键自己按规范化对象（sort_keys + 紧凑分隔 + ensure_ascii=False）重算 64 位 hex**。理由：远端复现不了原始空白/键序，采信对方值 → 采集机一个 bug 就能把整文件塌成 1 行；本地重算的 dedup 语义严格更强。**代价**：与采集机本地去重不可直接对账 → 契约 v1.1 冻结时必须回头统一（已进 README 悬而未决）。
19. **psycopg3 的 `conn.transaction()` 是"外层还是 SAVEPOINT"取决于进入瞬间连接是否 IDLE**（实测，非猜）：
    `transaction.py:215` 判据 `self._outer_transaction = pgconn.transaction_status == IDLE`。所以
    `with pg.write_conn(...) as conn: run(conn, commit=True)` 这种"外层再包一层"的写法，**只要内层进事务时还没人执行过任何语句，内层就是真 BEGIN/COMMIT**（libpq PQtrace 实测），外层 `with conn:` 的 rollback 变成空操作 → 现状"提交后才归档"成立；
    但**只要将来有人在 run() 之前先查一句**（最典型：`SELECT pg_advisory_lock(...)` 防 cron 重叠），外层立刻变成真事务、内层退化成 SAVEPOINT → kill 时"文件已进 done/ 而 DB 全回滚"的洞**原样复活**。
    ⇒ 已立 P0-STORE1c：`main()` 不再套 `write_conn`、`commit=True` 分支进事务前断言 IDLE、并加**零 DB 的 stub 顺序回归锁**。
    ⇒ 通用教训：**"看起来对"的跨资源（DB+文件系统）顺序保证，必须有一条不依赖真库的测试钉住**，否则它是"碰巧"，一次重构就没了。
20. **`league_ing` 没有 `CREATE TEMP TABLE` 权限**（实测 `permission denied to create temporary tables`）→ 想用临时表做"自清理测试"这条路不通；要证明事务行为就用 `PQtrace` 看协议，别改权限。
21. **队长自己也会造故障：新 DB 对象别顺手建进 `stg`**。P0-store 之后我想给回填加两块原始落地（`af_raw/fd_raw`），顺手建在 `stg.` → `tests/test_collector_contract.py` 的 `sorted(stg 表集合) == 七 topic 契约` **立刻红**。
    那条断言是**契约守卫**（防 schema 漂移），不是障碍：**红是对的方向，改的是我**。已迁到独立 `raw` schema（`docs/db/infra_p0_3_raw_api.sql`），stg 回到 7 表、用例复绿。
    ⇒ 通用规矩：**任何新增 DB 对象，先问"会不会撞到既有契约断言"**；顺带的第二个好处——躲开 p0_2 里 `ALTER DEFAULT PRIVILEGES IN SCHEMA stg GRANT … TRUNCATE` 的继承陷阱（放 stg 会自动带上 TRUNCATE，得额外 REVOKE）。
    ⇒ 复跑口径：`PG 残留` 那一步现在打印 14 张（ref4+stg7+ops3，raw 两块不计入，因它 owner/grants 独立且只追加）；对象总数看 `select count(*) from pg_tables where schemaname in ('ref','stg','ops','raw')` = 16。
22. **`sudo -u postgres psql -f ~/league-v2/docs/db/x.sql` 必然 Permission denied**：`/home/ubuntu` 是 0750，postgres OS 用户进不来我家目录（`-f /dev/stdin` 也不行，procfd 有 ptrace 级限制）→ 跑法固定为
    `install -m 0644 <file> /tmp/ && sudo -u postgres psql -d league -v ON_ERROR_STOP=1 -f /tmp/<file>`。
23. **`ALTER DEFAULT PRIVILEGES` 会让"以后建的表"自动带权限** → 给某 schema 授过 `TRUNCATE` 之后，在该 schema 里新建的每一张表都会继承，事后想收紧必须**逐表 REVOKE**（§9-21 就是这么撞上的）。
24. **`ref.league.scope` 有 CHECK，值域是 `regular|irregular`，语义是"竞彩开售范围"不是"联赛/杯赛"** → 我 seed 五大联赛时写 `scope='league'` 被整条 INSERT 拒（`ON_ERROR_STOP` 下 rc=3，前五联赛一条没进）。五大联赛 ⇒ `'regular'`；`window_from/window_to` 留给 P3 开关制。
    通用教训：**seed 前先 `\d+ 表名` 看 CHECK**，别照草案语义想当然。
25. **同一个坑会在别人手里第二次出现——因为守卫只装在了一个地方**（2026-09-15 最重要的一课）：
    `pg.connect()` 是 **非 autocommit**，psycopg3 下**第一条 SELECT 就开隐式事务**；此后 `with conn.transaction():` 进去时状态已非 IDLE
    ⇒ **自动降级成 SAVEPOINT**，`RELEASE` 不是提交 ⇒ 最外层隐式事务永远没人 COMMIT ⇒ 关连接整体回滚。
    P0-BACKFILL1 真跑 15 次请求、日志逐条"落块 HTTP 200"、**库里 0 行、账本 0 格**（PQtrace 实测：`BEGIN×2 SAVEPOINT×4 RELEASE×4 COMMIT×0`）。
    STORE1c 给 `collector_pull._load` 加了 IDLE 断言，但**没把它变成公共不变式**，回填这条新路径又踩一遍。
    ⇒ 纪律：**凡是"逐条提交"的写路径，进事务前必须显式 `conn.autocommit = True` 或断言 IDLE**，两者必居其一，写进工单铁律；
    ⇒ 更硬的道理：**CLI 写路径的验收必须包含一次真跑 + "落库行数 == 发出请求数" 的对账**，光看单测绿＝没验。
26. **API-Football 免费档除了 100/天还有 10/分钟**（实测连发第 11 条起全 429）⇒ 两源统一 `PAUSE_S=7`；
    收到 429 **立即收工**（继续打只会把剩余配额打成 5 个 429）；429 **不重试**（重试只会加重）；
    ⚠️ "失败也落块"配 **表级 UNIQUE(params_hash)** 会让 429 **永久毒化**该请求（重跑命中缓存跳过）
    ⇒ 已改 **partial unique `(params_hash) WHERE http_status=200`**，代价是 `ON CONFLICT (params_hash) DO NOTHING` 这种写法**当场抛 `InvalidColumnReference`**（必须跟着改成带 WHERE 的目标）。
27. **队长改 DDL 之前要先算它会不会打断线上写路径**：p0_3 换 partial unique 之后，**上一单刚验收过的 `api_get.py` 立刻不可用**（ON CONFLICT 目标不匹配）。
    这不是 coder 的错，是我改 schema 的连带影响 —— 所以 DB 变更必须**同一轮内**跟着发一张改代码的单（已发 P0-BACKFILL1b）。
28. **队长的 DB 变更同样要过全套测试**：p0_4 建完 fact 之后必须复跑 `pytest tests -q`（fact 属新增 schema，不该撞到任何既有断言；真撞上了先怀疑自己而不是改测试）。
29. **`rc=0` + 无哨兵 ≠ 完成，也 ≠ 造假**：P0-BACKFILL1 try1 跑了 9 分钟、写出 `api_get.py`，收尾一个"压缩到 90 行"的编辑**工具执行 failed** → ACP 直接结束回合、进程 rc=0，但没写 `.done`。派工器判定正确（自动 try2）。
    ⇒ 判据永远是**哨兵文件**；但"没完成"和"骗完成"要分开看：看 trace 末尾有没有 `tool_call_update: failed`、有没有真把活干到一半留下文件。
    ⇒ **别把行数预算压得太狠**：我给 api_get 的 ≤90（规范本意 ≤100）逼得它最后两步全在"压缩"，一次压缩失败就吞掉整回合。以后：**默认 ≤100，需要更紧要在工单里写"宁可拆文件也别压缩"**。
30. **OMP 侧的编辑故障模式：`Tool was not executed because the run was aborted: Streaming edit preview failed.`**
    （2026-09-15 在 FACT1 try1 与 BACKFILL1 try1 各撞一次，都是**收尾的大段改写**；同 log 里 0 次发生于纯新建阶段）
    ⇒ 表现：进程 rc=0、**没写哨兵**、文件停在半路（这次 6 个文件已写出 4 个）。派工器重试即续上，**不用我干预**。
    ⇒ 缓解（写进工单铁律）：**改文件优先"整文件重写"而不是原地大 Edit**；一次改动别跨半个文件。
31. **`bigserial` 的坑：表权限不覆盖序列权限**（2026-09-15 实测，p0_5 第一版就中招）：
    给 `league_app` 授了 `INSERT ON TABLE`，但 `INSERT INTO analysis.ev_report …` 仍 **42501 InsufficientPrivilege** ——
    因为 `serial/bigserial` 背后是一张**独立 sequence**，`nextval` 要 **USAGE（或 UPDATE）on the sequence**。
    而 `GENERATED ALWAYS AS IDENTITY` 的身份序列由列拥有、随表授权 ⇒ **不受影响**。
    ⇒ 规矩：新表一律 `bigint GENERATED ALWAYS AS IDENTITY`（草案里的 bigserial 我已就地改造，表空时 `DROP DEFAULT + ADD GENERATED ALWAYS AS IDENTITY` 即可）；
    ⇒ 并且**默认权限要连 `ON SEQUENCES` 一起授**（`ALTER DEFAULT PRIVILEGES … GRANT USAGE, SELECT ON SEQUENCES TO role`），别等撞了再补；
    ⇒ 验收矩阵必须**真插一行带序列的表**才算过（我只测 SELECT/UPDATE/DELETE 是漏的）。
33. **写路径的 `run()` 必须返回"本批计数"，否则测试一定会被逼去读全局状态**（2026-09-15 一天内同类 bug 第 3 次，第 3 次才看清病因）：
    表象都是"派单时全绿、队长真跑一遍生产数据后测试转红"。三次分别是：① `test_backfill_plan` 断言"待取==30"（真回填后剩 71）；
    ② 同文件"发出 3 条 / 配额耗尽即抛"（真库已有缓存 ⇒ 0 请求）；③ `test_upsert_from_raw` 断言 `unmatched_fd(conn) == []`
    ——而 `unmatched_fd()` 的实现是"取 `ops.ingest_log` **最新一条**"，生产留痕 3051 条一进来，它读到的永远是生产数据。
    **根因链**：`upsert_*.run()` 只把"本批未对齐 N 场"打进日志、**不返回** ⇒ 测试想验证只能读库 ⇒ 读到的是全局 ⇒ 依赖真库状态。
    ⇒ 立规矩（以后每张写路径工单都要照抄这两条）：
      · **返回值即证据**：`run()` 返回 dict（`rows_in/rows_ups/fd_aligned/fd_unmatched/...`），日志只是它的渲染；测试断言返回值，不断言日志文本。
      · **读全局的函数必须能限定作用域**（`src_file=` / `fd_ids=` / `since=`），并在 docstring 标"不传参＝生产读法，测试禁用"。
      · 验收必含一步：**在真库已有存量的状态下复跑全量**（空库绿不算绿）；工单里禁止"先清表再测"（`league_ing` 也没 DELETE 权限）。
34. **展示名不能当身份键；`to_cn()` 这类"字符串→字符串"的翻译不是稳定主键**（2026-09-15 P0-MODEL1 真跑才暴露）：
    `ref.team UNIQUE(sport, name_cn)` + `name_cn = to_cn(源队名串)`，上游 AF 一改名（`Vfl Bochum`→`VfL Bochum`）就产生**同俱乐部两行**，
    症状不是报错而是**下游静默少数据**（德甲 2024 季 306 场只拟合预测出 132 场，跳过 57%）。⇒ 规矩：
    ① 凡外部实体（俱乐部/球员/球场/联赛）**一律以源站 id 为身份**，`aliases jsonb` 存各源 id，展示名单独一列；
    ② 用**存储生成列**把 jsonb 里的 id 提出来（`af_id bigint GENERATED ALWAYS AS (…) STORED`）再建 `partial unique`，下游 join 不用反复解 jsonb；
    ③ 认队顺序必须 **id 优先、name 兜底**，且命中 id 时**只并 aliases 不改展示名**（否则跨季来回翻）；
    ④ 这条只有"真数据 + 真跑一遍下游"能抓到：单测里的队名都是我写的常量，永远绿。⇒ 每张数据类工单的验收都必须含一次真跑。
    ⚠️ 配套坑：`jsonb_object_agg()` 在**空集**上返回 NULL，而 `jsonb || NULL` = NULL ⇒ 合并 aliases 的 UPDATE 会把整列洗成 null（我炸过一次，非空约束+事务回滚救场），**必须 COALESCE(…, '{}'::jsonb)**。
35. **真实成本量级**（trace 里 `usage_update.cost` 是本话术累计，不是单回合）：一个 4-6 文件的工单 ≈ **15 万 token / $0.10-0.17**；之前 §2 写的 "$0.0032/turn" 是单回合价，别拿它估算整单成本（差两个数量级）。
36. **包装层比被包装层更严格 ⇒ 潜伏缺陷只在包装层响**（2026-09-15 P0-MODEL1 真跑）：v1 内核 `tau_correction` 在 τ 变负时
    `max(0.0, τ)`（留下 0 概率格），v1 自己的消费端再用 `p > 0.0001` 静默丢格 ⇒ **从不报错**；而 v2 `derive/grid.py::renormalize`
    要求每格 >0 ⇒ 真实高 λ 场次（拜仁 3.78）一进来就当场抛。⇒ 规矩：① 发现"新旧口径不一致"先分清**谁在静默、谁在响**，
    静默的那个才是错的一方；② 修在**包装层**（可达域收缩 `rho_eff = min(rho, (1-floor)/(λ_h·λ_a))`，不触发时与旧行为逐格相等），
    **不动冻结内核**；③ 有效域参数要把**生效值落库**（`features.rho_eff` + `params.rho_clamped`），否则回测时说不清是谁改的；
    ④ 这类洞**只有真跑撞得出**（单测里的 λ 都是我按"常见值"写的）⇒ 每张 model/data 工单的验收必须含一次真库真跑，
    而且要**跑满全部 (联赛,赛季) 组合**——我只跑了 10 个里的第 1 个就没事，是跑到 bundesliga 2024 才炸的。
37. **汇总数字必须自带口径范围——"分组均值"不能顶替"全量"当标题**（2026-09-15 P0-BACKTEST1 验收时抓到）：coder 报告 §1 写
    "四玩法 hit_rate 全部高于均匀：had 0.4899…"，我独立重算全量是 **0.4772**——差的那 1.3pp 不是算法错，是他标题里用的是
    **拟合场（fallback=False，2412/3504）**那一组，942 场兜底场被标题悄悄排除（分组数本身是对的，`backtest_report` 也一直按组返回）。
    ⇒ 规矩：① 任何对外报的单一数字必须标"全量/某组"，且**先给全量再给分组**；② 验收时我自己的复算要**同时算两个口径**
    （全量 + 各分组），只要标题数落在分组里而报告没说，就算报告缺陷（不改代码，改报告并要求补口径）；
    ③ 同分时也要防"标题挑组"：分组维度（兜底/拟合、联赛、赛季）越多，越容易无意中挑出最好看的那组。
38. **派单前对"新建文件路径"做三项预检**（2026-09-15 P0-CONFIG1：coder 反过来纠了我两处，都对，见 `scripts/config.py` 的模块 docstring）：
    ① **同名预检**——我指定的 `scripts/core/config.py` 与既有 v1 模块 `core/config.py` 撞名（20 处 `from core.config import` 在用），
       照抄就会把 v1 的再导出层覆盖掉；② **冻结正则预检**——我自己的 `league-accept.sh` 把 `scripts/core/` 整段判 FAIL，
       等于要求 coder 去做一件必然验收失败的事；③ **CLI 跑法预检**——本仓约定 `PYTHONPATH=scripts python scripts/...`（从 repo 根），
       直接按路径跑任何 ingest CLI 都会 `ModuleNotFoundError`（这不是回归，v1 起就这样），工单里"队长另做"的复跑命令必须写全，
       否则 T 项会被环境噪声误判成失败。
    配套：推送用现成的 `~/bin/gh-askpass.sh`，别再现场 `printf` 造 askpass（我已两次栽在手写 shebang/替换位置上）。
39. **工人身份要查证据，不能只读配置**（2026-09-15 15:02 用户把 ACP 默认从 `deepseek/deepseek-flash` 换成 `Agnes/agnes-3.0-flash`）：
    ① `modelRoles.default` 只说明**下一单**用谁，不说明**过去**用谁；真实模型要看
       `~/.omp/agent/sessions/**/*.jsonl` 里逐条 `"model"` 计数（我实测 14:53 那单 63/64 条都是 deepseek-flash）；
    ② `agent.db → model_usage.last_used_at` **不可信**（它记 deepseek-flash 上次使用 09-14 22:00，
       而实际今天 14:53 还在跑）——别拿它做审计口径；
    ③ **换模型 = 换工人**：新工人第一单派**零设计自由度**的单（机械拆分/格式化这类），把它的纪律（守不守 §2-D7 行数红线、
       会不会顺手改逻辑、报告诚不诚实）当试金石；此后每个工单在 README §6 记录"本单模型"，验收证据才可归因；
    ④ 派工器**不带 `-m`**，所以想临时换工人只能改 config.yml（且会全局生效）——不要把模型名写进工单正文，
       那会造成"工单声称的模型 ≠ 实际跑的模型"。
40. **`oracle` 就是本机（NDORACLE）**：国内机的 rsync 目标 `oracle:/srv/league-staging/incoming/cn-collector/` **不需要任何网络跳板**，是本地路径。
    但 `incoming/` 是 `drwxr-x--- league:league`，而我的登录会话**没有 league 组**（`usermod -aG league` 要新会话才生效）⇒
    `ls` 直接 `Permission denied`。**读法固定为 `sg league -c '…'`**（把整段 python/heredoc 脚本先写到 `/tmp` 再 `sg league -c "python3 /tmp/x.py"`，别把 `~` 依赖塞进去）。
    写方向（archive 到 `done/`、`bad/`）同理，且**派给 coder 的工单里这三个目录必须做成参数**（coder 子进程同样没有 league 组，测试一律传 tmp 目录）。
41. **海外 IP 打 `webapi.sporttery.cn` 直连返回 `HTTP 567` + 反爬 HTML**（不是超时、不是 403）⇒ 远端**无法**自查"与官网一字不差"，
    §8.3 的"抽 10 行与官网肉眼核对"这项**只有国内机能做**。队长做核对应改为：复算 `src_hash`、跨批 diff、跨 topic 身份交集、键数对账——并在回传里明确写"请你们核官网，我这边被挡"，别把做不到的事当成已验收。
42. **换工人后要重测"单次超时"，判据是"有没有开始落盘"**（2026-09-15 实测）：`Agnes/agnes-3.0-flash` 接 P0-COLLECT1b，**21 分钟 0 个文件写入**（全程 `agent_thought_chunk` 在读和分析），到 `timeout 1200` 被 `rc=124` 杀掉、颗粒无收。
    ⇒ ① 新工人前几单的超时按下限 **2400s / maxtries 2~3** 给（老工人 1200s 够用，别照抄）；② 中途看一眼 `wc -l` 目标文件是否还在原始行数——**只思考不落盘就主动 kill 重来**（每次尝试都是全新会话、无记忆，等到超时等于全损），别舍不得；
    ③ 杀的时候要按 **pid** 杀：`pkill -f "omp acp"` 会**匹配到我自己的 bash -c 命令行**把自己杀掉（§9-17 的又一个变种：模式出现在我这条命令里就一定自匹配）。杀完必须再 `ps` 确认没有孤儿 `omp acp` 在写同一个工作树。
43. **验收路径必须指到"本单改动的文件"**（2026-09-16 我自己踩的）：`league-accept.sh <TAG> tests` 会连 v1 遗留大文件一起判违规
    （`tests/test_poisson.py` 175、`tests/web/test_m3_jobs.py` 353…共 19 条），把本单误判成"拒收"。§2-D7 的原文是「**新文件** ≤100 行」，
    遗留文件属于已排队的 P0-HYGIENE。⇒ 验收命令一律列明细路径；只有 `scripts/` 的**冻结区自伤检查**才需要扫目录。
    顺手记一条口径：本仓"改文件"也按 ≤100 行管（COLLECT1 把 `test_collector_contract.py` 从 100 写到 121 再回到 105，仍判违规）。
44. **机械拆分单最常见的新增缺陷是"顺手补一个断言"**（2026-09-16 COLLECT1b/Agnes：把一条测试拆成两条时，给其中一条加了
    `report["ok"] is True`，而 `run()` 返回体没有 `ok` 键 ⇒ `KeyError`，全量 427 passed / **1 failed**）。
    ⇒ 验收这类单时必须跑**全量** pytest，并对"一拆二"的用例做**语句级集合比对**（金标有效语句是否全部出现在两半并集里，只多不许少）；
      多了断言本身可以接受（前提是真键），**红了就退**。比对脚本思路：`ast.dump` 每条顶层语句，剔除纯 docstring/常量表达式后取集合差。
45. **慢工人（Agnes）身上"拆小单"是反效果**（2026-09-16 实测两轮）：它的耗时**几乎全在探索**（20+ 分钟读文件/找先例），写代码只占尾部；
    每次换会话都**从零重读**，所以拆成 2a/2b 不会省时间，只会把探索成本×2（2a 派下去 13 分钟 0 改动，还越界去读 `jc_write.py`，我把它杀了）。
    ⇒ 正确做法是**一张大单 + 队长把喂料做到极致**：① 真值全部算好写进工单（我算了 7 条期望值 + HHAD 让球线五档分布 + dash 条数 4）；
    ② **半成品代码的缺陷清单预先核实并点名到行**（`jc_write.py` 的 D1 参数数量必不匹配 / D2 `snap_ts` 没进 cols 但它是 PK / D3 查了不存在的 `ref.team.jc_id` / D4 死代码）；
    ③ 明确"继承不许推翻重写"+"越界即拒收"；④ `maxtries 3`、单次 2400s。判据：**同一分钟内既没读也没写的 drift 苗头（开始搜 CLI 入口而本单禁改 scripts）就杀**。
46. **工人修期望值时最爱犯的偷法是把断言松绑而不是算真值**：新夹具下 `len(dash)==2` 对不上，它改成 `len(dash) > 0`（还留着原 docstring）。
    ⇒ 验收"期望值修正"类改动时，**凡是把 `==` 改成 `>0/is not None/in` 的，一律要求给出实算数字**（我这边直接 `python3` 遍历夹具算出 4 条，写进下一单 D0）。
    反例提醒：同一次改动里它把 `all(sorted(blocks)==...)` 改成 `all(sorted(set(blocks))==...)` 是**正当的**（跨批变化行让 block 列表出现重复），不是所有改动都是偷——逐条看证据。
47. **派工链上的 `md5sum -c` 必须用绝对路径清单**（2026-09-16 19:10Z 踩）：清单是 `cd ~/bin && md5sum league-accept.sh …` 生成的（裸文件名），
    我在 repo 目录里 `-c` → "No such file" → 返回非零 → **`&&` 链断掉，派工根本没发生**，而我还以为在跑。
    ⇒ ① 清单里存绝对路径；② 派工后**必须**看 `.omp-logs/<TAG>.attempts` 有 `try 1/…` 才算真的发出去了（`sleep 5~8` 再读，别看空就下结论）。
48. **对 Agnes 这类"探索型慢工人"要用 `【第一动作】先写文件再读代码` 的写死式工单**（19:09Z 实测：P0-COLLECT2b try1 **40 分钟 0 文件改动**，
    全程在"算 oracle/读 logger/跑 pytest"；把它上一位留下的 `jc_write.py` 105 行原样放着没动，D0 那一处也没改）。
    ⇒ 新工单格式：🅐 第一动作（先 `new file` 写骨架，每写一个函数就跑一次 CLI）＋ 🅑 **只准读这几个文件的这几行**（并列"不许读"清单）
    ＋ 真值表全部队长算好（oracle 行数、缺陷点名到行）＋ 超时压到 1500s×2（**给它"没时间慢慢读"的压力**）。
    ⇒ **19:11Z 实测有效**：2c 下去 **55 秒就 `new file` 建了 `jc_load.py`**（前两单 40 分钟 0 动作），6 分钟内改完 `jc_write.py` 的四条缺陷
    （`jc_id`/`where_note`/死代码 `INT` 全部消失，我 grep 复验）。**代价**：25 分钟只走到"writer 修好 + CLI 空壳 + D0 没改"，仍没收尾 ⇒
    结论是**写死式工单能把 Agnes 从"只读不写"里拽出来，但换不来它变快**；预算仍要按"一单两段（1500s×2）"排。
49. **`psycopg3` 的 `sql.Literal(str)` 会把 WHERE 子句当"值"加引号**（2026-09-16 D5，**实测**：`sql.Literal(' WHERE a>=b').as_string(None)` → `"' WHERE a>=b'"`）：
    工人用它拼 `ON CONFLICT DO UPDATE ... {clause}` 时，语句会变成 `SET x = EXCLUDED.x ' WHERE ...'` ⇒ **每条 insert 必报语法错误**，
    但**AST/行数检查完全看不出来**（这不是风格问题，是运行时炸弹）。⇒ 以后凡是 DB 写人类的单子，验收加一条：
    `python3 -c "from psycopg import sql; print(sql.Literal(' WHERE 1=1').as_string(None))"` 先教育工人**动态片段只能用 `sql.SQL`**，
    并要求它在报告里**贴一条真跑成功的 insert 输出**（不是 pytest 的绿，而是 `rowcount`/`ingest_log` 那种落地证据）。
50. **工单里的"数据布局"必须队长自己 `find`/`stat` 过一遍再写**（2026-09-16 20:41Z 我犯的）：我按文档记忆把真包写成"批目录 + `<topic>.jsonl`"，
    实际是"根级 `<上传时刻>.done` + `<topic>/<采集分钟>Z__NNN.jsonl|"empty"`"，两者**没有任何可解析的关联**（`snap_ts` 还跨 topic 不同）
    ⇒ 派出去的 2f 蓝图是错的，工人 3 分钟就撞墙。发现后立即**杀掉重发**（改函数 1/2/5 签名与幂等键），并在 skill 里记下"这是队长的错"。
    ⇒ 通用规则：**给采集/落盘类工单写"输入形状"之前，必须用 `find -maxdepth 2`、逐目录 `ls`、和一段只读 python 把形状钉死**，
      并且把"名字对不上、时间对不上"这类**反例**也写进工单（否则工人会按常理猜，猜出来的 loader 最坏是静默错）。
51. **给工人的"兜底口径"绝不允许依赖文件 mtime**（2026-09-16 21:38Z，**工人把我这条写错了**）：我在 2f/2g 工单里写"数据文件 `mtime ≤ .done` mtime 即属该批"，
    工人 `stat` 实测**包内所有 `.done` 与全部数据文件 mtime 完全相同**（15:38:26 = 我方解包时刻，被搬运抹平）⇒ 用 mtime 会把**三批全塞进每一批且不报错**。
    它改用**文件名时间戳窗口 `(t_{i-1}, t_i]`**，我复核与三批真实分布逐条吻合 ⇒ 采纳，并把实证写进回传文档 G 节。
    ⇒ 通则：**任何"批归属"必须来自可解析内容（名字/清单/表内键），不许来自文件系统元数据**；队长写"兜底口径"时先 `stat` 一遍再说。
52. **`Agnes` 的真实工作剖面**（夜里 7 次派工）：① **点名到行的修复 7/7 全对**（D0~D6 逐条 grep/pytest 复验）；② **新模块 0/5 落地**，
    瓶颈**不是读代码**（2g 禁止读代码，它仍花 **24 分钟纯思考**才落笔，trace 5.3MB 全是 `agent_thought_chunk`、**0 次工具调用**）；
    ③ 但它会在思考期间**做真实测量**（`inspect.signature` 读接口、`stat` 查 mtime、跑只读 psql），**这些测量能推翻队长的错误设定**——这是它比"照抄工单"更值钱的地方。
    ⇒ 队长下结论时**不要只算"写了多少行"**，还要看"它测出的东西对不对"；派工预算按 **2400s 单次 + 全内联材料** 起，别用 1500s×2。
53. **Python 3.11 的 `datetime.fromisoformat` 对 `2026-09-15T15-16-32` 这种串「不报错而是静默给错值」**（2026-09-16 22:31Z 队长实测）：
    它会吃 `T15` 当小时，然后把 **`-16-32` 当成 UTC 偏移** ⇒ 返回 `2026-09-15 15:00:00-16:32`（带负时区的错时间）；
    只有当偏移超出 ±24h（如 `-40:02`、`-35:00`）才抛 `ValueError: offset must be a timedelta strictly between ...`。
    ⇒ 凡"从**非标准**文件名时间戳反解时间"，工单里必须写死：**取出整数自己 `datetime(y,mo,d,h,mi,s)` 构造**，并附一张
      输入→输出对照表让工人逐条打印自证；**只写"用 fromisoformat"的工单＝埋静默错的雷**（这次三批全部 `ups=0` 就是它，
      而且如果包名刚好落在合法偏移区间，连报错都不会有，直接把批归属算错）。
54. **验收 `sql.*` 拼装时必须逐参数看渲染结果，不能只挑一处**（2026-09-16 22:45Z，工人替我补了第二颗雷）：
    我抓到了 `sql.Literal(where_clause)`（D5），却漏了同一函数里的 `sql.SQL(", ").join(map(sql.Identifier, updates))`——
    `updates` 每项是 `"col = EXCLUDED.col"` **整句**，被 Identifier 一包就成 `SET "col = EXCLUDED.col"` ⇒ PG 语法错（E2）。
    ⇒ 通则：**动态 SQL 片段一律 `sql.SQL`，只有裸标识符才用 `sql.Identifier`**；验收时用
      `python3 -c "from psycopg import sql; print(...as_string(None))"` **把整条语句渲染出来读一遍**（我 D5 就是这么抓的，但只渲染了 WHERE 那一小段）。
55. **工人"越界之前先报告"是可以被制度激发出来的**：2j 的边界条款写的是"跑不出 oracle 就贴 count 原样 + 取证 + 停下"，
    结果它**没有**为了让 T1 变绿去偷改 `jc_load.py`/`jc_write.py`，而是用只读探针取证出 E1/E2 两条我漏的缺陷、**并且没写 TASK_DONE**。
    ⇒ 下一单我直接把两行修法写进工单（`2k` 就是纯放行单，1200s）。**"能取证 + 敢停工"的工人比"能修好"的工人更省心**：
      工单里要永远留着这条出口，否则慢工人会用改别人的代码来换 count 好看。
56. **建 FK 之前必须实测两侧键集的包含关系**（2026-09-16 23:31Z，队长的 DDL 被自己的常识绊倒）：
    `fact.jc_result.match_id FK → fact.jc_match.match_id` 看着天经地义（"赛果当然来自开售清单"），
    实测**在售 17 场与赛果 15 场的 matchId 交集 = 0**（竞彩语义里 `jczq_offer`=未开售、`jczq_result`=已完场，两拨不相交）
    ⇒ 装载器修完 E1–E6 之后仍然全批 rollback，报 `ForeignKeyViolation`。
    ⇒ 规矩：**任何新 FK 落地前，先用真包跑一次 `select count(*) from 子侧 where key not in (母侧)`，非 0 就不许建**；
      需要连接语义就用"逻辑连接 + 查询期 join"，不要拿约束替业务建模。DDL 是队长的活，**这类错不会算到工人头上，但会吃掉一整晚**。
57. **慢模型的正确用法：把"取证"外包给它、把"决策"和 DDL 留在自己手里**（2m/2l/2n 三单连续验证）：
    工人连续三次在**权限边界内**用只读探针取证出我漏掉的缺陷（E2 SET 子句、E3 Identifier 包点号、E4/E5/E6 列级），
    每次都**没有偷改别人的文件、没有为了让数字好看造数据、没绿就不写哨兵** ⇒ 这是因为每张单都写了同一条出口：
    **"跑不出 oracle 就贴 count 原文 + 取证 + 停下"**。⇒ 派工模板里这条出口是**必需品**，不是可选项。
58. **工单里的 oracle 必须写成"增量"而不是"全表 count"**（2026-09-16 23:43Z，我在 2o 里差点又埋一个坑）：
    `jc_load.py` 末行打印的是**全表 count**，而库里已经装着 5 批真数据 ⇒ 任何改动复跑后 count 都是 `17/250/15`，
    **一个坏改动也能交出"count 一致"的假绿**。⇒ 装载类工单的验收数字要用**每批 `ups=` 增量**（`batch <marker> ups=N errors=[]`）
    + **`ops.file_arrival` 里该批的具体行数/路径形态**，这两个才与"库里已有多少数据"无关。
59. **改口径要连着改自己的检查脚本**（同一夜）：`~/bin/v2b-check.sh` 的 `ORACLE` 与三处标签写的是"两批 34 行/玩法、snap_ts=2"，
    真包涨到 5 批后它开始打印"期望 34、实际 50"这种**自我矛盾的输出**。⇒ 每次数据规模变化，**先改工具的期望值再派单**，
    否则工人会拿我的过期期望当标准来"修数据"。同类：`jc-fk-audit.py` 第一版把复合外键的子查询写成了
    `select (a,b) from t`（= 1 个 row 值 ⇒ `subquery has too few columns`），以及"扫到 0 条约束就报全部通过"的**假绿**——
    现在两条都修了，并且**没扫到任何外键时 exit=2**（把"没扫到"和"通过"分开）。
60. **算 oracle 必须"顺着被验收函数自己的语义"算一遍**（2026-09-17 00:04Z，DASH1a 里我第 4 次给出错期望）：
    我在工单里写 `fixtures_on(None) → 85 行`，理由是"17 场 × 5 玩法"；但那个函数的 `None` 分支是
    `business_date = (select max(business_date) …)` ⇒ 真口径是"**最新一个营业日**的场次" = 8 场 ⇒ **40 行**（库里另一日 9 场 = 45 行）。
    工人**没有**按我的 85 去改代码，它按 40 交出并写明差异 ⇒ 这是 §9-55 那条出口救回来的第 4 次。
    ⇒ 规矩：**凡是带"缺省/最新/默认"分支的函数，oracle 要用与该分支完全相同的 SQL 先跑一次**，
      并且工单里必须把"这个数是怎么来的"写成一句可复核的 SQL，而不是只写一个数字（数字无法自证，SQL 可以）。
    同类复发历史：`#MISSING` 我写 5（真 8）、fixtures 我写 85（真 40）——**都是"我记得"而不是"我此刻查了"**。
61. **"重算一遍 oracle"必须把业务规则一起算进去，否则新算出来的错数比旧错数更危险**（2026-09-17 00:20Z，传统足彩 2e）：
    我 00:12 用真包重算，得到 `jc_issue=4 / jc_issue_match=38`，据此准备推翻工单里旧版的 `7 / 62`。
    差在哪：① **合成父行** —— `jc_issue_draw` 的 3 个 `(game_num,issue_no)` 与期头侧 **交集为 0**（开奖都是上一期号），
    而 `fact.jc_issue_draw → fact.jc_issue` 有复合 FK ⇒ 不合成 3 条 `raw_head.head_source='jc_issue_result'` 的父行就整批违反外键（4+3=**7**）；
    ② **双来源展开** —— `matchList` 在 `jc_issue`（38）与 `jc_issue_result`（24）**两侧都有**，只按一期头展开就少 24 行（38+24=**62**）。
    ⇒ 规矩：**oracle 必须写成"可复核的推导链"**（哪来的数、按哪个 PK 去重、有没有第二来源、FK 是否需要补父行），
      光写一个数字（哪怕是刚测的）都不算数；旧版工单那两个数这次是**对的**，我差点用"新测"把它改错。
    附带事实（都实测过、别再猜）：`jc_issue_prize` **恒 0**（`prizeLevelList` 12 期全空数组）；开奖侧 `matchList` 的
    `result/czScore/czHalfScore/a/d/h` **全为空串** ⇒ `official_result/cz_score/cz_half_score` 只能落 NULL、`is_drawn` 全 false；
    `gmMatchId` **只有期头侧有**（114 个）；`startTime` 是纯日期（210/210）；`matchNum` 恒等于 1-based 下标（114/114）。
 62. **逐批期望值必须"每一批各自现算"，不许拿上一批的形状外推**（2026-09-17 01:04Z，COLLECT2o 的 E3，队长第 6 处规格错）：
     我在 E3 写"实时五批各 `ups=49`"，实际是 `23-01 / 23-03 / 23-13 / 00-03 = 40`、从 `00-13` 起才 `= 49`——
     差的正好是那几批的 `jczq_result` 是 **`.empty`**（那一刻没有已完场场次），而我看了两批有赛果就外推成"每批都带 9 条赛果"。
     ⇒ 规矩：凡是"**逐批 / 逐文件**"的期望，一律**从 `.done` 清单第二列 `awk` 现算成一张表**贴进工单
       （`awk -F'\t' '$1 ~ /^jczq_result\//{s+=$2} END{print s+0}' "$m"`），并在表旁写清"**为什么这几批不一样**"
       （`.empty` 是正常输出、不是缺档 ⇒ 别把 `.empty` 算成 gap）；这次是**工人自己算对、把我的数纠回来**，
       代价是它 3 分钟 + 我一轮返工 —— 说明"**外推出来的错期望一定会被真数据撞破**"，早点现算省事。
     同批实测事实（别再猜）：落港目录**每 10 分钟准时多一个 marker**（00:33 → 00:43 → 00:53 我三次当场看见）；
     `jclq_offer` 在 23:01 之后**每一批都是 `.empty`**（休赛期官方无盘）⇒ 篮彩眼下只有 result 有数据，别指望 offer。
 63. **工人跑到一半被 kill 过、或验收期间它还在改文件 ⇒ `ops.*` 里可能留着"未完成代码"写下的脏行，验收结束必须回查一遍**
     （2026-09-17 01:07Z，COLLECT2o 验收现场，队长自己发现的，工人报告里不会有）：
     我 01:05 从库里看到 `arrival 119 / gaps 14`（上一刻还是 99/8），多出的 **6 条 `2026-09-15T23-01-30Z/…#MISSING`** 一查就是假的：
     `23-01` 的 `.done` **明明列了 7 个 topic**（其中 2 个是 `.empty`）。我用 `python -c` 直接调**当前** `files_for_batch()`
     打印七个 topic 的归属 ⇒ **全部正确**（`.empty` 落 `empty` 不落 missing）⇒ 结论：那 6 行是 **00:59:23 那一刻代码还没写完时跑出来的一次**。
     ⇒ 三条规矩：
       ① **判"归属对不对"不要靠重跑装载器**（会写库、会撞车），用 `PYTHONPATH=scripts python - <<PY` 直接调函数打印返回值 —— **纯读、秒出、可与清单逐行对**；
       ② 装载器的 `#MISSING` 是 `INSERT`，**后面正确的跑不会把它撤销**（PK 是 `topic/src_file`，与真文件的 `src_file` 不同名）
          ⇒ 伪 gap 会**永久留在 `ops.file_arrival`**，只能**超级用户 `delete`**（`league_ing` 故意没有 DELETE 权限，这不是它的活）；
          这次我删前拍数、删后核对：`119/14 → DELETE 6 → 113/8`，剩下 8 条全是老三批（0 字节 marker 走窗口）**真缺**，逐条点过名；
       ③ 每次验收 ingest 类工单，末尾加一句 `select src_file from ops.file_arrival where src_file like '%#MISSING%' order by 1`，
          **数一下 gap 是不是只减少了没增加** —— 这一条我原先的 oracle 里没有（只写了"count 不许下降"），所以差点漏掉。
64. **"工人 15 分钟零写入"的第三种解释：ACP 会话在长思考里静默死亡**
     （2026-09-17 10:07 北京，`P0-COLLECT2q` 连炸三次之后才看清）：
     我先按"它只会读不会写"下结论 ⇒ 把工单从"行为描述"改成"内联骨架"再改成"内联整个函数 + 禁止先跑基线"，
     三次尝试分别 12 / 14 / 2 分钟、**全部零写入**。第四次去看进程和日志才发现真相：
     `.attempts` 记 `try 1 rc=0 end=…`、日志尾巴是**我包装器自己写的 `[ACP 无返回]`**，而且**三次都有这一行**
     ⇒ **omp 的 ACP 会话在生成中途断流，`omp-call` 正常退出（rc=0），我 `max_tries=1` 于是直接 EXHAUSTED。**
     附实测：死亡时 `usage_update: size=524288 used=29443` ⇒ **不是上下文撑爆** ⇒ 所以"把工单写得更短"根本救不了它。
     ⇒ 三条永久规矩：
       ① 诊断顺序固定：**`.attempts` 的 rc/end → 日志尾有没有 `[ACP 无返回]` → 才回头怪工单写得不清楚**
          （我今晚先怪了工单两轮，白拆两遍工单，还在报告里错怪了模型）；
       ② 派工 **`max_tries≥3`**：**只认 `.done` 哨兵，`rc=0` 绝不等于成功**；会话死亡是概率性的，重派比重写便宜；
       ③ 重派前必须验工区干净：派工器新增 `LEAGUE_WATCH_PATHS="scripts/ingest …"`，
          **只检工单授权可写的路径**（别检全仓 —— `predictions/*.json`、我自己的 `tickets/`、`docs/` 常年是脏的，
          我第一版就是全仓检查，被 `ai_scores.json` 误伤成 `DIRTY-ABORT`）；脏就 `exit 2` 交回队长看 diff，
          **绝不允许新尝试在"半个文件"上续写**（这正是 §9-63 那批伪 gap 的成因）。
65. **建了表却没把 DDL 文件提交进 git ⇒ 环境不可重建，而且当场发现不了**
     （2026-09-17 10:36 队长自查发现：`fact.jbq_match / jbq_offer / jbq_result` 三张表在库里活了两天、有数据、被工单当靶子用，
     但 `docs/db/` 里**根本没有** `infra_p0_10_jbq_tables.sql` —— 我当时是在 `/tmp` 里执行完就直接开工单，文件没落进仓库）。
     危害不是"少个文档"：① 换机/重建库会**少三张表**，装载器上线才炸；② 表形状只能靠 `information_schema` 反查，
     于是**任何"列名写错"类验收（`jc-cols-check.py`）都在拿现状当规范**，等于没有规范；③ 我自己写工单时的"列清单"就变成口述。
     ⇒ 三条规矩：
       ① **DDL 与执行必须同一提交**：`psql -f docs/db/xxx.sql` 之前那个 commit 就得包含这个文件（不是执行之后再补）；
       ② 新工具 **`~/bin/jc-ddl-audit.py`**：拿 `information_schema.tables` 全量基表逐张去 `docs/db/*.sql` 里找 `create table <schema>.<表>`，
          **缺一张就 exit=1**；已反证过（把补回来的文件临时挪走 ⇒ 准确报出那三张、exit=1；放回 ⇒ 38/38 exit=0）；
          ⇒ **每次验收 DDL 类工单、以及装 cron 之前跑一次**。
       ③ 反向补文件之后必须**证明它可信**：把 `fact.` 换成临时 schema 在**一个 `begin … rollback` 的事务**里重放，
          比对"表数 / 约束数 / 列数"与运行库一致（我这次是 **3 / 19 / 61** 两边全等），才准写"已核对"。
