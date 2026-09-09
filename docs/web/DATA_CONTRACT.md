# DATA_CONTRACT — 引擎数据契约（M0 勘察）

> 本文件是 web 层（M1–M4）唯一的数据口径依据。
> 勘察方式：静态读代码 + 读现有 JSON 样本；**未运行 `scripts/predict.py`**（保护免费 API 配额）。
> 所有结论附证据：文件路径+行号 或 JSON 样本片段。
> 状态：M0a 完成第 1–4 节；第 5–8 节留待 M0b。

## 1. CLI 全景

入口：`scripts/predict.py`（Python 3 CLI，argparse）。启动时 self-insert 脚本目录与仓库根进 `sys.path`，故 `ai/` 包与 `core/` 均可导入（scripts/predict.py:21-26）。

### 1.1 全部参数（scripts/predict.py:51-77）

| 参数 | 默认 | 取值 | 作用 |
|---|---|---|---|
| `--league` | `epl` | `LEAGUE_CONFIG` 的 key | 指定单联赛；与 `--all` 互斥（`--all` 优先） |
| `--all` | False | flag | 遍历 `LEAGUE_CONFIG` 全部联赛逐一运行；stdout 输出**组合 JSON 数组**（predict.py:431-444） |
| `--data-source` | `""` | `football-data` / `espn` / `api-football` | 覆盖联赛默认数据源；空串＝按联赛配置（LEAGUE_CONFIG） |
| `--monte-carlo` | False | flag | 启用蒙特卡洛模拟，结果写入 `output["monte_carlo"]`（predict.py:311-325,343-344） |
| `--n-simulations` | `DEFAULT_N_SIMULATIONS` | int | 蒙特卡洛迭代次数，默认值见 core/constants.py |
| `--backtest` | False | flag | 回测：**先** `_save_output` 落盘预测文件，再 `backtest_with_live_results`，结果写入 `output["backtest"]`（predict.py:370-374） |
| `--cleanup` | False | flag | 调 `cleanup_old_files(days=7)` 后**直接 return**（不跑预测，predict.py:417-419） |
| `--dates` | 无 | `YYYYMMDD-YYYYMMDD` | 指定数据窗口；缺省为 BJT「今天-明天」（predict.py:424-429） |
| `--no-fetch` | False | flag | **语义误导**：实际 `events=[]` 空列表（predict.py:82-84），并非读本地缓存；warning 建议改用 `--data-source football-data`（该源仍联网） |
| `--no-dc` | False | flag | 禁用 Dixon-Coles（`use_dc=False`，rho 不拟合） |
| `--update-rankings` | False | flag | 强制刷新 FIFA 排名（`:force_refresh`，predict.py:264） |
| `--train-ml` | False | flag | 训练各联赛 ML 模型后**直接 return**（不跑预测；仅 stderr 打印结果，predict.py:404-415） |
| `--no-ml` | False | flag | 本轮禁用 ML 概率混合（`ML_CONFIG["enabled"]=False`，predict.py:400-402） |
| `--dashboard` | False | flag | 额外生成静态 HTML：`predictions/dashboard_{league}.html`（predict.py:360-367） |

### 1.2 执行流与副作用（run_league，predict.py:233-387）

按序副作用：

1. **抓取+解析**（`_fetch_and_parse`）：产出 `(events, past, future, in_prog)` 四列表（predict.py:250）。
2. **历史累计**：`core.calibration.append_historical_past_matches(league_key, past)` 把已结束比赛写入历史文件（predict.py:253-259）——**每次运行都会写历史累计文件**（路径见 §4）。
3. **ELO**：抓 FIFA 排名 → 更新/初始化 ELO 评分表（predict.py:262-264）。
4. **校准**：`build_calibration` + `compute_calibration_offset`，可能**改写** `PREDICTIONS_DIR/pred_calibration.json`（predict.py:123-130, 178-181）。
5. **写预测文件**（主线必写，predict.py:380）：`PREDICTIONS_DIR/prediction_{now_utc:%Y-%m-%d_%H}.json`（predict.py:171-176），详见 §3。
6. **stderr 摘要**：`_print_summary` + `Total runtime: Nms` + 60 个 `=` 分隔线（predict.py:381-385）。

