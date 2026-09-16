# 盘口全历史样本（契约 v1.4 的实测依据）
- 来源：国内采集机 2026-09-16 09:12 北京 回传目录 `odds_history_sample/`（我方**只读复制**，原样未改一个字节）
- 端点：`getOddsHistoryV1.qry?channel=c&matchId=<id>`（见 `docs/project/契约v1.4-盘口全历史.md`）
- ⚠️ 样本里两行的外壳 `topic` 写成了 `jczq_offer`（**v1.4 已要求改成 `jc_odds_history`**）；本目录**只用于解析器测试**，
  永不放进任何装载 `--dir`（否则会被当普通盘口快照误解析）。
- 实测硬数（`python3` 现算，不是估计）：2 行 / `payload` 顶层 16 键 / 价格版合计 **34**（had 7 · hhad 9 · crs 6 · ttg 6 · haf 6）
  / 同 `(matchId, 玩法, updateDate+updateTime)` **0 组撞键** / 数组顺序**严格新→旧** / `src_hash` 复算**两行全一致**
- ⚠️ 两场的 `matchId`（2041482 卡塔尔亚 vs 韩国亚、2041495 柏太阳神）**都不在** `fact.jc_match`，
  也**不在**用户 06:35 定的联赛封闭清单内 ⇒ 只用来证明形状与算法，**不代表我们要预测它们**。
