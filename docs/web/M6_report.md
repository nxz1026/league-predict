# M6 报告：AI 摘要云端化（ai-enrich job）+ LLM 输出中文化

日期：2026-09-11 00:20（UTC） · 执行：编码 agent

## 交付物清单（wc -l 取证）

| 文件 | 行数 | diff |
|---|---|---|
| `ai/batch_pipeline.py` | 89 | +1（中文指令行） |
| `web/services/jobs.py` | 329 | +26/-11 |
| `web/routers/jobs.py` | 211 | +24/-0 |
| `static/index.html` | 376 | +34/-1 |
| `tests/web/test_m6_ai_enrich.py` | 240 | 新建 |

## 改动摘要

### 1. `ai/batch_pipeline.py`（唯一授权引擎例外）
`_build_prompt` 的 f-string 中，`Return: {...}` 行之后、`{scoring_rubric}` 之前插入：
`所有 summary 与 notes 必须使用简体中文撰写（JSON 键名保持英文）。`
git diff 确认 ai/ 目录仅此一行，`ai/` 其余零 diff。

### 2. `web/services/jobs.py`（服务层泛化）
- `create_job(args, trigger, script="predict")`：job dict 增加 `"script"` 字段；`run_job` 读取时 `job.get("script", "predict")` 容错老 job 文件缺字段。
- `_build_cmd(args, script="predict")`：predict → `predict.py`；ai_enrich → `ai_enrich_gha.py`。
- `trigger_predict` 拆出公共 `_spawn(script, extra_argv, trigger)`（配额守卫 + 并发守卫 + 登记），两 trigger 各 <25 行：
  - `trigger_predict` = `_spawn("predict", args, trigger)`（行为不变）
  - `trigger_ai_enrich` = `_spawn("ai_enrich", [], trigger)`（argv 固定为空）
- env 仍走 `_build_env()`（os.environ 全量透传），未改。

### 3. `web/routers/jobs.py`（新端点）
`POST /api/v1/jobs/ai-enrich`（require_auth、无 body 参数）：
- 202 + job（`_job_view` 现含 `script` 字段）；
- 409 already_running（复用现有 job view）；
- 429 quota_exhausted（与 predict 共享同一计数器）。
- `_executor.submit(jobs.run_job, ...)` fire-and-forget，语义与 /jobs/predict 一致。

### 4. `static/index.html`（前端增量）
AI 解读详情区顶部加「🧠 重新生成AI摘要」按钮：
- `runAiEnrich()`：POST /api/v1/jobs/ai-enrich → 复用页面现有 `pollJob` 同款轮询逻辑（`pollAiJob`）→ done 后调用 `loadAI()` 刷新 AI 详情列表。
- 样式沿用 `.btn`；错误态 429/409 与其余按钮一致；JS 增量 <40 行；未引新库。

### 5. `tests/web/test_m6_ai_enrich.py`（新建，7 测试）
仿 M3 `_Popen` mock 风格（全部假 Popen，零 live LLM/引擎调用、数据目录全指 tmp_path）：
- 401 未鉴权拒绝；
- 202 + `job.script == "ai_enrich"`、status=queued、轮询到 done 后 script 字段仍可读；
- 子进程 argv 末位指向 `scripts/ai_enrich_gha.py`（非 predict.py）；
- 409：已有任务运行时并发拒绝（同 job.script 断言）；
- 配额共享：limit=1 时 ai-enrich 触发后 predict 返回 429 quota_exhausted，`sources/status` used==1；
- 中文指令行存在（读 ai 包源文件，行号序 Return < 简体中文 < {scoring_rubric}，键名保持英文）；
- `_build_prompt` 输出含「简体中文」（注入假 `ai.llm_client` 模块，零 LLM 调用）。

## 验收：pytest 全量

```
cd /root/projects/league-predict && /root/venvs/web/bin/python -m pytest tests/web -q
63 passed, 2 warnings in 10.57s
```

（尾行取证；2 warnings 为 fastapi testclient 既有 StarletteDeprecationWarning，非本次引入。）

## 验收：ast 行数自查

全部函数 <50 行，最长 44 行（`ai/batch_pipeline.py::analyse_batch`）：
```
ALL FUNCTIONS < 50 LINES
web/services/jobs.py: max = 38 (run_job)
web/routers/jobs.py: max = 40 (_validate_args)
tests/web/test_m6_ai_enrich.py: max = 31 (test_ai_enrich_concurrent_409)
ai/batch_pipeline.py: max = 44 (analyse_batch)
```

## 红线自查