提前退出分支（**不落盘**——直接 `return output`，无 `_save_output` 调用，predict.py:266-289，返回对象仅存在于内存或被 `--all` 收集进 stdout 数组）：
- 窗口内无任何比赛：返回 `status="no_matches"` 的空 output（predict.py:266-274），`calibration={"note":"no data"}`。
- 无未来比赛且非回测：返回 `status="no_future_matches"` 的 output，附 `reconciliation`（若可对账）（predict.py:276-289）。
- `--train-ml` / `--cleanup`：main 内直接 return（predict.py:404-419），**不落盘预测**。

注意：现仓 `predictions/` 下存在 status=no_future_matches 的 `prediction_2026-07-21_10/11.json` 文件，与现版「不落盘」行为矛盾 → 推断为旧版代码产物（§3.2/§9 疑点）。

`--backtest` 落盘细节：`_save_output` 被调用**两次**——先落盘供 `backtest_with_live_results` 读取（predict.py:371），随后主线第 380 行再落盘一次（此时 output 已含 `backtest` 字段）。**最终磁盘文件含 `backtest`**。

### 1.3 stdout/stderr 约定

| 模式 | stdout | stderr |
|---|---|---|
| 单联赛（非 silent） | 整个 output 的 JSON（`indent=2, ensure_ascii=False`，predict.py:377-378） | logger 日志 + 摘要 + 计时 |
| `--all` | 各联赛 output 组成的 **JSON 数组**（predict.py:444）；每联赛分隔横幅走 stderr | 同上 |
| `--train-ml` | 无 | `league: trained/skipped` 逐行 + logger |
| `--cleanup` | 无 | logger 清理日志 |

注意：`--all` 与单联赛 stdout **形态不同**（数组 vs 对象）；单联赛模式下若 stdout 被消费为「CLI 产物」，`--all` 需要按数组解析。此点已记入 §9 疑点清单（web 层子进程捕获 stdout 时需分支处理）。

## 2. 预测 JSON schema

样本：`scripts/predictions/prediction_2026-07-21_13.json`（status=ok，8 条预测，证据见下引行号）；两个空文件 `prediction_2026-07-21_10/11.json`（status=no_future_matches）由旧版代码产出，现版已不落盘（见 §3.2 疑点）。

### 2.1 顶层 keys（组装代码：predict.py:328-357）

| key | 类型/可为空 | 说明 | 证据 |
|---|---|---|---|
| `generated_at` | str ISO8601 带时区 | BJT 时间戳（`+08:00`，误解见 §3） | predict.py:280,329；样本:2 |
| `data_window` | str `YYYYMMDD-YYYYMMDD` | 查询窗口 | predict.py:280,329 |
| `status` | str | `ok` / `no_matches` / `no_future_matches` | predict.py:270,281,330 |
| `league` | str | `LEAGUE_CONFIG` key（epl/csl…） | predict.py:281,330 |
| `tournament_type` | str | 联赛配置 `tournament_type`，默认 `league` | predict.py:245,330 |
| `data_source` | str 可空 | `--data-source` 原始串（未映射） | predict.py:331 |
| `dixon_coles_enabled` | bool | 是否启用 DC（`--no-dc` 时 False） | predict.py:332 |
| `dixon_coles_rho` | float 可空 | 拟合 ρ；未启用时为 None | predict.py:333 |
| `calibration` | dict | 窗口内完赛统计；无赛时 `{"note": "no past matches to calibrate from"}`（calibration.py:257） | predict.py:334 |
| `calibration_offset` | dict 可空 | 30 天历史修正因子；样本不足 5 场为 null | predict.py:334,166-167 |
| `past_matches` | list | 已结束比赛数组（schema 见 §2.3） | predict.py:335 |
| `predictions` | list | 预测数组（schema 见 §2.2） | predict.py:335 |
| `timing_ms` | dict `{total:int}` | 耗时毫秒（仅 status=ok） | predict.py:336 |
| `reconciliation` | dict 可空 | 仅在 `reconcile_predictions` 命中时出现（predict.py:339-341） | |
| `monte_carlo` | dict 可空 | 仅 `--monte-carlo`（predict.py:343-344） | |
| `backtest` | dict 可空 | 仅 `--backtest`（predict.py:373） | |
| `accuracy_summary` | dict 可空 | `{7d:..., 30d:...}`；`league_accuracy` 有空值或异常时缺省（predict.py:347-357） | |
| `message` | str 可空 | 仅 `no_matches`/`no_future_matches` 分支 | predict.py:272,283 |

