# CODE REVIEW — 代码质量审核报告（非功能）

- 审核人：队长　日期：2026-09-12　基线：main@9b7a89c
- 范围：健壮性 / 函数化（≤50L，功能为单位）/ 死代码 / 死模块。不含功能正确性。
- 手段：AST 全量函数测长、pyflakes 全仓、跨模块 import 引用分析、逐文件人工审读（web 全部 + 引擎抽样）、grep 反模式扫描。

## 结论速览

| 类别 | 数量 | 最高优先级 |
|---|---|---|
| 死模块 | 4 | `.agents/` 389 文件污染（占追踪文件 73%） |
| 死代码（函数/导入/变量/常量） | 20+ | feedback_loop 两个 0 调用函数（~130L） |
| 函数 >50L（应用层） | 11 | predictor.calculate_prediction **336L** |
| 函数 >50L（测试层） | 0 | ✅ |
| 健壮性缺陷 | 9 类 | 孤儿 queued 任务 → 全站 409 锁死 |

web/ 层函数粒度全部达标（无 >50L），store.py 的宽容解析与 tmp+os.replace 原子写、jobs.py 的文件锁、路由层 argv 白名单校验是现有代码的优点，保持。

---

## A. 死模块（建议整体删除）

1. **`scripts/ai_enrich_gha.py`（159L）** — 全仓 0 处 import；GHA 已于 2026-09-11 退役，云端富化走 `web/enrich.py`。输入契约（/tmp/predict_output.txt）只服务已下线平台。删除；`docs/web/` 历史记录不用改。
2. **`ai/feedback_memory.py`（43L）** — 0 引用、无 `__main__`，默认路径 `data/feedback.json` 在仓库里不存在。ECC 移植残留。
3. **`scripts/core/cache.py`（122L）** — 0 处 import（fetch/predict 均未接线）。宣称的 JSON 缓存层从未启用。按 YAGNI 删除；将来要磁盘缓存再按新需求实现。
4. **`.agents/skills/**`（389 个追踪文件，内含 ~2100 行 Python：lark-slides 的 iconpark_tool/template_tool/xml_text_overlap_lint、lark-sheets、lark-mail 模板等）** — 与本项目无关的第三方技能内容被 `git add` 进来了。`git rm -r .agents` + 追加 .gitignore。此项单独 commit。
5. `scripts/core/config.py` 的 constants/leagues re-export shim（~35L 的 noqa 名单）：docstring 自称"backward compatibility"，但仓内新代码已直接 import 子模块。pyflakes 的 26 条 "imported but unused" 全部来自这里。若外部无消费者，建议把 shim 收窄或删掉，让 import 图干净。

## B. 死代码（函数 / 变量 / 导入 / 冗余）

6. **`ai/feedback_loop.py:119 reconcile_results`、`:226 print_metrics_summary`** — 0 调用方（只有文件头注释提了一句）；连带 `METRICS_FILE` 变孤儿。删 ~130L。
7. `web/routers/jobs.py:46 _FORBIDDEN` — 定义了但 `_validate_args` 从不引用（未知参数校验用的是内联集合）。三份参数真值表（_FLAG_ARGS/_VALUE_ARGS/_FORBIDDEN）合一，删 `_FORBIDDEN`。
8. `web/services/jobs.py run_job`：`cmd = _build_cmd(args) if script == "predict" else _build_cmd(args, script)` — 两分支等价，`_build_cmd` 默认参数已处理 predict。化简为 `_build_cmd(args, script)`。
9. `web/services/ai.py try_ai_status`（+`config.AI_RESPONSE_TIMEOUT`）— 用 daemon 线程给一次纯本地文件读套"超时"，`ai_status()` 本身已全量防御、永不抛穿；超时后线程反而成为悬挂资源。拆掉包装，`routers/ai.py` 直调 `ai_status()`。
10. 未用导入（pyflakes 实锤，逐条删）：`ai/batch_pipeline.py` os；`ai/feedback_loop.py` os；`scripts/core/backtest.py` FOOTBALL_DIR、logger；`dashboard.py` json、FOOTBALL_DIR；`data/convert.py` logger；`data/fetch.py` as_completed、Path；`data/parse.py` json；`i18n.py` Path、Any；`model/features.py` math；`model/monte_carlo.py` L9 `dixon_coles_pmf`（L14 重复导入遮蔽，删 L9）。
11. 未用局部变量：`data/parse.py:301 spread_h_open`；`elo.py:118-122 score_a`（update_elo 内部由 score_h 推客队分，改 `score_h, _ =`）；`monte_carlo.py:202 current_round`；`tests/web/test_m6_ai_enrich.py:117 recorded`。
12. 文档腐烂（改动时顺手修）：`jobs.trigger_ai_enrich` 与 `routers/jobs.py` ai-enrich 端点 docstring 仍写"脚本 scripts/ai_enrich_gha.py"——实际执行 `-m web.enrich`（A.1 删除后此错更显眼）。

