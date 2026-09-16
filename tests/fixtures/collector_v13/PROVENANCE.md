# `jclq_result__23.jsonl` 出处（队长 2026-09-16 07:47 落夹具）
- 来源：国内采集机 **v1.3 清单包** `cn-collector/jclq_result/2026-09-15T23-01Z__001.jsonl`（北京 07:01 那一批），
  随《回传-v1.2执行报告》H 节一起推到 staging；我方 07:15 独立复算 **23/23 行 `src_hash` 与官方公式一致**。
- 为什么只有 23 行赛果、没有盘口：**NBA/CBA 休赛期**，官方 `jclq_offer.matchInfoList` 实测为空 ⇒ 盘口形状仍是推断，
  故本夹具**只冻结赛果**（`jclq_offer` 等开售窗口再补，见 OMP-SKILL §9-50）。
- 内容：7 日窗口内的篮彩完场赛果，`leagueId ∈ {7 女篮世界杯, 8 亚运会男篮}`，**不含 NBA/CBA**（休赛期无场次）。
  `matchId` 23 个互不相同；`finalScore` 形如 `"61-105"`；`status` 全为 `2`；`poolStatus` 全为空串；
  四玩法块 `mnl/hdc/hilo/wnm` 的非空计数（**单批 23 行的真值，测试就按这个钉**）：
  | 块 | goalLine 非空 | winOdds 非空 | resultStatus 非空 | combination 非空 |
  |---|---|---|---|---|
  | mnl | 0 | 14 | 9（值为中文「未开售」） | 14 |
  | hdc | 23 | 23 | 0 | 23 |
  | hilo | 23 | 23 | 0 | 23 |
  | wnm | 0 | 15 | 8（中文「未开售」） | 15 |
- 用法：`parse_jbq` 的期望值与 `fact.jbq_*` 的装载 oracle 都以本文件为准；**不许**为过测试改本文件（要改先改契约）。