**「每联赛每文件还是一次运行一个文件」：已实证，阶段 1（M0a）结论——文件名不含 league，任何一次 `run_league` 写 `prediction_{now:%Y-%m-%d_%H}.json`。`--all` 时多联赛共用同一文件名互相覆盖，只留最后一场联赛的 output（详见 §3.3 覆盖规则）。web 层若按联赛取数，此 schema 不可用，须改 `run_league` 文件名带 league 后缀（记入 §9 疑点清单）。**

### 2.2 `predictions[]` 逐场字段（predict_py 组装 + core/predictor.py 计算）

样本以 `prediction_2026-07-21_13.json:16-91` 为例（第一条 Qingdao Hainiu vs Tianjin Jinmen Tiger）：

|| 字段 | 类型/可为空 | 含义 | 证据 |
|---|---|---|---|
| `match` | str | **英文队名串**（LLM 不可用时回退）；为预测与赛果回填的**关联键**（predict.py:156；backtest.py:49 用 `p.get("match")` 对账） | 样本:88；parse.py:258/280-281；i18n.py:103-110 |
|| `home` / `away` | str | **英文队名串**（LLM 不可用时回退） | 样本:89-90；parse.py:280-281；i18n.py:103-110 |
| `direction` | str | 中文方向如 `"Qingdao Hainiu 胜 (接近)"`；平局含「平」/「平局」子串 | 样本:17；backtest.py:58 |
| `stars` | str | 置信级别 `"1-star"`…（星级体系，值域见 predictor.py THRESHOLDS 相关逻辑） | 样本:18 |
| `confidence_score` | float | 0-1 置信分 | 样本:19 |
| `predicted_score` | str `"H-A"` | 最可能比分 | 样本:20 |
|| `poisson_top3` | list[{score:str, prob:float}] | 前三最可能比分及概率（概率和 < 1，仅 Top3 子集） | 样本:21-34；predictor.py:268/282 |
| `lambda_home` / `lambda_away` | float | 泊松期望进球 | 样本:35-36 |
| `lambda_home_ci95` / `lambda_away_ci95` | list[float,float] | 95% 置信区间 | 样本:37-44 |
| `over_under` | str | `"Over 2.5"` / `"Under 2.5"` | 样本:45 |
| `btts` | str | `"Yes"` / `"No"`（双方进球） | 样本:46 |
| `dixon_coles_used` | bool | 本场是否用 DC | 样本:47 |
| `dixon_coles_rho` | float | 本场 ρ（=fitted_rho） | 样本:48 |
| `dixon_coles_league_rho` | float | 联赛默认 ρ（LEAGUE_DC_RHO） | 样本:49 |
| `onside_signals` | dict | `{home:{fifa_rank,fifa_score,league_footprint,host_advantage,confederation,onside_score}, away:{...}}` 6 字段全为数值 | 样本:50-67 |
| `confidence_note` | str 可空 | 置信说明，通常 null | 样本:68 |
| `odds_data_available` | bool | 是否获得赔率数据 | 样本:69 |
| `reasoning_factors` | dict | 14 个数值字段：`home/draw/away_ml_true_prob`、`home/away_form_score`、`home/away_record_score`、`spread_movement`、`home/away_onside_score`、`home/draw/away_prob_weighted`、`elo_home_expected`、`raw_lambda_home/away` | 样本:70-87 |

