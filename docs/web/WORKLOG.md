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
| 09-09 18:46 | M5预研 | FastAPI Cloud 官方文档核实：①Scale-to-Zero 默认开，Hobby 套餐 min 恒为0 ⇒ 常驻 cron 不可靠，M3 默认改为「访问时惰性刷新+当日BJT判据」，Pro(min≥1) 才叠加真 cron；②GitHub 集成仅默认分支 push 触发部署（PR/其他分支不触发）⇒ 开发分支安全，merge main 即上线；③.gitignore 生效、predictions/results 历史 JSON 在仓库内 ⇒ 冷启动自带种子数据；④env 敏感值须建为 Secret（创建时定型）；⑤无持久盘声明 ⇒ 会话/新产物重启即失，按风险登记处置 | ✅ |
| 09-09 18:47 | M0 | OMP 仍在执行（pid 13197，LinBlue provider 已解析；--timeout 1200s 上限约 18:57 BJT）；已挂 watcher → docs/web/logs/M0.done；到期未完则重派或转队长自办 | ⏳ |
| 09-09 19:02 | M0 事故 | 首次派工（LinBlue/DeepSeek-V4-Flash-0.1）19 分钟零产出：网关 /v1/models 正常(200/1.6s)，但该模型通道 503 no available channel；GLM-5.3 返回空 content。判读＝默认模型死通道导致 ACP 卡死。已杀进程 | ✅ |
| 09-09 19:04 | **M0a** | 重派：--acp --model Kimi-K2.7-Code（健康）--timeout 1500，策略改为**先建骨架后增量落盘**，范围收敛到契约 1–4 节（5–9 节留 M0b）。日志 M0a_20260909_190418.log，退出写 M0a.done。套餐确认=Hobby（免费档）⇒ M3 定稿「惰性刷新」为主 | ⏳ 进行中 |
