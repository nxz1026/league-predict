# League Predict

联赛预测引擎。多数据源融合 + 信号模型 + ELO + Dixon-Coles 双变量泊松 + 蒙特卡洛模拟。

零外部依赖，纯 Python stdlib。

## 架构

```
数据源                             特征                     模型                      输出
────                               ────                     ────                      ────
API-Football (含赔率)               赔率去水 (remove_vig)       Onside 4+1 信号加权        JSON (stdout)
football-data.org (历史)          → form/record 评分       → ELO 场级更新            → stderr 人类摘要
ESPN (无 key 降级)                  盘口移动量化                Dixon-Coles 双变量泊松
                                   ELO 期望得分             蒙特卡洛 10k 次模拟
                                   26 维 ML 特征向量
```

## 数据源对比

| 源 | 赔率 | 覆盖 | 免费额度 | 默认联赛 |
|---|------|------|---------|---------|
| **API-Football** | 33 家博彩公司, 1X2/盘口/大小球 | 全联赛, 最近 3 天 | 100 次/天 | EPL, La Liga, Bundesliga, Serie A, Ligue 1 |
| **football-data.org** | 无 | 全联赛, 全历史 | 10 req/min | 备用 |
| **ESPN** | 有限 (DraftKings) | MLS, 中超, 国际赛 | 无限制 | 降级回退 |

## 预测模型

### 信号融合公式

```
home_strength = market_home × 20% + onside_home × ~70% + elo_home × 10% + spread_movement × 0.5
away_strength = market_away × 20% + onside_away × ~70% + elo_away × 10% - spread_movement × 0.5
draw_strength = market_draw × 20% + draw_base

P(home) = home_strength / sum
```

### 比分预测 (Dixon-Coles)

- λ_home = raw_home_strength × 2.8
- λ_away = raw_away_strength × 2.8
- ρ 自适应拟合 (三分搜索 + 网格兜底)
- 遍历 0-8 球联合概率, 输出 top-3 + 95% CI

### ML 特征工程

26 维特征向量已就绪, 可直接用于 XGBoost / sklearn 训练:

| 类别 | 特征数 | 包含 |
|------|--------|------|
| 赔率特征 | 4 | 去水概率, 赔率可用性 |
| 球队状态 | 4 | form score, record score |
| 市场信号 | 3 | spread movement, ML implied |
| 信号模型 | 4 | Onside score, FIFA score |
| ELO 特征 | 4 | expected, rating, diff |
| 交叉特征 | 6 | form/record 差积, odds/elo 差 |
| 主场 | 1 | is_host_country |

```python
from core.model.features import extract_features, build_training_set, FEATURE_COLUMNS

# 单场特征
vec = extract_features(match, {"elo_ratings": elo})

# 训练集
X, y = build_training_set(past_matches, {"elo_ratings": elo})
```

## 快速开始

```bash
# 环境变量 (API-Football 用于赔率, football-data.org 备用)
export API_FOOTBALL_KEY=your_key
export FOOTBALL_DATA_API_KEY=your_key

# 预测 EPL (默认 API-Football, 含赔率)
python3 scripts/predict.py --league epl

# 使用 football-data.org (历史数据)
python3 scripts/predict.py --league epl --data-source football-data

# MLS (默认 ESPN)
python3 scripts/predict.py --league mls

# 蒙特卡洛冠军模拟
python3 scripts/predict.py --league epl --monte-carlo

# 指定日期范围
python3 scripts/predict.py --league epl --dates 20250101-20250131

# 回测
python3 scripts/predict.py --league epl --backtest
```

## 文件结构

```
scripts/
├── predict.py                 # CLI 入口
├── core/
│   ├── predictor.py           # 预测计算入口
│   ├── elo.py                 # ELO 评分系统
│   ├── config.py              # 联赛配置 + 阈值
│   ├── data/
│   │   ├── fetch.py           # API-Football / football-data / ESPN 聚合
│   │   ├── parse.py           # 赔率解析 + 去水 + 特征提取
│   │   └── convert.py         # API-Football → ESPN 格式 (含赔率)
│   ├── model/
│   │   ├── onside.py          # Onside 4 信号 (FIFA排名/联赛足迹/主场/足联)
│   │   ├── poisson.py         # Poisson / Dixon-Coles
│   │   ├── monte_carlo.py     # 蒙特卡洛 10k 模拟
│   │   └── features.py        # 26 维 ML 特征工程
│   ├── calibration.py         # 自动校准
│   ├── backtest.py            # 回测 + 复盘
│   ├── rankings.py            # FIFA 排名统一入口
│   └── output.py              # 输出 / 文件清理
├── predictions/               # 预测结果 JSON (自动生成)
├── results/                   # 实际赛果 JSON (自动生成)
└── references/                # 排名 / 文档 / 趋势
```

## 支持的联赛

| 键 | 联赛 | 默认数据源 | API-Football ID |
|----|------|-----------|----------------|
| epl | English Premier League | api-football | 39 |
| laliga | La Liga | api-football | 140 |
| bundesliga | Bundesliga | api-football | 78 |
| seriea | Serie A | api-football | 135 |
| ligue1 | Ligue 1 | api-football | 61 |
| mls | Major League Soccer | espn | 253 |
| jleague | J-League | football-data | 98 |
| csl | Chinese Super League | espn | 169 |

## 技术栈

- **零外部依赖**: urllib + json + gzip + math + pathlib (全 stdlib)
- **赔率处理**: 十进制 → 美式 → 三向去水 (比例法)
- **去水方法**: `p_home / (p_home + p_draw + p_away)`
- **ELO**: K=20, 主场加成 100, 净胜球自适应 K 值
- **Dixon-Coles**: ρ ∈ [-0.3, 0.3], 三分搜索优化
- **蒙特卡洛**: 逐场 Poisson 采样, 10k 次完整赛季模拟
- **校准**: 历史累积分布修正, 含 onside 信号修正
