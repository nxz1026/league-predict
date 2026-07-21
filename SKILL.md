---
name: league-predict
description: 联赛预测引擎。多数据源（API-Football/football-data.org/ESPN），信号模型 + ELO + Dixon-Coles 泊松 + 蒙特卡洛模拟。零外部依赖，纯 Python stdlib。
---

# League Predict — 联赛预测引擎

每日自动预测未来 24h 比赛，回填前 24h 结果，产出复盘。支持 5 大联赛 + MLS + J 联赛 + 中超。

## 架构概览

```
数据源层              解析层              模型层              输出层
─────────            ─────              ─────              ─────
API-Football (赔率)   格式统一化           Onside 4+1 信号      JSON
football-data.org  → 去水 (remove_vig)  → ELO 评分         → stdout
ESPN (降级回退)        特征提取            Poisson / DC       stderr 摘要
                                         蒙特卡洛模拟
```

## 数据源

| 源 | 赔率 | 覆盖范围 | 免费额度 |
|---|------|---------|---------|
| **API-Football** | 有（33 家博彩公司） | 全联赛，最近 3 天 | 100 次/天 |
| **football-data.org** | 无 | 全联赛，历史数据 | 10 次/分 |
| **ESPN** | 有（仅部分联赛） | MLS/中超/世界杯 | 无限制 |

- 5 大联赛默认走 **API-Football**（含赔率），自动回退到 ESPN
- 使用 `--data-source` 强制指定数据源
- 离线赛季自动降级到 ESPN（无赔率模式）

## 预测模型

### 信号融合

```
最终概率 = 市场赔率 × 20% + Onside 信号 × (80% - ELO%) + ELO × 10% + 盘口移动修正
```

| 信号 | 权重 | 说明 |
|------|------|------|
| 市场赔率去水 | 20% | 三向去水后真实概率 |
| Onside 4 信号 | ~70% | FIFA排名 + 联赛足迹 + 主场优势 + 足联强度 |
| ELO 评分 | ~10% | 场级更新，替代静态月度排名 |
| 盘口移动 | ±修正 | spread open→close 方向量化 |

### 比分预测

- **Dixon-Coles 双变量泊松** — ρ 自适应拟合（低分平局校正）
- **λ 映射** — raw_strength × 2.8 → 期望进球
- **输出** — top-3 最可能比分 + 概率 + 95% 置信区间

### 蒙特卡洛 10k 次

淘汰赛/联赛冠军模拟。

### ML 特征工程

26 维特征向量已就绪（含赔率/ELO/Onside/交叉特征），`build_training_set()` 可生成训练集。安装 XGBoost 后即可训练。

## 运行

```bash
# 默认 EPL（API-Football + 赔率，离线季自动降级 ESPN）
python3 scripts/predict.py --league epl

# 指定 football-data.org
python3 scripts/predict.py --league epl --data-source football-data

# MLS（默认 ESPN）
python3 scripts/predict.py --league mls

# 蒙特卡洛模拟
python3 scripts/predict.py --league epl --data-source football-data --monte-carlo

# 自定义日期范围
python3 scripts/predict.py --league epl --dates 20240816-20240818

# 禁用 Dixon-Coles
python3 scripts/predict.py --league epl --no-dc

# 清理 7 天前旧文件
python3 scripts/predict.py --cleanup
```

## 输出

- **stdout**: JSON（预测结果 + 回填 + 校准 + 蒙特卡洛）
- **stderr**: 人类可读摘要（数据源、信号分解、校准信息）

## 文件结构

```
scripts/
├── predict.py                # CLI 入口
├── core/
│   ├── predictor.py          # 预测计算入口
│   ├── elo.py                # ELO 评分系统
│   ├── config.py             # 联赛配置 + 阈值
│   ├── data/
│   │   ├── fetch.py          # 多数据源聚合
│   │   ├── parse.py          # 赔率解析 + 去水
│   │   └── convert.py        # 格式转换
│   ├── model/
│   │   ├── onside.py         # Onside 4 信号
│   │   ├── poisson.py        # Poisson / Dixon-Coles
│   │   ├── monte_carlo.py    # 蒙特卡洛模拟
│   │   └── features.py       # ML 特征工程
│   ├── calibration.py        # 自动校准
│   ├── backtest.py           # 回测评估
│   └── output.py             # 输出/存档
predictions/                  # 预测结果 JSON
results/                      # 实际赛果 JSON
references/                   # FIFA 排名、趋势、文档
```

## 配置

- `scripts/core/config.py` — 联赛配置（league_id、api_football_id、espn_slug、data_source）
- 新增联赛：在 `LEAGUE_CONFIG` 添加条目，确保 `api_football_id` 与 API-Football 联赛 ID 对应
- 阈值集中管理在 `THRESHOLDS` 字典

## 参考文档

- `references/odds-math.md` — 美式赔率解析与去水公式
- `references/poisson-math.md` — Poisson 比分分布设计
- `references/calibration-architecture.md` — 校准架构决策
- `references/country-codes.md` — 中英文队名映射

## Pitfalls

1. **赔率仅来自 API-Football** — ESPN 赔率只在特定联赛（MLS/中超）可用。5 大联赛必须有 API_FOOTBALL_KEY 环境变量。
2. **免费计划限制** — API-Football 免费计划只能查最近 3 天 + 100 次/天。赛季中够用，休赛季无数据。
3. **ESPN "Away at Home" 格式** — 原始 match 字段是 "客队 at 主队"，内部已转换为 "主队 vs 客队"。使用 display 字段输出。
4. **预测不调用 LLM** — 所有计算是确定性 Python。LLM 只在 Hermes 编排模式下做输出格式化，不影响预测结果。
