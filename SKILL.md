---
name: world-cup-predict
description: 2026 世界杯预测 + 自动回填 + 复盘一体化。支持 Hermes cron（飞书推送）和 GitHub Actions（邮件推送）双模式。Python 引擎 scripts/predict_wc.py 跑 P0 全字段 + P2 三向加权评分 + Poisson 比分分布算法。GHA 版已实测通过（2026-06-29），每日 16:35 BJT 自动推送邮件。
---

# World Cup Predict — 一体化版

每日 10:30 BJT 跑一次（cron `30 2 * * *` UTC，或 GitHub Actions schedule `4 8 * * *`），覆盖未来 24h 比赛，产出预测 + 自动回填前 24h 结果 + 复盘摘要。

## 部署模式

本 skill 支持两种部署路径：

| | Hermes cron | GitHub Actions |
|--|-------------|-----------------|
| 触发 | Hermes `cronjob` schedule `30 2 * * *` | `schedule: cron '4 8 * * *'` (UTC 08:04 = BJT 16:04) |
| 执行引擎 | Hermes agent + `predict_wc.py` | 纯 `predict_wc.py`，无需 Hermes |
| 模型依赖 | LongCat-2.0-Preview (LLM) | 无（纯 deterministc Python，stdio only） |
| 推送渠道 | 飞书（sidecar HTTP API 卡片） | 邮件（SMTP via `dawidd6/action-send-mail@v3`） |
| 依赖 | Hermes 环境 + sidecar + secrets.yaml | GitHub Secrets + `requests` |
| 侧边栏 | feishu-card-sidecar-watchdog 守护 | GitHub-hosted runner |

### GitHub Actions 部署流程（当需要 cron 不在 Hermes 环境运行时）

1. Fork/创建仓库，复制 `scripts/predict_wc.py` + `references/tournament-trends.md`
2. 创建 `.github/workflows/world-cup-predict.yml`（见 `references/gha-workflow-template.md`）
3. 在 GitHub 仓库 Settings → Secrets → Actions 中添加：`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`
4. 本地验证：`python3 scripts/predict_wc.py`（检查 stdout JSON 输出）
5. 手动触发一次确认推送正常
6. 暂停 Hermes 侧的 cron：`cronjob(action='pause', job_id='<原id>')`

### 邮件 vs 飞书的选择

- **飞书版**：保留在 Hermes 侧，LLM 负责格式化 + sidecar 发卡片。适合需要 tournament-trends 软校准和 LLM 解读的场景。
- **邮件版**：迁移到 GHA，纯 Python 脚本 + SMTP。适合**确定性、无 LLM、审计型**工作流，更省 token、更透明、更适合 CI/CD。

## ⚠️ 核心约束

- **只预测未来 24h 内未开赛的比赛**（最多 5 场）
- 总输出 **≤ 400 字**
- 不发邮件（只存本地 + final response 输出）
- 回填时 **不修改 predictions/\***，只读
- **比分采用 Poisson 分布预测**（2026-06-19 改造）：输出 top-3 最可能比分 + 概率。λ = raw_strength × 4.5，强队 λ 3.0-3.5，弱队 λ 0.3-0.8。见「步骤 4：Poisson 比分分布」。
- **Poisson 准率 22-30%**，高于启发式 10-15%。输出 top-3 比分展示概率梯度，避免单调感。脚本 `predict_wc.py` 已实现 Poisson 比分分布（v2 2026-06-25），JSON 输出含 `poisson_top3` + `lambda_home`/`lambda_away` 字段。

## ⚡ 执行流程（严格按此顺序：先回填 → 再校准 → 后预测）

> **关键设计**：预测前必须先用真实结果校准，避免预测偏差继续累积。
>
> **2026-06-22 改造**：predict_wc.py 是确定性脚本，Planner 直接跑，不建 Coder 卡（避免 LongCat 在 kanban 模式下的 protocol_violation）。只建 Auditor 卡审计 JSON 输出。P1 必须驳回（不可给有条件通过），触发修复循环（最多 3 轮）。

## 🤖 LLM 配置（改这里切模型，不用动 SKILL.md 或 cron）

