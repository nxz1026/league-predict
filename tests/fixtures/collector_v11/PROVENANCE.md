# v1.2 夹具来源与选取理由（队长生成，禁改一个字节）

- 真包：`oracle:/srv/league-staging/incoming/cn-collector/`，批 2026-09-15T14-35Z__001 / 2026-09-15T15-03Z__001 / 2026-09-15T15-16Z__001
- 只裁剪行，字段零改动。
## ⚠️ 外壳故意保留两态（回归样本，不是缺陷）
- **真包行 = 9 键**（v1.2：`kind topic snap_ts fetched_at endpoint http_status collector_host payload src_hash`）；
- **旧探针行 = 8 键**（v1.1，无 `fetched_at`）：`errors` 2 行、`jclq_result` 2 行、`jc_issue_result` 后 3 行、`lottery_draw` 后 12 行，共 **19 行**。
  ⇒ 解析层**不得要求 `fetched_at` 存在**（只用于算延迟，绝不参与 `src_hash`／身份键／时序排序）；
  远端历史上还收到过 v1.0 的包，「少一个可选键就报错」的写法一律算缺陷。

**jczq_offer** 91 行 = 第 1 批全 85 行（17 场 × 5 块）+ 第 2 批中 `src_hash` 变化的 6 行。
- 覆盖：同一 `(matchId,block)` 跨两个 `snap_ts`；且这 6 行**价格一字未动、只有 `*f` 旗标归零**（真包实测）
  ⇒ 夹具本身就是「入库不许去噪、CLV 只比价格键」两条裁决的回归样本。
- 键形状：payload **26 键**（生产 `getMatchCalculatorV1`）；`options` 键数 had/hhad 10、crs 66、ttg 20、hafu 23；
  让球线只在 `options.goalLine/goalLineValue`（`HHAD` 样例 `+1`/`+1.00`，`HAD` 块为两个空串）。

**jczq_result** 15 行（第 1 批全量；第 3 批内容与它逐字节相同 ⇒ 不重复收）。
- 覆盖：`sectionsNo1` 半场 / `sectionsNo999` 全场 / `h,d,a` 固定奖金 SP / `winFlag` / `poolStatus=Payout` / `matchResultStatus`；
  含**空比分行**（`sectionsNo999=''`，未开或取消）⇒ 不许把空串当 0。

**jc_issue** 4 行 = 4 个**在售期头**（90/26127、900129/26127、98/26181、94/26188）。
- 关键事实：90 与 900129 **期号同为 26127**（跨玩法重号）⇒ 主键必须 `(game_num,issue_no)`；
- `matchList` 长度 14/14/6/4（对应四种玩法），带 `gmMatchId` ⇒ 可与 `fact.jc_match.match_id` 直连。

**jc_issue_result** 6 行 = 真包 3 行（**上一期、未开奖**：`prizeLevelList=[]`、`matchList[].czScore=''`）
+ 旧探针 3 行（**已开奖**：`prizeLevelList` 长度 3/1/1、`czScore`/`result` 有值，如 `"3＋,1"` 全角）。
- 两态都要有：`jc_issue_prize` 在真包上期望 **0 行**，靠旧探针行才能验奖级展开；FK 孤儿的两种解法也分别可测。
- ⚠️ 真包期头（26126/26180/26187）与 `jc_issue` 期头（26127/26181/26188）**互不重合** ⇒ 3/3 孤儿，父行必须合成。

**lottery_draw** 22 行 = 4 个玩法各 1 期（`85` 大乐透 / `35` 排列3 / **`350133` 排列5** / `04` 7星彩）
+ 第 3 批中与第 1 批**同身份不同 `src_hash`** 的 6 行 + 旧探针 12 行（含 7星彩 `stakeAmount="---"`）。
- 覆盖：同一 `(game_num,issue_no)` 跨批内容变化（`prizeLevelList` 整体换形、`lotterySaleEndTimeUnix` 由 `0` 变 `{}`）
  ⇒ 本 topic 是「必须 DO UPDATE + 类型容错」的唯一现成回归样本。

**jclq_result** 2 行**只来自旧探针**：真包三次都是 `.empty`（篮彩休赛期，官方 `value` 只有 `vtoolsConfig`）。
  按 §9 裁决解析层对它 `raise`（fact 无篮球落点表），保留是为将来建表时有真字段可依。

**errors** 2 行**只来自旧探针**（`P0001` 失败体，`value:null`）：真包 3 批 HTTP 全 200、`errorCode` 全 `"0"`
  ⇒ `kind=error` 分支至今**没有真包样本**，已在回传里要求国内机下次触发时保留样例行。

