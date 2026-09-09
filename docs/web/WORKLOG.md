# WORKLOG — league-predict Web Dashboard（队长台账）

| 日期(BJT) | 里程碑 | 动作 | 状态 |
|---|---|---|---|
| 09-09 18:30 | 立项 | 用户拍板 5 项决策（FastAPI Cloud 部署/调度上云+GHA下线/AI作扩展降级/单账号/router拆分） | ✅ |
| 09-09 18:35 | — | 双仓勘察完成；PLAN.md + WO-M0.md 落仓，分支 `web-dashboard` 建立，commit 4249d2b | ✅ |
| 09-09 18:37 | **M0** | 派工 OMP（omp-call --acp --timeout 1200，pid 13194，日志 docs/web/logs/M0_20260909_183742.log）：产出 DATA_CONTRACT.md + M0_report.md，全仓只读 | ⏳ 进行中 |

## 待办/依赖
- [用户] 申请 FastAPI Cloud 新服务（M5 前到位即可，开发用占位）→ 已入 inbox
- [队长] M0 交付后：抽查契约结论 vs 代码实际（重点：文件命名时区、--all 产物形态、results 关联键），闭环疑点清单，然后写 WO-M1
- [队长] 验收红线速查：引擎 `scripts/` diff 必须为空；新增文件仅限 web/ static/ docs/web/ requirements-web.txt pyproject [web] extra；import 禁 pandas/sklearn/xgboost/tensorflow；无敏感值入库

## 备忘
- 本地 20s 命令上限：OMP 用 nohup+日志文件方式派发，轮询用短命令
- welfare 参照要点：入口 pyproject `[tool.fastapi] entryPoint = "src.api:app"`（league 将为 `web.api:app`）；compose 端口 8000:8080、healthcheck /health、restart unless-stopped（league 本地调试可用 8010 占位）
- 云端若实测无常驻定时器 → 启用 PLAN §1.2 fallback（惰性触发+TTL），M3 时定夺
