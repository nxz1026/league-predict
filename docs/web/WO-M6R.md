# WO-M6R（返工）：ai-enrich 执行体从 GHA 契约改为 web 原生

## 为什么返工（一段话）
M6 把 job 执行体指到 `scripts/ai_enrich_gha.py`，但该脚本输入是 GHA 专属的
`/tmp/predict_output.txt`（云端永无此文件）→ 云端 job exit 0 但零产出。
本单换成 web 原生执行体，数据直接读现有 `web.services.store`。

## 改动清单（只许动这 4 个文件）

### 1. 新建 `web/enrich.py`（web 层，非引擎）
- `collect_items() -> list[dict]`：调 `web.services.store.latest_by_league()`，
  每联赛 doc["data"]["predictions"] 取前 5，构造
  `{"name": match, "league": 联赛key, "date_found": "", "direction": direction, "stars": stars, "confidence": confidence_note}`。
- `main() -> int`：先 `items = collect_items()`，空则 print "[AI Enrich] no items" 返回 0；
  **在此函数内部才** `from ai.batch_pipeline import analyse_batch` 和
  `from ai.feedback_loop import save_ai_scores`（延迟 import，模块顶层严禁 import ai/）。
  调 `analyse_batch(items, context="", preference_prompt="", config=CFG)`，
  CFG = {"ai": {"model": os.environ.get("LLM_MODEL") or "agnes-2.5-flash",
  "batch_size": 5, "rate_limit_seconds": 3, "min_score": 0},
  "priorities": (LP_AI_PRIORITIES 逗号分隔) or DEFAULT_AI_PRIORITIES}。
  `save_ai_scores(enriched, league_key="")`；print 统计（处理条数/写回条数）返回 0；
  任何异常捕获后 print 并以 1 返回。
- `if __name__ == "__main__": raise SystemExit(main())`。
- 顶注一行：`"""web.enrich — AI 摘要富化批处理 CLI（python -m web.enrich），仅 job 子进程使用。"""`

### 2. `web/services/jobs.py`
`_build_cmd` 的 ai_enrich 分支改为 `[sys.executable, "-m", "web.enrich"]`
（cwd 已是 BASE_DIR，可 -m）。predict 分支不动。

### 3. `tests/web/test_m6_ai_enrich.py`（同单修锚点）
- 202 用例断言 argv 含 `-m` 与 `web.enrich`。
- 新增 2 个离线用例（严禁 live LLM/网络）：
  a) `collect_items`：monkeypatch `web.services.store.latest_by_league` 返回
     两个联赛 doc → 断言条数与字段映射；
  b) `main`：monkeypatch `ai.batch_pipeline.analyse_batch`（返回带中文 summary 的假 enriched）
     与 `ai.feedback_loop.save_ai_scores`（捕获入参）→ 断言写回被调用、返回 0。

### 4. `docs/web/M6_report.md` 文末追加「M6R 返工记录」一节（原因+改动+测试结果）

## 硬规矩（同 WO-M6）
- 除上 4 文件零触碰；ai/ 与 scripts/ 零 diff（含 M6 已授权行不许再动）；函数 <50 行；py3.11；无新依赖。
- 禁 git commit/push。
- 自查：`cd /root/projects/league-predict && /root/venvs/web/bin/python -m pytest tests/web -q` 全绿
  + ast <50 行自证；结果写进报告 M6R 节。
- 交付哨兵：`echo M6R-DONE > /root/projects/league-predict/docs/web/logs/M6R.done`