- `git status --short`：改动仅 `ai/batch_pipeline.py`、`static/index.html`、`web/routers/jobs.py`、`web/services/jobs.py`、新 `tests/web/test_m6_ai_enrich.py`；`docs/web/logs/STATUS.md` 为前任 M6 尝试遗留改动（未触碰）。`scripts/`、`web/config.py`、`auth`、预测 API 零 diff。
- 未执行 git commit/push（队长审核后统一提交）。
- 无新依赖（requirements-web.txt / pyproject 未动）。

## 踩坑记录

1. **共享 `_executor` 线程池竞态**：单跑 `test_m6_ai_enrich.py` 全绿、全量 tests/web 时 `test_ai_enrich_concurrent_409` 偶红——前一测试的 GateProc 阻塞线程仍在池中排队，首个 POST 的 run_job 未执行到 Popen 就断言。修复：两处测试 finally 释放 gate + 断言前轮询等待 `recorded` 非空/终态。
2. **`_build_prompt` import 拉入 `requests`**：web venv 未装 requests，直接 import `ai.batch_pipeline` 会 ModuleNotFoundError。注入假 `ai.llm_client` 模块规避，仍执行真实 `_build_prompt` 函数体（零 LLM 调用）。
3. **行序断言陷阱**：`scoring_rubric` 子串首次出现是模块常量定义（行 19），非 f-string 占位。改为行号级比较 `Return行 < 中文行 < {scoring_rubric}占位行`。

## 兼容性说明

- M3 测试 `app` fixture 单参 monkeypatch `_build_cmd=lambda args: ...`：`run_job` 对 predict 脚本保持单参调用，对 ai_enrich 走双参分支，M3 测试全量不受影响（事实：63 passed 全绿）。
---

# M6R 返工记录

## 原因

M6 把 ai-enrich job 执行体指到 `scripts/ai_enrich_gha.py`，其输入是 GHA 专属的 `/tmp/predict_output.txt`，云端运行时该文件永不存在 → job exit 0 但零产出。改为 web 原生执行体，数据直接读 `web.services.store`。

## 改动摘要（4 文件）

| 文件 | 改动 |
|---|---|
| `web/enrich.py`（新建） | `collect_items()` 调 `store.latest_by_league()`，每联赛 `data.predictions` 前 5 条映射为 `{name, league, date_found, direction, stars, confidence}`；`main()` 内延迟 import `ai.batch_pipeline.analyse_batch` / `ai.feedback_loop.save_ai_scores`（顶层零 import ai/），空集打印 `[AI Enrich] no items` 返 0，异常捕获返 1；`__main__` 走 `raise SystemExit(main())` |
| `web/services/jobs.py` | `_build_cmd` ai_enrich 分支改为 `[sys.executable, "-m", "web.enrich"]`（cwd 已是 BASE_DIR，可 -m）；predict 分支不变 |
| `tests/web/test_m6_ai_enrich.py` | 202/argv 用例锚点改断言 `-m` + `web.enrich`（不再指向 `ai_enrich_gha.py`）；新增 2 个离线用例：`collect_items` 字段映射与每联赛前 5 截断、`main` 假 analyse_batch（中文 summary）/假 save_ai_scores 断言写回且返 0 |
| `docs/web/M6_report.md` | 追加本节 |

## 测试结果

```
cd /root/projects/league-predict && /root/venvs/web/bin/python -m pytest tests/web -q
65 passed, 2 warnings in 10.07s
```

## ast 行数自查

```
web/enrich.py::collect_items: 22 行
web/enrich.py::main: 28 行
web/services/jobs.py::_build_cmd: 5 行
ALL < 50 LINES
```

## 红线自查

- 仅动工单 4 文件；`ai/`、`scripts/`、`static/` 零触碰（含 M6 已授权行未再动）。
- 未执行 git commit/push；无新依赖。

## 字段映射修正（M6R2）

`web/enrich.py::collect_items` 内层循环原用 `pred.get("pick")` 三元归约 `direction`，但预测 dict 真实键为 `direction`（值如"挪威 胜"）、`stars`、`confidence_score`，不存在 `pick` / `confidence`。修正：
- 删除 `direction` 局部变量块与 `stars`/`confidence` 的旧 `.get()` 行；
- 改为 `"direction": pred.get("direction", "?")`、`"stars": pred.get("stars", "?")`、`"confidence": pred.get("confidence_score", "")`；
- 测试 fixture 同步改用真实键（`direction="曼城 胜"`、`stars="2-star"`、`confidence_score=0.61`），断言对应更新。
```
cd /root/projects/league-predict && /root/venvs/web/bin/python -m pytest tests/web -q
65 passed, 2 warnings in 12.69s
```