## C. 函数化 >50L（应用层 11 个；测试层 0 个 ✅）

| 位置 | 函数 | 行数 | 拆分建议（按既有内聚缝） |
|---|---|---|---|
| scripts/core/predictor.py:31 | calculate_prediction | **336** | 段注释即天然刀口：`_resolve_dc_rho` / `_apply_calibration` / `_blend_signals`（方向概率+draw 修正） / `_fuse_ml` / `_compute_lambdas` / `_score_lines`（DC/泊松+BTTS） / `_consistency_and_ci`。主函数变 ~40L 编排器 |
| scripts/core/data/parse.py:223 | parse_events | 173 | `_warm_i18n` / `_classify_events` / `_split_windows`（past/future/in_progress 各自成函数） |
| scripts/predict.py:233 | run_league | 155 | 步骤 1–9 注释即拆分单位：`_fetch_and_parse` / `_update_elos` / `_calibrate` / `_fit_rho` / `_build_predictions` / `_monte_carlo_step` / `_backtest_step` / `_emit_outputs` |
| scripts/predict.py:390 | main | 57 | argparse 分派与联赛循环分离 |
| model/monte_carlo.py:136 | simulate_world_cup | 120 | 种子分组 / 逐轮推进 / 冠军概率各自成函数（bracket/sequential 两分支已部分抽出，沿用模式） |
| model/poisson.py:113 | fit_dc_rho | 68 | 网格搜索与目标函数分离 |
| model/features.py:64 | extract_features | 66 | 特征组分块（form/record/odds/h2h） |
| model/monte_carlo.py:38 | monte_carlo_champion | 65 | 模拟循环与统计汇总分离 |
| model/onside.py:77 | compute_onside_signals | 57 | 四信号一函数一个 |
| model/poisson.py:58 | dixon_coles_match_probs | 53 | λ 修正与概率表构建分离 |
| scripts/core/elo.py:94 | process_match_result | 51 | 顺手（结果解析可并入 helper） |
| web/api.py:46 | create_app | 50 | 贴线：lifespan、路由挂载各抽 ~20L 小函数 |

原则复核：这些都不"必须"超 50 行——predictor 与 run_league 是纯粹的历史堆积，内部结构注释早已按功能分段，只是没落成函数。

## D. 健壮性缺陷（按危害排序）

**D1（高）孤儿任务全站锁死** — `web/services/jobs.py` + `routers/jobs.py`
`create_job` 落盘与 `_executor.submit(run_job)` 非原子：容器冷启动重启、submit 抛异常、或 `_lazy_auto_trigger` 在 submit 前 `marker.write_text` 失败，都会留下永久 queued/running 状态文件；此后 `active_job()` 永远命中非终态 → 所有新触发 409，唯一解药是删文件或重启。
修法：`active_job()` 内做过期回收——`status==running 且 started_at + 2*PREDICT_TIMEOUT < now` 或 `queued 且 created_at + 60s < now` 且无活线程持锁 → `_spin_state(..., STATUS_FAILED, error="recovered orphan")`。同时 `_lazy_auto_trigger` 把 marker 写入挪到 submit 成功之后。