**版本漂移提示**：predictor.py:342-343 的返回 dict 还含 `ml_model_used`（bool）与 `ml_proba`（list 可空）两字段，样本 13 无此二字段 → 样本由旧版生成，或该次运行 ML 未启用且字段被裁剪。web 层按此 schema 消费时应把这两个字段视为「可能缺失」（详见 §9 疑点）。

AI 反馈注入：`adjust_prediction(pred, ai_adjustments)` 按联赛加载（predict.py:303,160-161），可能改写上述字段（详见 §5 M0b）。

### 2.3 `past_matches[]` 字段（parse.py:314-368 构造成员）

样本 `prediction_2026-07-21_10.json:20-56`：

| 字段 | 类型/可为空 | 说明 |
|---|---|---|
|| `name` | str | **英文队名串** `"Away vs Home"`（`to_cn` 翻译不可用时回退英文） | 样本10:22；parse.py:258 |
| `status` | str | `STATUS_FULL_TIME` 等 ESPN status name |
| `completed` | bool | |
| `kickoff_utc` | str ISO8601 `...Z` | **UTC** 时间（parse.py:271 从源数据解析） |
| `time_to_kickoff_h` | float | 相对 now 的小时差（负=已过） |
|| `home`/`away` | str | **英文队名串**（`to_cn` 翻译不可用时回退英文） | 样本10:27-28；parse.py:280-281 |
|| `home_en`/`away_en` | str | 源数据 displayName（英文） | 样本10:29-30；parse.py:335-336 |
| `home_abbr`/`away_abbr` | str | `UNK` 表示未知 |
| `score` | str `"H-A"` | 完赛比分 |
| `home_form`/`away_form` | str | W/D/L 串（parse.py:214） |
| `home_form_score`/`away_form_score` | float | 0-1 形态分（parse.py:213） |
| `home_record`/`away_record` | str | `"W-D-L"` 汇总（parse.py:218） |
| `home_record_score`/`away_record_score` | float | |
| `ml_home_close`/`draw_ml` | float 可空 | 钱线赔率（parse.py:296-297 取 `moneyLine`） |
| `home_ml_implied`/`draw_implied` | float 可空 | 隐含概率 |
| `home_true_prob`/`draw_true_prob`/`away_true_prob` | float 可空 | 无赔率时为 null |
| `spread_home_line`/`spread_home_close_odds` | str | 让球线/赔率（无则为空串） |
| `spread_movement_score` | float | 让球移动分 |
| `total_over_close`/`total_under_close` | str | 大小球盘口 |
| `odds_data_available` | bool | |

### 2.4 `calibration` 字段（build_calibration，calibration.py:278-289）

`total_matches/home_wins/draws/away_wins`（int）、`home_win_rate/draw_rate/away_win_rate`（float 0-1）、`favored_by_odds/favored_won`（int）、`odds_accuracy`（float）。样本:8-19。无赛时 `{"note": "no past matches to calibrate from"}`（calibration.py:257；样本 13:11-12）。

`calibration_offset`（compute_calibration_offset，calibration.py:221-232）：`home/draw/away_correction`、`onside_home/away_correction`（float，钳位 [0.5,2.0]）、`sample_size`（int）、`sample_weight`（float）、`actual_home/draw/away_rate`（float）。持久化在 `references/.calibration_state_{league}.json`（calibration.py:15-18,235）。

## 3. 文件命名与时区

### 3.1 谁生成、何时覆盖