LLM 从本目录 `config.yaml` 的 `llm` 段读取：

```yaml
llm:
  provider: Api.openmodel.ai   # 走 ~/.hermes/config.yaml 的 providers 段
  model: deepseek-v4-flash
```

- `provider` 对应 `~/.hermes/config.yaml` 里 `providers[].name`（含密钥和 base_url）
- `model` 是该 provider 支持的模型名
- cron jobs.json 里的 `model` / `provider` 字段是兜底覆盖，agent 启动时若已 pin provider 优先用 jobs.json
- 当前默认：`Api.openmodel.ai` / `deepseek-v4-flash`（2026-06-18 改）

### 核心引擎

所有计算由 `/root/.hermes/scripts/predict_wc.py` 执行：
```bash
python3 /root/.hermes/scripts/predict_wc.py
```
输出：JSON 写入 `predictions/prediction_YYYY-MM-DD_HH.json`，包含校准参数 + 预测结果。

### P0 全字段利用

从 ESPN API 的 raw JSON 提取过去忽略的字段：

| 字段 | 路径 | 用途 |
|------|------|------|
| 球队近 5 场状态 | `competitors[].form` (如 "DWDDW") | form_to_score: W=3, D=1, L=0 归一化 |
| 本届赛事战绩 | `competitors[].records[].summary` (如 "1-0-0") | record_to_score: W-D-L 比分 |
| 主队 ML 赔率 | `odds[0].details` (如 "CZE -125") | parse 后计算隐含概率 |
| 平局 ML 赔率 | `odds[0].drawOdds.moneyLine` (如 265) | 三向去水计算 |
| 亚盘盘口线 | `pointSpread.home.close.line` (如 -0.5) | 区分碾压 vs 接近 |
| 亚盘水位变化 | `pointSpread.home.open/close.odds` | spread_movement_factor 量化 |

### P2 算法：三向加权评分

**步骤 1：ML 去水** (remove_vig)
```
home_implied = parse_american_odds("-125") = 125/225 = 0.5556
draw_implied = parse_american_odds(265) = 100/365 = 0.2740
away_implied = 1.07 - home - draw = 0.2404  (7% bookmaker margin)
home_true = 0.5556/1.07 = 0.519
```

**步骤 2：三向强度计算** (clamp ≥ 0)
```
home_strength = home_true × 0.40 + home_form × 0.20 + home_record × 0.15 + spread_movement × 0.25
away_strength = away_true × 0.40 + away_form × 0.20 + away_record × 0.15 + (-spread_movement) × 0.25
draw_strength = draw_true × 0.50
```

**步骤 3：归一化 + 方向判定**
```
P(home) = home_strength / total
• P(home) > 45% 且 > P(away)×1.3 → 主胜
• P(away) > 45% 且 > P(home)×1.3 → 客胜
• P(draw) > 40% → 平局
• 否则 → 取最高方向 + (接近)
```

信心星级：评分 > 0.8 ⭐⭐⭐⭐⭐ / > 0.65 ⭐⭐⭐⭐ / > 0.5 ⭐⭐⭐ / > 0.35 ⭐⭐ / 其他 ⭐

### 步骤 4：Poisson 比分分布

取代原来的启发式 if-elif，使用 Poisson 分布预测比分。

**λ 计算**（从三向原始强度 → 期望进球）：
```
raw_home = home_true × 0.40 + home_form × 0.20 + home_record × 0.15 + spread_movement × 0.25
raw_away = away_true × 0.40 + away_form × 0.20 + away_record × 0.15 + (-spread_movement) × 0.25
raw_draw = draw_true × 0.50

λ_home = (raw_home + 0.5 × raw_draw) × 4.5    # 强队 λ ~3.0-3.5
λ_away = (raw_away + 0.5 × raw_draw) × 4.5    # 弱队 λ ~0.3-0.8
```

**Poisson 联合概率**（遍历 0..8 球 × 0..8 球）：
```
P(h, a) = Pois(h; λ_home) × Pois(a; λ_away)
```

取 top-3 最可能比分，带概率百分比输出。

