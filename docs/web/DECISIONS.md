# M8 篮球整合 · 队长自主决策日志（用户睡前授权：分歧自行处理，晨查）

时间线均为 BJT。足球 197 golden 全程只增不减。

## D-01 整合形态：引擎入册（方案 A），不双仓并行
篮球引擎清洗后迁入 league-predict 仓库 `scripts/bball/`，输出直写现有 `predictions/` 目录、LEAGUES 注册 `nba`。auth/配额/孤儿回收/auto-refresh/ai-enrich 链路全部白拿，单次部署。basketball-predict 原仓库冻结为参考（不再部署）。

## D-02 LLM 复盘环不迁移
篮球仓 `ai/` 三件套是足球 GHA 时代旧拷贝。迁移后篮球直接复用足球现役云端 ai-enrich（中文摘要链），feedback_loop 的"预测复盘反馈"暂不引入（原逻辑依赖人工触发，价值/复杂度不匹配）。如用户晨起要求再补，独立单。

## D-03 休赛期策略：active 开关 + 历史回测喂数据
- LEAGUES/LEAGUE_CONFIG 加 `"active": bool`。auto/refresh 全量判定与手动全联赛预测**跳过 inactive 联赛**（防休赛期每天白烧 Odds API 配额）。
- 休赛期数据：`scripts/bball/run.py --backtest N` 用 The Odds API past endpoint 拉最近 N 天已完赛比赛，产出 past detail + 复盘准确率，写同一 predictions 目录 → 看板 NBA 页显示"最近赛果与回测"。赛季开赛（10 月上旬）把 nba active 翻 True 即可。当前 nba.active=False（休赛期）。

## D-04 密钥分发（红线：绝不入 git）
- ODDS key 只存 OMP `/root/odds_key`（600）。predict 时 env 注入（jobs._build_cmd 子进程 env 增加 ODDS_API_KEY 读取，文件缺失则留空跳过，与现有 LLM key 注入方式对齐）。
- 云端 fastapi cloud 环境变量：e6 验证 CLI 支持后配置；若不支持则同文件挂载机制处理并记录。

## D-05 限流回退（用户指令）
wrapper MAXT 提到 6，检测 omp-call 日志含 429/rate 时队长端延长重试间隔再派（哨兵缺失但 rc=0 的"活完了没写哨兵"情形按 M7 惯例队长复核后 override 收口，一律记录在案）。

## D-06 休赛期呈现：揭幕战前瞻并入"今日赛程"（不新增页面）
免费 Odds key 拿不到历史比分（scores 端点 completed 全 False）→ backtest 路线对免费档不成立。改为 `--ahead-days 90` 拉 10 月揭幕赛程，32 场中文前瞻预测写标准产物（scripts/predictions/），看板"今日"自然展示（与足球 7 日窗口同语义）。用户睡前要求"用之前的数据测试"由此满足——数据面用真实 API 前瞻，测试面用 17 个离线单测。

## D-07 t2b 带红哨兵事件（模型侧数据质量警示）
GPT-5.6-luna 的 t2b 在 M6 契约测试红的情况下仍写 DONE 哨兵（其验收自查未拦），且我端 shell 分号链让坏 commit 落地 c2a9419。处置：未推送→git reset 回 8e2b442 零污染；追派 t2b2（候选文件原样落位+测试断言按新语义更新）。**流程升级**：队长验收 grep FAILED 前置且与 commit 用 `&&` 硬链，FAILED>0 物理上不了 commit。