预测文件由 `_save_output` 写 `PREDICTIONS_DIR/prediction_{ts}.json`，`ts = now_utc.strftime("%Y-%m-%d_%H")`（predict.py:171-172）。**注意：函数参数名 `now_utc` 是误导，实际传入的是 BJT 时间**——`main()` 中 `now_bjt = datetime.now(timezone(timedelta(hours=8)))`（predict.py:422），且在 `--all`（predict.py:438）和单联赛（predict.py:446）中都以 `now_bjt` 作为 `now_utc` 实参传入。故：

- **文件名时间戳是 BJT**（`prediction_2026-07-21_10.json` = BJT 7月21日10点）。样本文件落在 `scripts/predictions/` 而非仓库根 `predictions/`（`PREDICTIONS_DIR` 解析为 scripts 下目录，见 core/config.py——M0b 确认）。
- **`generated_at` 同样是 BJT**（predict.py:280/329 `now_utc.isoformat()`，样本:2 为 `+00:00` 疑为旧版或 `_save_output` 参数不同，见 §3.2）。
- **同小时内重复运行**：`ts` 粒度到小时，同小时第二次运行**覆盖**同文件名（predict.py:171-172 直接 open w）。

**`--all` 覆盖规则**：所有联赛共用同一 `now_bjt`，`_save_output` 写同一文件名，后跑的联赛覆盖先跑的（predict.py:431-444），最终磁盘只留 **最后一个** 联赛的 output；`--all` 的数组只在 stdout 打印，不落盘。

样本 `2026-07-21_10`（status=no_future_matches，BJT 10:57 生成，`data_window=20250101-20250103`）与 `_11`（BJT 11:03）**同日同小时级别冗余共存**，且 10/11 两个空文件都在 `_13`（status=ok）之前生成——三者非同一小时故不覆盖；10 与 11 是不同小时的两份独立空输出。此样本集无法回答「同一小时多次运行是否覆盖」，但因时间戳粒度到小时，理论上会覆盖（见 §9 疑点）。

### 3.2 样本 `generated_at` 时区矛盾（疑点）

样本 10/11/13 的 `generated_at` 均带 `+00:00`（如 `2026-07-21T10:57:34.956948+00:00`），而现版代码 `now_utc=now_bjt` 应输出 `+08:00`。两种可能：① 样本由旧版（`datetime.now(timezone.utc)`）生成；② 存在另一入口以 UTC 调用（如 GHA workflow 直接 import run_league 传 UTC）。**未运行脚本核实，记入 §9 疑点清单。**

### 3.3 「某联赛最新一次运行」的可靠选取规则

因文件名不含 league 且同小时覆盖，无法从文件名或顶层 `league` 保证拿到「某联赛最新」：同一小时多联赛只剩一份。web 层可靠做法（伪代码）：

```
# 前提：先修 §9-1（文件名带 league）或改用目录按联赛分文件；否则只能取"最新一次某文件"，
# 该文件可能是任意联赛，且无法判断覆盖顺序。
def pick_latest_for_league(league):
    candidates = []
    for f in glob("predictions/prediction_*.json"):
        d = json.load(f)
        if d.get("league") != league: continue
        candidates.append((parse_ts(d["generated_at"]), f))
    return max(candidates)[1] if candidates else None   # 按 generated_at 最大
```

可靠依据是 `generated_at`（BJT）；但由于同小时覆盖，**磁盘上可能只存在最后跑的那个联赛的文件**，此时该文件顶层 `league` 可能不是目标联赛，「最新一次可靠选取」在现命名方案下**无法保证**（§9 疑点）。web 层建议依赖 GHA/scheduler 单联赛独立运行、各自落盘，再按 `generated_at` 取最大。

## 4. 赛果与回填

### 4.1 `results/*.json` schema（现版输出 core/output.py:31-74）

`save_results(past)` 在每次 `_fetch_and_parse` 后被调用（predict.py:91），路径 `RESULTS_DIR / f"result_{today}.json"`，`today = datetime.now(timezone.utc).strftime("%Y-%m-%d")`（output.py:36-37）——**文件名日期是 UTC**（与预测文件名 BJT 不一致，见 §3 疑点）。