**示例**（巴西 vs 海地，λ=3.2 vs 0.5）：
```
3-0 (14%) / 2-0 (13%) / 4-0 (11%)
```

**参数调整**：`LAMBDA_MULTIPLIER`（当前 4.5）提高 → 比分更激进，降低 → 更保守。

### 自动校准

每次运行后计算：
```
calibration.home_win_rate = past home wins / total
calibration.odds_accuracy = ML favorites that actually won / total ML-favored matches
```
校准数据输出到 JSON + 自动更新 `references/tournament-trends.md`。

### 国家名中文化

`COUNTRY_CN` 字典 (130+ 队) + `to_cn()` 函数：英文国家名 (ESPN) → 中文（"Czechia 胜" → "捷克 胜"，"South Africa at Czechia" → "南非 vs 捷克"）。ESPN event name 格式 "Away at Home" 自动转换为 "客队 vs 主队"。覆盖 2026 世界杯 48 队 + 常见国家队。完整映射见 `references/country-codes.md`（可被任何体育预测 skill 复用）。

### 第一步：回填已结束比赛（先写真实结果）

```python
# 用 ESPN API 抓过去 24h 的已结束比赛，写入 results/result_YYYY-MM-DD.json
# 格式同现有 results/
```

**只填真实抓到的比分，不用 LLM 猜。** 失败比赛跳过。

直接用核心引擎 `/root/.hermes/scripts/predict_wc.py` 跑全流程：抓 ESPN → 解析 → 回填 → 校准 → 预测 → 写 JSON。

### 第二步：自动校准（对比回填结果 → 计算校准参数）

对比 `predictions/`（过去 48h 内预测）vs `results/`（刚刚回填的数据），输出 1 句复盘校准：

```
📊 最近 N 场复盘：方向 X/Y，热门队 Z 场仅 A 胜 → 降档信心度
```

### 第三步：预测未来比赛

#### 数据源

**ESPN API**（自带 DraftKings 赔率）— 唯一数据源，不需要 API Key。

```
GET https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD-YYYYMMDD&limit=50
```

**日期窗口**：`dates={today-1}-{today+1}`（3 天），避免边界漏场。

#### 方法论

**只分析 spread/total 的 open→close movement**。这是唯一可靠的数据（ESPN API 的 `moneyline` 字段经常为空，`spread` 和 `total` 的 open/close 实测最稳定）。

4 步：
1. 提取 `odds[0].pointSpread.home.open/close`（水位变化）
2. 提取 `odds[0].total.over/close` 和 `under.close`（大小球变化）
3. **spread 水位翻转** 是最强信号（如 -115→-135 表示市场信心增强）
4. **ML 开盘数据不可得** — 放弃 ML open→close 分析，只从 `web_extract` 摘要确认当前 ML 关闭盘

#### 关键校准【动态数据，2026-06-27 改造】

⚠️ **不再用静态数字**——每次预测前必须先读 `references/tournament-trends.md`，用最新的 tournament 方向分布做 soft calibration。

**当前已知趋势（会被 tournament-trends.md 覆盖）**：

| 分布 | 信号 | soft calibration 行为 |
|------|------|----------------------|
| draw_rate > 25% | 强队难赢盘、48队扩军弱队死守 | 当本场 ML draw_prob < 30% → 在输出中添加"⚠️ tournament 平局率偏高，注意本场可能被低估" |
| home_rate >> away_rate | 中立场地主场效应 / 跨北美旅行 | 当 spread 无强烈信号且为主场队 → 默认 +0.5 星倾向主场 |
| 联合会差异 | CAF 防守闷平 / UEFA 碾压正常 | UEFA 对非 UEFA → 维持信心；CAF 对 CAF → 默认倾向小比分 |
| odds_accuracy = 0 | ESPN 无 ML open，ML 信号不可信 | 当 ML 与 spread 矛盾 → 优先信 spread，ML 仅作参考 |

**校准是「soft judgment」**：不改 `predict_wc.py` 的计算结果，只在 LLM 格式化输出时体现（备注、用词调整、接近比赛的倾向表述）。

