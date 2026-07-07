# World Cup Predict v3.1

2026 世界杯预测引擎。Onside 4+1 信号模型 + Dixon-Coles 泊松 + 蒙特卡洛模拟。

## 架构

```
ESPN API → 解析 → Onside 4+1 信号 → 综合强度 → Poisson/DC → 蒙特卡洛
                                    ↑ ELO
```

### 核心组件

| 组件 | 说明 |
|------|------|
| **数据源** | ESPN API（免费，零依赖） |
| **信号模型** | FIFA排名 + 联赛足迹 + 东道主 + 足联实力 + ELO |
| **市场融合** | Shin 去水 + 加权融合（market 30% + onside 70%） |
| **比分预测** | Dixon-Coles 双变量泊松（ρ 自适应拟合） |
| **冠军模拟** | 蒙特卡洛 10k 次 |
| **集成投票** | 多 ρ 参数多数决 |
| **校准回路** | 累积历史分布修正 + 回测 |

## 运行

```bash
# 本地测试
python3 scripts/predict_wc.py --no-fetch

# 实时数据
python3 scripts/predict_wc.py

# 蒙特卡洛模拟
python3 scripts/predict_wc.py --monte-carlo

# 清理旧文件
python3 scripts/predict_wc.py --cleanup
```

## 输出

- **stdout**: JSON（预测结果 + 回测 + 蒙特卡洛）
- **stderr**: 人类可读摘要（数据来源、信号分解、投票结果）

## 修复日志

| 版本 | 日期 | 改动 |
|------|------|------|
| v3.1 | 2026-07-07 | P0: 修复权重缩放/λ不一致/ρ拟合bug |
| v3.1 | 2026-07-07 | P1: market_odds 0.30 + 指数衰减 + Shin去水 + ELO |
| v3.1 | 2026-07-07 | P2: 集成多ρ投票 |
| v3.1 | 2026-07-07 | P3: 预测摘要输出 + 回测窗口30天 + 阈值调优 |

## 文件结构

```
scripts/
├── predict_wc.py      # 核心引擎（零外部依赖）
├── send_cron_card.py  # 飞书推送
├── parse_espn.py      # ESPN 解析器
references/
├── fifa_rankings.json # FIFA 排名
├── tournament-trends.md
├── country-codes.md
predictions/           # 预测结果
results/               # 实际赛果
```

## 技术细节

- **零外部依赖**: 纯 stdlib（urllib + json + math + gzip）
- **Dixon-Coles**: ρ 自适应拟合（网格搜索 per-match λ）
- **ELO**: 从历史比赛自算，初始 1500, K=32, 主客因子 60
- **Shin 去水**: 几何平均法替代比例法
- **集成投票**: 3 组 ρ 参数（0.15/拟合值/0.25）多数决
