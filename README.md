# League Predict

联赛预测引擎。多数据源融合 + 信号模型 + ELO + Dixon-Coles 双变量泊松 + 蒙特卡洛模拟。

零外部依赖，纯 Python stdlib。每日 21:00 (BJT) 通过 GHA 自动运行。

## 架构

```
数据源                             特征                     模型                      输出
────                               ────                     ────                      ────
API-Football (含赔率)               赔率去水 (remove_vig)       Onside 4+1 信号加权        JSON (stdout)
football-data.org (历史)          → form/record 评分       → ELO 场级更新            → stderr 人类摘要
ESPN (无 key 降级)                  盘口移动量化                Dixon-Coles 双变量泊松
                                    ELO 期望得分             蒙特卡洛 10k 次模拟
                                    26 维 ML 特征向量 (实验性)
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
home_strength = market_home × 20% + onside_home × ~70% + elo_home × 18% + spread_movement × 0.5
away_strength = market_away × 20% + onside_away × ~70% + elo_away × 18% - spread_movement × 0.5
draw_strength = market_draw × 20% + draw_base

P(home) = home_strength / sum
```

### ELO 评分

- K=20, 主场加成 100, 净胜球自适应 K 值
- `expected_score` 使用标准公式: `1 / (1 + 10^((elo_b - elo_a_home) / 400))`
- 场级即时更新，持久化至 `references/.elo_ratings.json`

### 比分预测 (Dixon-Coles)

- λ_home = raw_home_strength × league_multiplier (联赛差异化，非统一 2.8)
- λ_away = raw_away_strength × league_multiplier
- ρ 按联赛差异化: EPL=0.17, Serie A=0.28, Bundesliga=0.19 等
- τ 校正含 `max(0, tau)` 钳位，防止负概率
- 三分搜索 + 网格兜底拟合
- 遍历 0-8 球联合概率, 输出 top-3 + 95% CI

### 校准

- 历史累积分布修正
- Onside 信号使用专用 `onside_home_correction` / `onside_away_correction` 减半因子
- 指数平滑持久化

### 蒙特卡洛

- 逐场 Poisson 采样, 10k 次完整赛季模拟
- 淘汰赛: 标准 World Cup 对阵表 (A1vB2, C1vD2, ...)
- 收敛诊断: std_error, 95% CI

### ML 特征工程 (实验性)