**信心度规则修正**：
- 信心 ⭐⭐⭐⭐ 及以上 → **必须有 spread 和 total 双信号支持**，缺一不可
- 盘口模糊（spread open/close 差异 < 10%）→ 最高给 ⭐⭐
- 比分预测改为 Poisson 分布（见步骤 4），输出 top-3 最可能比分 + 概率

#### 输出（5 项）

| 项目 | 说明 | 示例 |
|------|------|------|
| 方向+信心 | 推荐方向 + 1-5 星 | Spain 胜 ⭐⭐ |
| 比分 top-3 | Poisson 三向最可能比分 + 概率 | 2-1 (18%) / 1-1 (15%) / 3-1 (12%) |
| 期望进球 λ | 主+客 Poisson λ 之和（0.1 精度） | λ=4.2 |
| 大小球+线 | Over/Under | Over 2.5 |
| 双方进球 | Yes/No | No |

#### 存档

`predictions/prediction_YYYY-MM-DD_HH.json`

## Cron 卡片输出（2026-06-25）

Cron job 的 `deliver: "feishu"` 默认发送**原生文本**，不是卡片。
要让 cron 输出卡片化，在 prompt 末尾加"卡片发送硬规则"：

```
⚠️ 卡片发送硬规则（P0 必须遵守）
不要使用 final response 发送！final response 会发送原生文本，不会卡片化。
必须用以下方式发送卡片：
1. 将报告内容写入 /tmp/cron_card_content.md
2. 执行：bash /root/.hermes/scripts/send_cron_card.sh "$(cat /tmp/cron_card_content.md)"
3. 确认发送成功后，final response 只输出：[SILENT]
```

脚本路径：`/root/.hermes/scripts/send_cron_card.sh`（通用，所有 cron 可复用）
原理：通过 sidecar HTTP API 发送 `message.started → answer.delta → message.completed` 三事件，sidecar 渲染卡片后发往飞书。

## GitHub Actions 迁移踩坑（2026-06-29 实战）

### 1. JSON 解析：stderr 日志 + stdout JSON 混合

`predict_wc.py` 的 `log()` 函数输出 `[predict] ...` 到 stderr，JSON 输出到 stdout。GHA workflow 中如果用 `2>&1 | tee /tmp/output.txt`，文件里是混合内容：

```
[predict] Fetching ESPN: ...
[predict] Got 7 events from ESPN
{
  "generated_at": "...",
  ...
}
```

**错误做法**：`json.loads(open('/tmp/output.txt').read())` → `JSONDecodeError: Extra data`

**正确做法**：
```python
output = open('/tmp/predict_output.txt').read().strip()
json_start = output.find('{')
decoder = json.JSONDecoder()
data, _ = decoder.raw_decode(output[json_start:])
```

**关键**：
- 用 `output.find('{')` 而不是按行找 `startswith('{')`，因为 JSON 对象内部可能有 `{` 字符
- 用 `raw_decode()` 而不是 `json.loads()`，只解析第一个 JSON 对象，忽略尾部残留日志
- 如果脚本本身 exit code 1，`|| (cat /tmp/output.txt && exit 1)` 能在 GHA 日志里显示错误原因

### 2. Step outputs 必须写 $GITHUB_OUTPUT

Python 的 `print()` 在 GHA 里只输出到日志，**不会**设置 step output。

**错误做法**：
```python
print(f"subject={subject}")
print(f"body<<EOF\n{email_body}\nEOF")
```

**正确做法**：
```python
import os
github_output = os.environ.get('GITHUB_OUTPUT', '/dev/null')
with open(github_output, 'a') as f:
    f.write(f"subject={subject}\n")
    f.write(f"body<<EOF\n{email_body}\nEOF\n")
```

或者用 `shell: bash` 让 shell 处理：
```bash
python3 script.py > /tmp/body.txt
echo "subject=..." >> "$GITHUB_OUTPUT"
echo "body<<EOF" >> "$GITHUB_OUTPUT"
cat /tmp/body.txt >> "$GITHUB_OUTPUT"
echo "" >> "$GITHUB_OUTPUT"
echo "EOF" >> "$GITHUB_OUTPUT"
```

