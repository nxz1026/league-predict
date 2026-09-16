# collector-cn（国内采集机）

league-predict 系统国内采集机：取中国体育彩票官方 JSON → 落 JSONL → 推远端 oracle。
实施文档：`F:\国内采集机实施文档-v1.md`（§5 契约为准，不得自创字段名）。

## 环境

- Python ≥ 3.9，仅 stdlib（urllib/json/hashlib/pathlib/subprocess/tarfile）
- 出站 ssh 到 oracle（`~/.ssh/config` 已配：`oracle` = ubuntu@140.83.62.161，经 DSH 跳板）
- 时钟 Asia/Shanghai；输出时间戳一律 UTC ISO8601 带 Z

## 用法

```bash
python collector.py --probe            # 探针模式（复探用）
python collector.py --collect <topic>  # 采集指定 topic 落 JSONL
python collector.py --collect-all      # 采集全部 7 topic
python collector.py --push             # 旧路径：打包 out/ → scp+sudo 推 oracle + 空 .done（兼容）
python collector.py --push-batch <topic>...   # v1.2 批量推送（B1 全 7 topic + B2 .done 最后 + G(A) 清单）
```

批量脚本：`scripts/collect_batch.bat offer|night`；计划任务走 `wscript+scripts/collector_silent.vbs [offer|night]`（无窗口）。
- `offer`（默认）= 7 快 topic（jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw），`collector_offer_10m` 专用
- `night` = 8 topic（offer 7 + jc_odds_history），4 个 daily 档（09:30/15:30/21:30/23:30）专用
- `jc_odds_history` 单批 ~60-75s（27 场在售 QPS=1.0），从 10m 快批挪到 daily，防网络挂起时 10m 档堆积僵尸 python（2026-09-16 死机复盘）

## 契约 v1.2（远端 2026-09-15 升级：新增 fetched_at 键 + 7 topic 完整推送 + .done 清单）

- 通用行外壳：`{"kind","topic","snap_ts","fetched_at","endpoint","http_status","collector_host","payload","src_hash"}`（v1.2 新增 `fetched_at` = 响应解析完成时刻，UTC 带 Z）
- `fetched_at` 不进入 `src_hash`、不做身份键，不与 `snap_ts` 混用
- `snap_ts` = 请求发出时刻（UTC 带 Z），同批同值；官方更新时间留 payload 原样
- `kind="error"`：`errorCode != "0"` 或 `success != true` 时必须产行（失败响应无 value 键）
- payload 官方键名原样，不许改名/清洗/判奖（如 `lotterySaleEndtime` 少 a、`stakeAmount` 千分位、`result:"3＋,1"` 全角加号、`sectionsNo999:"取消"`）
- `src_hash` = `sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",",":")))`
- 身份键：offer/result = `matchId`；issue/lottery = `(lotteryGameNum, lotteryDrawNum)`
- `jczq_offer`/`jclq_offer`：一行 = 一场 × 一个玩法（had/hhad/crs/ttg/hafu），`options` 整块 + `oddsHistory` 原样
- `jclq_offer`/`jclq_result` 已冻结（v1.2 解除 "unverified-shape" 标记）：篮球 = NBA/CBA（老板 06:35 决定），`jclq_result` 窗口 = 近 7 日（`{today_minus_7}`~`{today}`）；`jclq_offer` 行粒度 = 一场 × 一个玩法（同 §5.1 足球），玩法 `mnl/hdc/hilo/wnm`
- 采集节奏（v1.3）：
  - **offer 快批档**：`jczq_offer`+`jclq_offer` 快 topic 快照（`collector_offer_10m`），批次含 7 topic 齐全（B1，**不含** `jc_odds_history`）；2026-09-17 起降频为**每小时一次**（原 10 分钟档在用户确认数据密度需求降低后放宽）
  - **4 daily 档**：09:30/15:30/21:30/23:30 = 全 8 topic（含 `jc_odds_history`）；对应 `collector_silent.vbs night`
  - 每批 = **该档 topic 全部齐全**（.jsonl 或 .empty，缺一个 = 批次缺陷，B1）
- **B2 原子推送**：tar 解到 `.staging/` → 逐文件 `mv` 到 topic 目录 → 最后 `install` `.done`（`.done` 是批次最后一步）
- **G(A) `.done` 清单**：`.done` 文件内含 manifest，每行 `<topic>/<file>\t<rowcount>\t<sha256-of-row-bytes>`；**相对路径必须带 `topic/` 前缀**（2026-09-16 修复：前缀缺失导致远端 312 个文件"无主"、每批 440 条回退告警）；`.empty` 行数为 0、聚合列空。远端以清单为准（不再用文件名窗口匹配）
- **`__002` 分片**：10 分钟档同分钟重跑/重试可能追加 `__002`，清单是唯一正确映射（旧文件名窗口匹配已死）

## 探针结论（2026-09-15，13 端点全 200）

| topic | 真实接口 | 备注 |
|---|---|---|
| jczq_offer | `uniform/football/getMatchCalculatorV1.qry?channel=c` | 文档的 getMatchListV1.qry 返 HTTP 567 反爬 |
| jczq_result | `uniform/football/getUniformMatchResultV1.qry?...&matchPage=1&pcOrWap=1` | 文档的 getMatchResultV1.qry 恒空 |
| jc_issue | `lottery/getFootBallConcernV1.qry?param=<gameKey>,0` | gameKey=90/900129/98/94 |
| jc_issue_result | `lottery/getFootBallDrawInfoV2.qry?isVerify=1&param=94,0;90,0;98,0` | 含奖级/销量/滚存 |
| jclq_offer | `uniform/basketball/getMatchCalculatorV1.qry?channel=c` | 彩种已停售，value 提示停止销售 |
| jclq_result | `uniform/basketball/getUniformMatchResultV2.qry` | V2，历史开奖可查 |
| lottery_draw | `lottery/getHistoryPageListV1.qry?gameNo=<no>&provinceId=0&isVerify=1&termLimits=30` | gameNo=85/35/350133/04（文档 3501/3502 无数据） |
| jc_odds_history | `uniform/football/getOddsHistoryV1.qry?channel=c&matchId=<id>` | 新（v1.3）：一行 = 一场在售足球 × 整条赔率走势（6 块 + 元键原样），matchId 取自 getMatchCalculatorV1 的 Selling 场次；定时 8-topic 批 |

## 推送通道

本机无 rsync；远端 `incoming/` 属 `league:league`（ubuntu 在 league 组但无写权限）。
实际：`scp` 打包文件到 `/tmp` → `ssh oracle "sudo -n mv + tar xzf + chown league:league + touch .done"`（ubuntu 免密 sudo）。

## 实施顺序（文档 §3 强制）

1. `--probe` 跑通，探针包 rsync 回传 oracle（`incoming/cn-collector/`）
2. 海外侧核对字段，冻结 §5 契约（版本号 +1）
3. 解析代码只消费冻结后字段，`--collect` 启用
4. cron 定时（09:30/15:30/21:30/01:30 offer；23:05 result；20:10/22:40 issue；23:30 lottery）
5. 验收：3 天连续 cron、7 topic 文件齐全、抽 10 行核对、断网补推无重复

## 红线

- QPS ≤ 1，重试 3 次指数退避（5/15/45s）
- 只 GET 公开 JSON；不登录、不存 cookie、不解析 HTML
- 单批 0 行也产 `.empty` 标记；文件追加写禁止覆盖历史批
- 行内 `src_hash` = 原始 JSON sha256（幂等键）