样本 `scripts/results/result_2026-07-21.json`：

```json
{
  "date": "2026-07-21",
  "matches": [
    {
      "id": "Brentford FC vs Arsenal FC",
      "kickoff_utc": "2025-01-01T17:30:00Z",
      "home": "Brentford FC",
      "away": "Arsenal FC",
      "home_score": 1,
      "away_score": 3,
      "status": "STATUS_FULL_TIME"
    }
  ]
}
```

| 字段 | 类型 | 说明 | 证据 |
|---|---|---|---|
| `date` | str | UTC 当日 `YYYY-MM-DD` | output.py:36 |
| `matches[].id` | str | `past` 记录里的 `name`（中文 `"主 vs 客"`） | output.py:58 |
| `matches[].kickoff_utc` | str | ISO8601 `...Z` UTC | output.py:59 |
| `matches[].home`/`away` | str | `home_en`/`away_en`（**英文**队名，回退中文） | output.py:60-61 |
| `matches[].home_score`/`away_score` | int | `score="H-A"` 拆分 | output.py:62-63 |
| `matches[].status` | str | ESPN status name | output.py:64 |

合并规则：同日多次运行按 `home_away` 键合并（output.py:40-48,66-69），后写覆盖先写。当日无完赛记录则不写文件。

### 4.2 与 predictions 的关联键

**没有 `match_id` 级别的强关联键**。三条路径各自用不同键：

1. **预测文件内 `reconciliation`**：`reconcile_predictions(past, days=7)` 用 `name`（`"Away vs Home"` 英文队名串）做键，把当前窗口的 `past_matches` 的赛果与 `PREDICTIONS_DIR/prediction_*.json`（近 7 天 mtime）里的 `predictions[]` 比对（backtest.py:17-31,36-49）：
   - 关联键 = `predictions[].match` 字符串 ↔ `past[].name` 字符串（**英文队名串精确匹配**；`to_cn` 翻译不可用时回退英文）。
   - 方向判定基于 `direction` 前缀（backtest.py:56-65）：`d.startswith(home_team)` / `d.startswith(away_team)` / `"平" in d`。
   - 产出 `reconciliation`（backtest.py:90-99）：`reconciled/correct_direction/correct_score/correct_over_under`（int）、`direction_accuracy/score_accuracy/over_under_accuracy`（float）、`details[]`。

2. **`backtest_with_live_results`**（predict.py:370-374，`--backtest`）另走 `football-data.org` 实际赛果回测（backtest.py:278-382），输出 `output["backtest"]`，包含 `status/matched_matches/accuracy` 等（具体字段 M0b 细读）。

3. **`league_accuracy`**（predict.py:349-357，`accuracy_summary` 7d/30d）：按联赛过滤读历史文件统计（backtest.py:102-175，字段 `direction_accuracy/score_accuracy/over_under_accuracy/reconciled`，见 predict.py:226-228）。

**排序/唯一性**：`reconcile_predictions` 中 `actuals` 以 `name` 为键，后到覆盖先到（backtest.py:19-28）。日期+主队+客队组合**等价于** `name` 字符串本身（`name="Away vs Home"` 由 parse.py:258 组成），所以不采用 `kickoff_utc+home+away` 复合键；**`kickoff_utc` 不参与对账**。

### 4.3 命中判定实现位置（各管什么）

| 模块 | 管什么 | 证据 |
|---|---|---|
| `core/backtest.py` | 预测 vs 赛果的三项命中统计（方向/比分/大小球）；`reconcile_predictions`（窗口对账）、`league_accuracy`（按联赛历史精度）、`backtest_with_live_results`（在线回测） | backtest.py:17-382 |
| `core/calibration.py` | 赛果**分布**统计（主/平/客胜率）→ 修正因子；`build_calibration`（窗口）、`compute_calibration_offset`（30 天历史+指数平滑） | calibration.py:158-289 |
| `core/output.py` | `save_results` 写 `results/result_{date}.json`（**只写赛果，不含预测命中**） | output.py:31-74 |
| `core/elo.py` | 用赛果更新 ELO 评分表（`process_match_result`，predict.py:98-104） | predict.py:95-107 |