### 3. GHA 文件系统限制

- 不能写 `/root/football/` → `PermissionError: [Errno 13] Permission denied`
- 必须用相对路径（`Path(__file__).resolve().parent.parent`）
- `predict_wc.py` 已改为基于脚本位置自动计算 repo 根目录

### 4. predict_wc.py 零外部依赖

脚本只用 stdlib：`urllib.request` + `json` + `gzip` + `math` + `pathlib`。

**不需要** `pip install requests`，**不需要** `requirements.txt`。

GHA workflow 中直接 `python3 scripts/predict_wc.py` 即可。

### 5. dawidd6/action-send-mail 必填字段

`from` 参数是 required。如果 `${{ secrets.SMTP_USER }}` 为空（secret 未配置），报错：
```
Input required and not supplied: from
```

**调试清单**：确认 GitHub Secrets 全部配齐 — `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`。

### 6. 迁移后必须暂停原 Hermes cron

GHA 版工作后，原 Hermes 侧 cron（job_id `84d210ffeedc`）必须暂停，否则会重复推送。

```json
{"action": "pause", "job_id": "84d210ffeedc"}
```

## 踩坑

- **核心引擎**：所有计算交给 `scripts/predict_wc.py`（cron prompt 一句话调用），LLM 只负责格式化输出。不要在 cron 里手写 ad-hoc 解析代码。
- **AgentMail inbox 必须先创建**：`mcp_agentmail_create_inbox(username="hermes_nd0104", domain="agentmail.to")`
- **ESPN 日期窗口扩 3 天**：`dates=today-1-today+1`，单天窗口的凌晨场会漏
- **moneyline 字段不存在**：放弃从 raw JSON 找 ML open/close，只用 spread/total 的 open/close
- **Post-delete verification** 不需要发邮件
- **execute_code 在 cron 下被 BLOCKED**：必须用 `terminal` + `write_file` 替代
- **Terminal heredoc 含中文被拦截**：用 `write_file` 写 .py 到 /tmp 再 `terminal python3 /tmp/script.py`
- **`parse_american_odds` 符号陷阱**（2026-06-18 实战 bug）：负赔率 `-125` 隐含概率公式是 `abs(odds) / (abs(odds) + 100) = 0.5556`。**不要写成** `-odds / (-odds + 100)`（符号乘进去会得 5.0 这种离谱值）。单元测试：`-125` 应返回 `~0.5556`，`-360` 应返回 `~0.783`，`+105` 应返回 `~0.488`，`+265` 应返回 `~0.274`。任一偏差 >0.01 即公式错。
- **不要把 draw_ml_implied 混进单一 "home_score"**（2026-06-18 算法 bug）：原版 `home_score = home_ml × 0.30 + draw_ml × 0.25 + ...` 会让平局概率高的比赛整体偏向"主队优势"，方向判定失灵。**正解**：三向独立算 `home_strength` / `away_strength` / `draw_strength`，再归一化后比较三个概率。即使计算 home 的强度也不掺 draw 因子。
- **Poisson λ 用 raw_strength 不用归一化概率**（2026-06-19 新算法）：λ 计算基于归一化前的三向原始强度（raw_home/raw_away/raw_draw），而非归一化后的 home_prob/draw_prob/away_prob。原始强度保留了绝对大小差异（强 0.8 vs 弱 0.2），归一化后会变成 0.6 vs 0.15，对比被压缩。
- **Coder 卡不要用 reasonix/LongCat**（2026-06-22 实战）：reasonix 作为 Coder 跑 `predict_wc.py` 脚本没问题，但**不会调 `kanban_complete`** 回传结果，导致 protocol_violation x2。**解法**：predict_wc.py 是确定性脚本，Planner 直接跑，不建 Coder 卡。只建 Auditor 卡审计 JSON 输出。
- **Auditor 的 P1 必须是驳回**（2026-06-22 实战）：P1 严重（逻辑错误、边界未处理）→ 裁定「驳回」，不是「有条件通过」。**解法**：Auditor 卡 body 中硬编码"P1 = 必须驳回，不可给有条件通过"，不给 Auditor 自行判断空间。Planner 收到 P1 驳回后触发自动修复循环（最多 3 轮）。
- **ESPN match 字段是 Away at Home 格式，predicted_score 是 home-away 格式**（2026-06-24 实战 bug）：match 字段如 "卡塔尔 vs 波黑" 实际是 away at home（客队在前），但 predicted_score 如 "0-1" 是 home-away 格式（主队在前）。LLM 格式化时如果直接用 match 当 "主队 vs 客队"，方向就和比分数字矛盾（如写"卡塔尔胜"但比分 0-1 表示客队卡塔尔赢，读者以为主队卡塔尔 0 球输了）。**解法**：predict_wc.py 已新增 match_display（"主队 vs 客队"）、score_display、direction_display 字段。cron prompt 已加 P0 硬规则：LLM 必须用 display 字段原样输出，禁止用原始 match 字段。
- **CLI 报错先确认再深潜**（2026-06-24 教训）：用户截图显示 hermes: error: argument command: invalid choice: gateway，实际是用户打错字（typo），不是真正的 bug。**规则**：遇到 CLI 报错时，先原样执行一遍命令确认是否可复现，不要立即跳进源码排查。
- **GHA 迁移 JSON 解析陷阱**（2026-06-29）：`predict_wc.py` 的 stderr 输出 `[predict] ...` 日志行，stdout 末尾才是 JSON。在 GHA workflow 中解析时必须先找 `{` 开头的行作为 JSON 起始，不能直接对整个 stdout 做 `json.loads()`。正确做法：`lines = output.strip().split('\\n')` → 找 `line.strip().startswith('{')` 的索引 → `json.loads('\\n'.join(lines[i:]))`。**注意**：即使找到 `{` 开头行，后面仍可能有非 JSON 内容（如后续日志），最稳健的做法是用 `json.JSONDecoder().raw_decode('\n'.join(lines[i:]))` 只解析第一个 JSON 对象，忽略尾部垃圾数据。
- **GHA dawidd6/action-send-mail 必填字段**（2026-06-29）：`dawidd6/action-send-mail@v3` 的 `from` 参数是 required。如果 `${{ secrets.SMTP_USER }}` 为空（secret 未配置），会报 `Input required and not supplied: from`。调试时需确认 GitHub Secrets 全部配齐（SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO）。
- **predict_wc.py 零外部依赖**（2026-06-29）：核心脚本只用 `urllib.request` + `json` + `gzip` + `math`（全部 stdlib）。GHA workflow 中 `pip install requests` 是多余的，直接 `python scripts/predict_wc.py` 即可，无需安装任何包，也无需 requirements.txt。
- **predict_wc.py 零外部依赖**（2026-06-29）：核心脚本只用 `urllib.request` + `json` + `gzip` + `math`（全部 stdlib）。GHA workflow 中 `pip install requests` 是多余的，直接 `python scripts/predict_wc.py` 即可，无需安装任何包。
- **迁移后必须暂停 Hermes cron**（2026-06-29）：GHA 版工作后，原 Hermes 侧 cron（job_id `84d210ffeedc`）必须 `cronjob(action='pause')`，否则会重复推送。迁移时有两个 cron 并存的窗口期应尽量短。
- **GHA 版确定性脚本无需 LLM 格式化开销**（2026-06-29）：迁移后邮件格式化直接在 workflow 里用 Python 模板完成，无需调用 LLM。好处是省 Token、可审计、可复现；代价是失去 tournament-trends 的 soft calibration 能力。如果后续需要软校准（根据 tournament-trends 调整信心度），考虑发飞书消息指向 SMTP 邮件 + LLM 解读的组合方案。

