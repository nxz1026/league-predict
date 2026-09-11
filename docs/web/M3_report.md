# M3 报告 · 任务触发 + 惰性刷新 + AI 扩展

日期：2026-09-10 12:45 UTC 前后
范围：`web/` + `tests/web/` 增量扩展（M1/M2 骨架之上），`scripts/ core/ static/` 零 diff。

## 交付物清单（2016-09-10 落盘）

| 文件 | 行数 | 职责 |
|---|---|---|
| `web/services/jobs.py` | 314 | 子进程状态机 queued/running/done/failed/timeout + 文件锁 + 配额守卫 |
| `web/services/ai.py` | 93 | AI 富化扩展模块（try-import/try-call 全降级） |
| `web/services/cron.py` | 67 | apscheduler 可选件（ENABLE_CRON 才启动，try-import） |
| `web/routers/jobs.py` | 187 | POST /jobs/predict + GET /jobs/{id} + GET /jobs/auto/refresh |
| `web/routers/ai.py` | 27 | GET /ai/status + GET /ai/details |
| `web/routers/sources.py` | 59 | sources/status 增加配额用量与最近任务状态 |
| `web/config.py` | 91 | M3 配置项（超时/日限额/AI 限时/ENABLE_CRON） |
| `web/api.py` | 104 | ai 路由 try-import 降级 + cron 启动挂载 |
| `tests/web/test_m3_jobs.py` | 339 | M3 验收测试（13 项） |

## 验收点逐条证据

**A · pytest 全绿**
```
$ python3 -m pytest tests/web -q
56 passed, 2 warnings in 5.67s
```
（43 基线 + 13 M3 新增全绿。）

**B · 并发双触发只起一个子进程**
证据：`tests/web/test_m3_jobs.py::test_concurrent_trigger_only_one_producer`。
- 第一个 POST 202（门控假 Popen 挂起制造 running 窗口）；
- 第二个 POST 409 + `code=already_running`，返回既有任务；
- 断言 `recorded` 子进程数 == 1，GET /jobs 仅 1 条。
实现：`jobs.trigger_predict` 先配额、后 `active_job()` 并发守卫（jobs.py:304-315）；执行侧 `run_job` 再持 `jobs.lock` 排他锁（jobs.py:247-250）。

**C · ai.py 改坏后 app 仍能起、其余端点 200**
证据：`tests/web/test_m3_jobs.py::test_ai_broken_app_starts`。
- 将 `web/services/ai.py` 改写为语法后首行 `_broken = 1 / 0`；
- 注入 `sys.modules["web.routers.ai"] = None` 强制 import 失败；
- `importlib.reload(web.api)` → `ai_router is None`（api.py:21-25 try/except 捕获）；
- `create_app()` 成功：`/health` 200、`/api/v1/ai/status` 404（路由降级跳过）、login 200、`/sources/status` 200、`/jobs` 200。
实现：api.py 顶层 try-import（红线 4），`include_router` 前判 None。

**D · 状态机可轮询到终态；timeout 路径有测试覆盖**
证据：
- `test_job_poll_to_terminal`：POST → 轮询 GET /jobs/{id} 至 `done`（假 Popen wait=0），断言 `exit_code == 0`；
- `test_run_job_timeout`：假 Popen `wait` 抛 `subprocess.TimeoutExpired` → 终态 `timeout` + `error="timeout killed"` + `finished_at` 非空（jobs.py:271-278 到点必杀）；
- `test_run_job_failed_exit_code`（exit 2 → failed）、`test_run_job_spawn_error`（OSError → failed + spawn failed）。
实现：`run_job` 内 `proc.wait(timeout=config.PREDICT_TIMEOUT_SECONDS)`，超时 kill + 二次 wait(5)（jobs.py:268-278）。

**E · 配额耗尽后 POST → 429**
证据：`tests/web/test_m3_jobs.py::test_quota_exhausted_429`。
- DAILY_TRIGGER_LIMIT=2 下 `quota_consume()` 两次 True、第三次 False；
- POST /jobs/predict → 429 + `code=quota_exhausted`（routers/jobs.py:112-116）。
另 `test_quota_consume_limited`、`test_quota_reset_on_new_day`（跨 BJT 日重置，昨日计数 79 → used 0）。

**惰性刷新（工单交付物）**
证据：`test_auto_refresh_trigger_and_dedup` —— 无 today 数据时首次触发 `triggered:true`，同日再触发 `triggered:false, reason=already_today`（同日去重 marker 落 `web/.data/auto_refresh_last.json`）。
鉴权：`test_jobs_require_auth` —— jobs 三端点未登录全 401。

## 红线自查

1. **测试安全网**：全部引擎子进程为假 Popen（`_fake_sp`），门控/超时/失败均为模拟行为，零真实执行；无外部 API；jobs/quota 目录全指向 tmp_path，不触碰生产 `web/.data`。
2. **引擎零 diff**：`git diff --stat scripts/ core/ static/` 为空。
3. **只动允许目录**：变更仅 `web/`（9 文件）+ `tests/web/test_m3_jobs.py` + `docs/web/logs/STATUS.md`（M3 工作记录）；apscheduler 依赖未实际安装，cron 仅 `ENABLE_CRON=true` 时 try-import，默认路径零新依赖导入，故无需追加 requirements-web.txt/pyproject。
4. **AI 模块不阻塞启动**：api.py try-import + ai.py 内部 try/except 双保险；验收点 C 专测通过。
5. **函数 <50 行 / 3.11 / 无重型依赖**：全模块无超过 50 行的函数；兼容 3.11（`dict | None`、`ZoneInfo`）；零 pandas/numpy/sklearn/xgboost。
6. **禁 git**：未执行任何 commit/push；仅 `git status`/`git diff --stat` 取证。

## 踩坑记录

- `importlib.reload(web.api)` 后 `ai_router` 仍为旧 APIRouter 而非 None：根因是 reload 复用模块 dict，且 `sys.modules.pop` 后 `web.routers.ai` 子缓存未被清除。修复：改用 `monkeypatch.setitem(sys.modules, "web.routers.ai", None)`（import 语义下值为 None 抛 ImportError，标准注入法）。
- 首轮 `test_job_poll_to_terminal` 失败（真实执行 predict.py）：fixture 层漏 mock Popen。修复：测试内 `monkeypatch.setattr(jobs_mod, "subprocess", _fake_sp(_OkProc))`。