**D2（高）409 白耗配额** — `jobs._spawn` 先 `quota_consume()` 再查 `active_job()`；并发拒绝路径不退券。修法：先并发守卫后消费配额，或在 already_running 分支回补 count。

**D3（高）登录 500** — `web/auth.py:76-77` `hmac.compare_digest(str,str)` 遇非 ASCII 用户名/密码抛 TypeError → 500（且绕过锁定记账）。修法：两侧 `.encode("utf-8")` 再比较。

**D4（中）LockTimeout 裸 500** — `_exclusive_lock` 超时异常无路由层映射，errors.register 兜底成 500。修法：routers 捕获 → 409/503 + `code="lock_busy"`。

**D5（中）_spawn TOCTOU 竞态** — active_job 检查与 create_job 写入间无锁，两并发请求可双双通过。修法：检查+创建整体包进 `JOBS_LOCK_FILE` 临界区（run_job 已用同锁，语义吻合）。

**D6（中）SQLite 连接不关** — `session_store._connect()` 各处 `with conn:` 只提交事务不关闭（create/validate/delete 与 api.py lifespan 的 `_conn`）。CPython 靠引用计数兜底，但属未定义行为依赖。修法：`contextlib.closing` 包一层，或统一 `_with_conn()` 辅助。

**D7（中）GET 带副作用** — `GET /jobs/auto/refresh` 会创建任务并扣配额，浏览器预取/探活可触发。修法：改 POST（前端同步一处调用点）。另：去重 marker 用 UTC 日、配额用 BJT 日，跨日窗口可双触发，统一 BJT。

**D8（低）启动期 env 解析裸奔 + 默认密码** — `web/config.py` 模块级 `int(os.getenv(...))` 任意一个坏值 → import 即崩（全端点 500 无提示）；`AUTH_PASSWORD` 缺省为可猜测占位值。修法：`_env_int(name, default)` 容错回退 + warning；生产模式（如 `ENV=prod` 或检测到非本机 HOST）下 AUTH_PASSWORD 缺失即拒绝启动。

**D9（低，系统性）open() 无 encoding ×41 处** — 引擎侧读写中文 JSON 全靠容器 locale 兜底。修法：全部补 `encoding="utf-8"`（可脚本化改一遍，跑测试即可验收）。

其余顺手项：
- `calibration.py:15,107`、`ml_model.py:172` 字符串注解 `"Path"` 但从未 import Path（类型提示说谎，`get_type_hints` 即炸）→ 真 import；`fetch.py:58,62` 的 `Any` 同（且 fetch/i18n 首行 `from __future__` 导致下一行 docstring 不再是模块 docstring，移位）。
- `_spin_state` 的默认 job dict 与 `create_job` 重复维护 → `create_job` 复用之。
- cron.py `from web.routers.jobs import _executor` 依赖路由层私有符号 → executor 移入 `web/services/jobs.py` 导出 `submit(job_id)`。
- `auth._failures` 无上限/无过期清理 → 记录 lockout_until 时顺带 evict。
- `ai_enrich_gha.py:159` f-string 无占位符——随 A.1 删除自然消失。

## 处置建议

拆成两张工单派 OMP：
- **WO-M7a 清理单**（低风险，先走）：A1–A4 删除 + B6–B12 + D9 + 类型注解修正；纯删与改字，预期测试 192 全绿即验收（个别测试引用被删模块需同步删）。
- **WO-M7b 健壮性单**：D1–D8 + C 表前四个巨型函数拆分（predictor/parse_events/run_league/main），每项先补最小复现测试再改；C 表其余 7 个可作为 M7c 渐进还债。

两单各自独立 commit、全量 pytest 绿 + 本地 `build_league_web.sh` + 云端 deploy15 冒烟（health/登录/ai-enrich 一轮）后合并。