## references 引用

- `references/calibration-architecture.md` — 校准架构决策：build_calibration() 不反馈脚本、tournament-trends 信号可用性评估、LLM soft calibration 框架
- `references/espn-match-format.md` — ESPN API match 字段 "Away at Home" 格式 vs predicted_score "home-away" 格式差异及 display 字段修复
- `references/espn-api.md` — API 字段结构详解
- `references/tournament-trends.md` — 跨 session 趋势累积
- `references/odds-math.md` — 美式赔率解析与去水公式 (独立可复用)
- `references/poisson-math.md` — Poisson 比分分布设计文档（λ 计算、参数理由、典型输出）
- `references/country-codes.md` — 130+ 队中英文映射 (可被任何体育预测 skill 复用)
- `references/feedback.md` — 反馈日志模板（预测 vs 实际结果，用于跨 session 学习）
- `references/gha-workflow-template.md` — GitHub Actions 迁移：完整 workflow 模板 + JSON 解析陷阱 + Secrets 配置 + 邮件排版 + 迁移后暂停原 cron 要点

---

## Pitfalls

1. **校准数据无反馈回路是架构局限，非代码 bug**（2026-06-28 实战）—— 来源：通道 B（会话审计），五维度分类：功能实现。`build_calibration()` 输出的 `home_win_rate`/`draw_rate` 等统计数字从未反馈到 `calculate_prediction()` 的权重中。回填 66 场历史数据后，预测算法的权重（ML 40% + form 20% + record 15% + spread 25%）完全不读 calibration dict。这不是遗漏，是架构设计决定让确定性脚本只做计算、让 LLM 用 tournament-trends 做 soft judgment。**不要尝试加 calibration feedback loop**——66 场样本量（95% CI ±11pp）精度不够调参，且 spread 25% + form 20% 已经隐含了 tournament-level 调整。正确做法：保持脚本不变，把 tournament-trends 的文本解读注入给 cron prompt（LLM），让它在格式化输出时做软判断。

