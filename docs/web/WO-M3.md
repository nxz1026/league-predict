# WO-M3 · 任务触发 + 惰性刷新 + AI 扩展

前提：M1/M2 已交付。背景事实（契约 §1/§6）：引擎每次运行有写副作用与外部 API 配额（免费档每日百来次），部署平台 Hobby 档会缩到零 ⇒ **常驻 cron 不可靠，主调度=惰性刷新**；apscheduler 只做 `ENABLE_CRON` env 开关下的可选件，默认关。

## 交付物
| 文件 | 职责 |
|---|---|
| `web/services/jobs.py` | 子进程跑 `scripts/predict.py` CLI（cwd=仓库根、`sys.executable`、独立 env、输出重定向 web/.data/jobs/<id>.log）；文件锁 `web/.data/jobs.lock` 保证**同时只有一个生产者**；默认超时 600s 到点必杀；状态机 queued/running/done/failed/timeout 写 `web/.data/jobs/<id>.json` |
| 配额守卫 | `web/.data/quota.json` 日计数：每日触发上限（env，默认 80，给手动留余量），跨 BJT 日自动重置；无预算 → 429+原因 |
| `web/routers/jobs.py` | `POST /api/v1/jobs/predict`（require_auth；参数白名单透传：league/dates 等，禁任意字符串注入 argv）、`GET /api/v1/jobs/{id}` |
| 惰性刷新 | `predictions/today` 数据缺失时 fire-and-forget 后台任务（经同一把锁与配额守卫；同日去重，一天至多自动触发一次） |
| `web/services/ai.py` + `routers` 端点 | 契约 §5 链路：AI 富化为**扩展模块**——try-import/try-call，超时或失败一律降级 `{available:false, reason}`，绝不阻塞/拖垮主流程；端点响应限时（默认 8s） |
| `web/routers/sources.py` 扩展 | sources/status 增加配额用量与最近任务状态（读 jobs/quota 状态文件） |
| apscheduler 可选件 | 仅当 `ENABLE_CRON=true` 才启动（api.py  lifespan 里 try 包裹），默认路径零新依赖导入 |

## 红线（重灾区，逐条自查）
1. **测试安全网**：pytest 严禁真实跑引擎/真实打外部 API/读真实敏感 env——子进程与网络全 mock。测试用假产物目录。
2. scripts/ core/ 零 diff；引擎只经 CLI 子进程消费。
3. 只许动 web/ tests/web/（apscheduler 可入 requirements-web.txt 与 pyproject web extra，因 ENABLE_CRON 可选件需要）。
4. AI 模块任何异常（含 import 失败）不得影响 app 启动与其余端点——验收点 C 专测。
5. 禁 git；函数 <50 行；3.11；无 pandas/numpy/sklearn/xgboost。

## 验收点
A pytest 全绿；B 并发双触发只起一个子进程、第二个返回 queued/already-running 语义；C `web/services/ai.py` 人为改坏后 app 仍能起、其余端点全 200；D jobs/{id} 状态机可轮询到终态、timeout 路径有测试覆盖；E 配额耗尽后 POST → 429。

## 完成信号
`docs/web/M3_report.md` + 哨兵 `docs/web/logs/M3.done`=`M3-DONE`+UTC。
