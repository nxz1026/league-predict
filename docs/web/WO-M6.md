# WO-M6：AI 摘要云端化（ai-enrich job）+ LLM 输出中文化

## 背景（一段话）
GHA 已下线，AI 摘要（`predictions/ai_scores.json`）失去再生通道，web 只读缓存。
LLM 网关 agnes-ai（OpenAI 兼容 + json_object 模式）已实测可用（key/base/model 已进
`deploy/runtime.env`→staging `config.env`，web 进程 `os.environ` 全量继承）。
本单给 web 补一个手动 AI enrich job，并让 LLM 输出中文。

## 改动清单（只许动这 5 个文件 + 1 个新测试）

### 1. `ai/batch_pipeline.py` —— 唯一授权引擎例外（≤2 行）
`_build_prompt` 的 f-string，在 `# Instructions` 段 `Return: {...}` 行之后、
`{scoring_rubric}` 之前插入一行：
`所有 summary 与 notes 必须使用简体中文撰写（JSON 键名保持英文）。`
除这一行外 `ai/` 全目录零 diff。

### 2. `web/services/jobs.py` —— 泛化脚本执行
- `trigger_predict` 不动。新增 `trigger_ai_enrich()`：复用现有
  `_exclusive_lock`/quota/`_spin_state` 机制，argv 固定为
  `[str(config.BASE_DIR / "scripts" / "ai_enrich_gha.py")]`。
- 实现建议：把现有 job 的行成拆出公共 `_spawn(script_path, extra_argv, trigger)`，
  两个 trigger 函数各 <25 行；job dict 增加 `"script"` 字段（默认 predict，
  老 job 文件缺字段要容错）。
- env 走现有 `_build_env()`（os.environ 全量透传，已验证），不改。

### 3. `web/routers/jobs.py` —— 新端点
`@router.post("/jobs/ai-enrich", status_code=202)`，require_auth，
无 body 参数；语义与 jobs/predict 一致（202+job / 409 busy / 402 quota_exhausted）。
复用现有 `_job_view`。quota 与 predict 共享（同一计数器，够了）。

### 4. `static/index.html` —— AI tab 加一个按钮
"🧠 重新生成AI摘要"：POST /api/v1/jobs/ai-enrich → 复用页面现有 job 轮询 →
完成后刷新 AI details 列表。样式与现有触发按钮一致；JS 增量 <40 行；不引新库。

### 5. `tests/web/test_m6_ai_enrich.py` —— 新建
仿 `test_m3_jobs.py` 的 `_Popen` mock 风格（**严禁 live LLM/引擎调用**）：
- 401 未鉴权拒绝；
- 202 + job.script 指向 scripts/ai_enrich_gha.py、status=queued；
- 409：已有 job 运行时并发拒绝；
- quota 计数共享消耗断言；
- 中文指令行存在于 `_build_prompt` 输出（读 ai 包断言含「简体中文」）。

## 硬规矩
- 每个函数 <50 行；py3.11 兼容；无新依赖。
- 上面清单外任何文件（引擎 scripts/、web/config.py、auth、预测 API…）零 diff。
- 不许 git commit / push（队长审核后统一提交）。
- 自查（全绿才算完）：
  `cd /root/projects/league-predict && /root/venvs/web/bin/python -m pytest tests/web -q`
  加 ast 行数检查脚本自证 <50 行。
- 交付：报告写 `docs/web/M6_report.md`（改动文件、diff 摘要、测试输出尾行、自查命令与结果）；
  最后一步 `echo M6-DONE > docs/web/logs/M6.done`。
