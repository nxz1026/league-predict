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
| `--no-fetch` | False | flag | 用本地缓存数据，跳过网络抓取 |
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

提前退出分支（不写预测文件）：
- 窗口内无任何比赛：返回 `status="no_matches"` 的空 output，仍走 `_save_output` 落盘（predict.py:266-274）。
- 无未来比赛且非回测：`status="no_future_matches"`，仍落盘，附 `reconciliation`（若可对账）（predict.py:276-289）。
- `--train-ml` / `--cleanup`：main 内直接 return，**不落盘预测**。

### 1.3 stdout/stderr 约定

| 模式 | stdout | stderr |
|---|---|---|
| 单联赛（非 silent） | 整个 output 的 JSON（`indent=2, ensure_ascii=False`，predict.py:377-378） | logger 日志 + 摘要 + 计时 |
| `--all` | 各联赛 output 组成的 **JSON 数组**（predict.py:444）；每联赛分隔横幅走 stderr | 同上 |
| `--train-ml` | 无 | `league: trained/skipped` 逐行 + logger |
| `--cleanup` | 无 | logger 清理日志 |

注意：`--all` 与单联赛 stdout **形态不同**（数组 vs 对象）；单联赛模式下若 stdout 被消费为「CLI 产物」，`--all` 需要按数组解析。此点已记入 §9 疑点清单（web 层子进程捕获 stdout 时需分支处理）。

## 2. 预测 JSON schema

待补

## 3. 文件命名与时区

待补

## 4. 赛果与回填

待补

## 5. AI 富化链路

待补（M0b）

## 6. 数据源与配额

待补（M0b）

## 7. 联赛代码表

待补（M0b）

## 8. i18n

待补（M0b）

## 9. 疑点清单

待补
