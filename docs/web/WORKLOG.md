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
| 09-09 19:10 | 机制变更 | 用户指令：**锁定 LinBlue/DeepSeek-V4-Flash-0.1（付费模型），抽风不死不休**。落地：`/root/omp-resilient.sh` 派工器（≤30次重试、单试超时、DONE哨兵、断点续做prompt）；SOP 更新进 PLAN §7。弃用 Kimi 试跑（其骨架成果保留），杀进程时踩坑：pkill -f 模式包含自身命令行＝自杀，改用 "[o]mp" 括号式。 | ✅ |
| 09-09 19:10 | **M0a** | 派工器上线重派（pid 14104，try1/30 开始 19:10:50，单试超时 900s）。完成信号=logs/M0a.done 含 M0a-DONE | ⏳ |
| 09-09 19:39 | M0a 纠偏 | try1 卡死 26 分钟无产出（omp-call 的 `--timeout` 只保护 chunk 收集循环，不覆盖 `session/prompt` 的阻塞读——模型抽风时看门狗失效，重试机制空转）。修复：`/root/omp-resilient.sh` 外层加 `timeout --kill-after=15 (TMO+90)` 硬杀 + 孤儿 acp 子进程清扫；19:40:27 重新起跑（pid 14885） | ✅ |

## 监控体系上线 (20:30–21:12)
- 发现 omp-call 两个结构 bug：req() 吞掉全部 session/update（日志恒 0B、永远"[ACP无返回]"）；turn 结束后空转满 timeout 才退。已修（读流+实时 trace 进 stderr→日志）。
- 模型铁律再确认：ACP --model 必须裸名 DeepSeek-V4-Flash-0.1；带 LinBlue/ 前缀 = 静默挂死。
- 监控三层：① OMP 官方 hook（~/.omp/agent/hooks/heartbeat.ts，经 --hook 显式加载——自动发现在 print/acp 无效）→ hb/heartbeat.jsonl 工具级事件流；② /root/omp-watchdog.sh cron 每分钟：wrapper 死了复活 / 日志+心跳双沉默>12min 戳子进程强制重试 / STATUS.md 状态行；暂停某任务 touch logs/<TAG>.paused；③ 可选推送 /root/omp-notify.conf NOTIFY_URL（ntfy 兼容，待用户 topic）。
- M0a 进度：第 1 节已落盘（predict.py 引证抽查 3/3 属实）；try6 进行中；wrapper 30 次耗尽会被 watchdog 复活续跑。

## M0a 验收 PASS (23:36)
- SUCCESS try8 21:49 BJT；哨兵 2026-09-09T13:30Z；契约 23.8KB（§1-4）。
- 抽证：§2 顶层 keys 与真实 JSON 逐一对上；predict.py:280/329 引证属实；scripts/core 零 diff；commit 00b5516。
- 亮点发现（Web 层直接受益）：①now_utc 是 now_bjt 的别名（变量名撒谎），文件名时间戳=BJT、粒度到小时；②文件名不含联赛码→同小时多联赛互相覆盖→store 层必须按联赛分文件或改命名（§9-1）；③样本 generated_at +00:00 与现版 +08:00 矛盾，已挂 §9 疑点（疑似 GHA 旧版直调）。
- M0b 23:36:53 发车（§5-9+疑点收口），budget 1200s x30，watchdog 已接管 .job。

## 队长文书 (23:45)
- PLAN §7 SOP 修正：派工模型改裸名 DeepSeek-V4-Flash-0.1（带前缀=静默挂死，附 WORKLOG 事故链接）。
- WO-M1.md 定稿：骨架+认证 11 交付物、6 红线、A-E 验收点；暂不加 apscheduler（留给 M3）。
- 09-10 03:18:11  **M0b STALLED 3.5h 未出哨兵 → 流水线停车，待晨间人工处置** (auto-chain)

## 事故：哨兵大小写空转（01:35–05:50）
- M0b 实际 01:35 完成（契约 48.9KB、待补0、报告5.4KB），但 agent 把哨兵写成 `M0B-DONE`（大写B），wrapper/watchdog/pipeline 三处大小写敏感 grep 均不认 → 空转 20 次重试 ×~22min（浪费付费模型调用，late 轮次还在自发打磨 §9 无害亦无效），pipeline 03:18 按规停车（stall commit 682e385，机制本身是对的）。
- 修复：三脚本哨兵检查全部 grep -qi；M0b.job 摘除、halt 清除、wrapper 20972 停止。流水线重启，M0b 将走过闸提交，继续 M1→M4。
- 教训入 skill：完成信号字符串必须机器可判、检查一律大小写不敏感。
- 09-10 05:49:08  **M0b GATE-FAIL（原因见 pipeline.log）→ 流水线停车，越权文件已移 /tmp/forensics/M0b** (auto-chain)
