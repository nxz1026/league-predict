# 契约 v1.1 测试夹具的来源

由队长于 2026-09-15 用国内采集机回传的**真实探针响应**生成（`/tmp/probe_pack`，13 次探针全 HTTP 200）。
生成脚本：`docs/db/make_collector_fixtures.py`（同版本可复跑）。

规则：payload 内所有键名/值/类型**与官方响应逐字一致**（含 `取消`、`3＋,1`、`"12,387"`、`"---"`、`"国  安"` 全角空格、
`lotterySaleEndtime` 的官方少字母拼写），**没有任何清洗或改名**。

为控制体积做的截断（只截列表长度，不截字段）：
- jczq_offer：取 matchInfoList[0].subMatchList 前 8 场 × 5 块
- jclq_offer：官方 errorCode=0 但 value 只有 vtoolsConfig（真无开售）⇒ 按 §7 产 .empty 标记，不产数据行
- lottery_draw：每彩种取 value.list 前 3 期（共 30 期可取）
- lottery_draw：每彩种取 value.list 前 3 期（共 30 期可取）
- lottery_draw：每彩种取 value.list 前 3 期（共 30 期可取）
- lottery_draw：每彩种取 value.list 前 3 期（共 30 期可取）
- errors：lottery_draw__08.json 是真实 P0001 失败响应（endpoint 沿用同 topic 的探针 URL，snap_ts 为占位）
- errors：lottery_draw__09.json 是真实 P0001 失败响应（endpoint 沿用同 topic 的探针 URL，snap_ts 为占位）

`collector_host` 已替换为占位名 `probe-host-01`。