## 自审（每次运行后执行）

预测跑完后，Planner 直接执行自审（不通过 Coder 卡）：

### Step 1: 读取本次预测结果
```bash
cat predictions/prediction_<latest>.json
```

### Step 2: 回填对比
读取 `results/result_<today>.json` 中的真实比分，对比本次预测：
- 方向是否正确（主胜/客胜/平局）
- 比分是否接近真实比分（top-3 中是否包含真实比分）
- 信心星级是否与实际结果匹配

### Step 3: 提取教训
对每场对比结果，提取：

| 字段 | 说明 |
|------|------|
| 比赛 | 球队 A vs 球队 B |
| 预测方向 | 主胜/客胜/平局 |
| 实际结果 | 比分 |
| 准确度 | 方向对/错，比分距离 |
| 教训 | 下次怎么改进 |

### Step 4: 更新本 skill Pitfalls
如果提取到新教训，用 `skill_manage(action='patch', name='world-cup-predict', ...)` 追加到本 skill 的 Pitfalls 段：

```
N. **教训标题**（YYYY-MM-DD 实战）—— 描述 + 修复方法
```

**不重复添加**已有 pitfalls。如果本 skill 没有 Pitfalls 段，先创建。

### Step 5: 自审（立即执行，不等 self-reflection）

预测跑完后，**必须立即执行自审**，将教训沉淀到本 skill：

1. 读取 `predictions/prediction_<latest>.json`
2. 读取 `results/result_<today>.json` 中的真实比分
3. 对比每场预测的方向和比分准确度
4. 提取教训，用 `skill_manage(action='patch', name='world-cup-predict', ...)` 追加到本 skill 的 Pitfalls 段
5. 将校准参数追加到 `references/tournament-trends.md`

**自审结果必须回传给飞书**，格式：
```markdown
### 📊 预测自审 YYYY-MM-DD
- 方向准确率: X/Y
- 比分命中: top-3 中包含真实比分 Z 场
- 教训: ...
- 已更新 skill pitfalls + tournament-trends.md
```

## 自审输出要求

**每次预测完成后，必须将以下内容通过飞书发送给用户：**

1. **预测结果摘要**（5 项：方向+信心 / 比分 top-3 / 期望进球 λ / 大小球 / 双方进球）
2. **自审结果**（方向准确率 / 比分命中 / 新教训）
3. **已更新的文件**（skill pitfalls / tournament-trends.md）

**不要只发"建卡成功"或"审计通过"，要发实际的预测内容和自审结论。**
