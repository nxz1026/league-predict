# WO-M0 工单 — 引擎数据契约勘察（只读）

## 目标
产出一份 `docs/web/DATA_CONTRACT.md`，作为后续 web 层（M1–M4）唯一的数据口径依据。**本工单阶段不改任何代码**（除新建该文档与勘察脚本产物外，其余文件只读）。

## 必读背景
- 本仓 docs/web/PLAN.md（总体方案，尤其 §2/§3/§5）
- 参照仓 `/root/projects/welfare_predict`（web 栈样板，只读；重点 src/api.py、src/session.py、src/scheduler.py、static/index.html 的结构与模式，不要复制其重依赖）

## 交付物：docs/web/DATA_CONTRACT.md 必须覆盖以下 9 节
1. **CLI 全景**：`scripts/predict.py` 全部参数、每种参数组合的副作用（写哪些文件/目录、stdout/stderr 格式）。特别说明 `--all`、`--league`、`--dates`、`--dashboard`、`--cleanup`、`--train-ml`、`--no-ml`。
2. **预测 JSON schema**：以 `predictions/` 现有文件为样本，逐字段说明类型/单位/可为空性；重点：顶层 keys（generated_at/data_window/status/league/tournament_type/data_source/dixon_coles_*/calibration/calibration_offset/past_matches/predictions）；predictions[] 内每场的字段（direction/stars/predicted_score/poisson_top3/lambda_home/lambda_away/*_ci95/over_under/BTTS 相关/onside_signals 等）。**「每联赛每文件还是一次运行一个文件」要实证**。
3. **文件命名与时区**：`prediction_YYYY-MM-DD_HH*.json` 中时间戳是 UTC 还是 BJT？谁生成、何时覆盖？「某联赛最新一次运行」的可靠选取规则（给出伪代码）。
4. **赛果与回填**：`results/*.json`（及 scripts/results/ 若不同）schema；与 predictions 的关联键（日期+主队+客队？kickoff_utc？）；命中判定的现有实现位置（backtest.py/calibration.py 各管什么）。
5. **AI 富化链路**：ai/ 与 scripts/ai_enrich_gha.py 的调用关系；AI 文本落在预测 JSON 的哪个字段（若无则说明注入方式）；未配置 LLM 时行为。
6. **数据源与配额**：各源（API-Football/football-data/ESPN）限速、免费档日配额；`core/cache.py` 缓存目录/键/过期策略（web 层「sources 状态」端点将只读这些）。
7. **联赛代码表**：constants.py/leagues.py 里联赛的 code/名称/中文映射（web 层 `/{league}` 参数取值域）。
8. **i18n**：core/i18n.py 的用法，预测 JSON 是否含双语文本。
9. **疑点清单**：读代码无法确定、需要队长/用户拍板的问题列表（编号列出）。

## 方法要求
- 只静态读代码 + 读现有 JSON 样本；**禁止运行 `predict.py`（任何参数）**，避免消耗免费 API 配额；允许 `pytest tests/`（先确认测试不联网——若有联网用例跳过并注明）。
- 文档内所有结论必须附证据：文件路径+行号 或 JSON 样本片段。
- 文档用中文；预计 200–400 行。

## 红线
- 只读：不得修改 `scripts/`、`ai/`、`tests/`、根配置等任何既有文件。
- 唯一允许新增：`docs/web/DATA_CONTRACT.md`、`docs/web/M0_report.md`。
- 不得写入任何账号/密钥类值（哪怕是示例值）。

## 自测与汇报
- 交付时输出 M0_report.md：完成清单、每条结论的证据密度自评、未尽事项、疑点清单（同步进 DATA_CONTRACT 第 9 节）。