回填方向：`results/*.json` 是**纯赛果存储**，预测命中分析不读它（读的是 prediction 文件 + `past_matches`）；两份数据源（results 与 past_matches 内嵌）内容重复，格式上 results 是英文队名+int 比分，past_matches 的 `name/home/away` 也是英文（LLM 翻译不可用时），但 `score` 为 str——web 层回填展示需注意这一重复与差异（疑点 §9）。

## 5. AI 富化链路

待补（M0b）

## 6. 数据源与配额

待补（M0b）

## 7. 联赛代码表

待补（M0b）

## 8. i18n

待补（M0b）

## 9. 疑点清单

（M0a 简短版；M0b 待细读补充）

1. **`--all` 多联赛同名覆盖**：`_save_output` 文件名为 `prediction_{now:%Y-%m-%d_%H}.json`，不含 league；`--all` 时各联赛在同一小时内写同一文件，后写覆盖先写，磁盘只留最后一个联赛（predict.py:171-176,431-444）。web 层按联赛取数需改文件名带 league 后缀；由队长拍板是否改代码。
2. **时区口径矛盾**：样本 `generated_at` 为 `+00:00`，而现版 main 传参 `now_bjt`（predict.py:422-446）应得 `+08:00`。可能①样本是旧版产物（`no_future_matches` 分支现版也不落盘，sample 10/11 文件存在即旧版证据）；②存在另一入口以 UTC 调用（如 GHA workflow import run_league）。未运行脚本不能定论。
3. **文件名/时间戳时区不一致**：预测文件名与 `generated_at` 是 BJT（predict.py:422），而 `results/result_{date}.json` 文件名是 UTC（output.py:36）。web 层展示与清理需各自换算。
4. **`--no-fetch` 语义误导**：help 写 "Use local cached data"，实际 `events=[]` 空列表（predict.py:82-84），warning 还建议改用 `--data-source football-data`（该源是联网抓取，非离线）。另有 `core/cache.py`（文件型 API 缓存，TTL 默认 1 小时，目录 `FOOTBALL_DIR/.cache`，SHA256 URL 键，cache.py:17-18,21-32），但 fetch.py 是否实际使用待 M0b 核查（第 6 节范围）。
5. **Web 层读取路径**：`PREDICTIONS_DIR`/`RESULTS_DIR` 指向 `scripts/predictions`、`scripts/results`（constants.py:37-40，`FOOTBALL_DIR=LP_OUTPUT_DIR 或脚本目录`），仓库根同名目录为空壳。web 层读文件路径须以 `scripts/` 为根（或由环境变量 `LP_OUTPUT_DIR` 重定向）。
6. **样本字段漂移**：样本 13 缺 predictor.py:342-343 的 `ml_model_used`/`ml_proba`；`prediction_10/11` 空文件属旧版行为。web 层 schema 校验需容忍缺失。
7. **方向判定健壮性**：`direction` 为「中文队名 + 胜/(接近)」自由字符串，回填对账靠前缀匹配（backtest.py:56-65）；队名互为前缀（如「曼联」与「曼联青年队」）时前缀解析可能歧义，predictor.py:299-303 已留 warning。web 层若自行回填需复用同一解析逻辑。
8. **LLM 消耗源**：`parse_events` 的 `warm_translations`（parse.py:233-249）在每次运行触发 LLM 队名翻译（i18n.py:48-101），这是「禁止运行 predict.py」的直接原因之一；web 层子进程调用时需评估额外 LLM 配额消耗（第 5/6 节 M0b 详查）。
9. **`--all` stdout 与落盘不一致**：`--all` 的数组 JSON 只在 stdout，磁盘无对应聚合文件；单联赛输出为对象。web 层子进程捕获需按模式分支解析（§1.3）。
