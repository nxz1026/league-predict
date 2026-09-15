# collector-cn（国内采集机）

league-predict 系统国内采集机：取中国体育彩票官方 JSON → 落 JSONL → 推远端 oracle。
实施文档：`F:\国内采集机实施文档-v1.md`（§5 契约为准，不得自创字段名）。

## 环境

- Python ≥ 3.9，仅 stdlib（urllib/json/hashlib/pathlib/subprocess/tarfile）
- 出站 ssh 到 oracle（`~/.ssh/config` 已配：`oracle` = ubuntu@140.83.62.161，经 DSH 跳板）
- 时钟 Asia/Shanghai；输出时间戳一律 UTC ISO8601 带 Z

## 用法

```bash
python collector.py --probe            # 探针：逐个 GET 候选端点 → probe/probe_pack.tar.gz
python collector.py --collect <topic>  # 采集落 JSONL（契约冻结后启用）
python collector.py --push             # 打包 out/ → scp+sudo 推 oracle + .done
```

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