> ⚠️ 此模块为实验性功能，特征集和接口可能在版本间变更。

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
├── predict.py                 # CLI 入口 (run_league 拆分为 6 个子函数)
├── core/
│   ├── predictor.py           # 预测计算入口
│   ├── elo.py                 # ELO 评分系统
│   ├── config.py              # re-export (向后兼容)
│   ├── constants.py           # 路径/URL/重试/模型参数/权重/阈值/映射
│   ├── leagues.py             # 联赛配置 + DC ρ + λ 乘数
│   ├── cache.py               # 文件缓存 (TTL 过期 + 键生成 + 清理)
│   ├── log.py                 # 日志 (支持 LEAGUE_PREDICT_LOG_LEVEL)
│   ├── data/
│   │   ├── fetch.py           # API-Football / football-data / ESPN 并行聚合
│   │   ├── parse.py           # 赔率解析 + 去水 + 特征提取
│   │   └── convert.py         # API-Football → ESPN 格式 (含赔率)
│   ├── model/
│   │   ├── onside.py          # Onside 4 信号 (FIFA排名/联赛足迹/主场/足联)
│   │   ├── poisson.py         # Poisson / Dixon-Coles (τ 钳位)
│   │   ├── monte_carlo.py     # 蒙特卡洛 10k 模拟 (标准淘汰赛对阵)
│   │   └── features.py        # 26 维 ML 特征工程 (实验性)
│   ├── calibration.py         # 自动校准
│   ├── backtest.py            # 回测 + 复盘
│   ├── rankings.py            # FIFA 排名统一入口
│   └── output.py              # 输出 / 文件清理 (合并策略)
├── predictions/               # 预测结果 JSON (自动生成)
├── results/                   # 实际赛果 JSON (自动生成)
└── references/                # 排名 / 文档 / 趋势
```

## 支持的联赛

| 键 | 联赛 | 默认数据源 | API-Football ID | DC ρ | λ 乘数 |
|----|------|-----------|----------------|------|--------|
| epl | English Premier League | api-football | 39 | 0.17 | 2.8 |
| laliga | La Liga | api-football | 140 | 0.22 | 2.7 |
| bundesliga | Bundesliga | api-football | 78 | 0.19 | 3.2 |
| seriea | Serie A | api-football | 135 | 0.28 | 2.5 |
| ligue1 | Ligue 1 | api-football | 61 | 0.21 | 2.7 |
| mls | Major League Soccer | espn | 253 | 0.23 | 2.9 |
| jleague | J-League | football-data | 98 | 0.20 | 2.8 |
| csl | Chinese Super League | api-football | 169 | 0.22 | 2.9 |

## 技术栈

- **零外部依赖**: urllib + json + gzip + math + pathlib (全 stdlib)
- **赔率处理**: 十进制 → 美式 → 三向去水 (比例法)
- **去水方法**: `p_home / (p_home + p_draw + p_away)`
- **ELO**: K=20, 主场加成 100, 净胜球自适应 K 值
- **Dixon-Coles**: 联赛差异化 ρ, τ 钳位防负概率, 三分搜索优化
- **蒙特卡洛**: 逐场 Poisson 采样, 10k 次完整赛季模拟, 标准 World Cup 淘汰赛对阵
- **校准**: 历史累积分布修正, onside 信号专用减半因子
- **缓存**: 文件级 TTL 缓存, 过期清理, URL 键生成
- **并行获取**: API-Football + ESPN fallback 并行请求
- **API 校验**: 响应结构验证 + 速率限制追踪

## v4.1 变更日志

### 致命修复 (P0)
- **ELO 公式符号**: `expected_score` 指数项 `(effective_a - elo_b)` → `(elo_b - effective_a)`, 修复强队系统性低估
- **Dixon-Coles 负概率**: `tau_correction` 加 `max(0, tau)` 钳位, 防止 1-1 比分时 ρ×λ_h×λ_a 超限
- **Calibration 双重修正**: Onside 信号使用专用 `onside_home_correction` 减半因子, 不再与 market odds 重复修正

### 高优先级 (P1)
- 测试 mock 字段名统一 (`home_prob` → `home_true_prob`)
- 移除 MyMemory 翻译 API (COUNTRY_CN 字典已覆盖)
- Backtest 移除硬编码数据源检查, 新增 `_backtest_api_football()`
- Monte Carlo 标准世界杯淘汰赛对阵表 (A1vB2 模式)
- Fetch API 响应结构校验 (`_validate_api_response`)

### 中优先级 (P2)
- `ELO_WEIGHT` 移入 `THRESHOLDS` 配置化
- FIFA 排名获取统一委托 `rankings.py`
- `COUNTRY_CONFEDERATION` 重复键清理
- API-Football 速率限制追踪 (`_rate_limit_info`)
- 日志级别环境变量支持 (`LEAGUE_PREDICT_LOG_LEVEL`)

### 低优先级 (P3)
- `__import__` 改顶部 import
- 线程安全问题随 MyMemory API 移除消除
- ELO 测试覆盖 20 个用例
- `save_results` 改合并策略

### 重构 (P4)
- P-label 注释清理
- `run_league` 拆分为 6 个子函数
- `config.py` 拆分为 `constants.py` + `leagues.py` + `config.py` (re-export)

### 增强 (P5)
- ML 特征管线标记为实验性
- Cache 补全 TTL 过期清理 + URL 键生成 + `purge_expired()`
- API-Football + ESPN fallback 并行获取 (`ThreadPoolExecutor`)
- JSON→SQLite/Parquet 评估: 数据量 ~95KB, 无迁移必要