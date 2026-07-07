# 业界足球比赛预测方案调研报告

> 调研时间：2026-07-07
> 目标项目：/tmp/world-cup-predict/scripts/predict_wc.py（2152 行 Python，零外部依赖）
> 当前算法：Onside 4 信号模型 + Dixon-Coles 泊松 + 蒙特卡洛模拟
> 调研范围：FiveThirtyEight SPI、Opta、博彩赔率模型、Kaggle 获奖方案、学术界经典模型、xG 模型

---

## 1. 当前项目全景（用于对标）

**核心流程**：ESPN API → 解析（ML/spread/form/records）→ Onside 4 信号（FIFA排名+联赛footprint+东道主+足联实力）→ 三向加权评分（市场20%+Onside 80%）→ Dixon-Coles 双变量泊松 → 蒙特卡洛冠军模拟（10k次）

**已用方法**：Poisson 回归、Dixon-Coles tau 修正、去水（remove_vig）、时间衰减 form 评分、soft calibration、MC 模拟

**核心局限**：
- 单一数据源（ESPN API），无实时赔率聚合
- Onside 4 信号只有 4 个静态特征，无动态 xG/射门/控球类特征
- λ 计算基于「raw_strength × 2.8」的启发式，而非从历史数据 MLE 拟合 attack/defense 参数
- Dixon-Coles ρ 使用网格搜索而非完整 MLE 联合优化（attack/defense 参数无独立拟合）
- ChatGPT 时代前的方法论——当前业界最前沿已把 xG 和机器学习（XGBoost）做进核心

---

## 2. FiveThirtyEight SPI（Soccer Power Index）

### 核心方法论
- **核心特征**：SPI = OFF + DEF 双评分体系。OFF 代表「对阵平均球队的期望进球」，DEF 代表「对阵平均球队的期望失球」
- **xG 基础**：SPI 使用 xG（预期进球）和 ns xG（非射门预期进球）作为底层信号，而非简单的 W/D/L 赛果
- **比赛重要性权重**：引入 `importance1/2` 字段（0-100），重要比赛权重更高
- **场次重要性校准**：adj_score（比赛状态调整后的进球数）——剔除垃圾时间/大比分领先后的数据污染
- **数据源**：SPI 历史数据集覆盖 40 个联赛（2016-2023），含 17 个字段
- **API 可用**：`https://projects.fivethirtyeight.com/soccer-api/club/spi_matches_latest.csv`

### 与 Onside 4 的差距
| 维度 | FiveThirtyEight SPI | Onside 4 |
|------|---------------------|----------|
| 底层信号 | xG + nsxG + adj_score（射门质量级） | W/D/L 赛果 + FIFA 排名（结果级） |
| 攻防分离 | OFF/DEF 双维度独立评分 | 单维度综合强度 |
| 重要性校准 | 比赛状态调整（adj_score） | 无 |
| 联赛覆盖 | 40 联赛/国际比赛 | 6 联赛 + 世界杯 |

### 独立评估结论
TransferScience 的回测（36,335 场比赛，2016-2023）显示：
- SPI 方向判断力强（知道谁更强），但置信度校准差
- 作为静态 pre-game 模型，SPI 在 10-90% 区间**系统性高估**真实概率
- Pinnacle 收盘赔率在概率校准曲线上几乎完美贴合 45° 线，SPI 有系统性偏差
- **结论**：SPI 适合赛季/tournament 级模拟，不适合逐场 beat 博彩市场

### 开源实现/数据
- 数据集：`github.com/fivethirtyeight/data/blob/master/soccer-spi/README.md`
- SPI 全球排名：`spi_global_rankings_intl.csv`（国际队）和 `spi_global_rankings.csv`（俱乐部队）

---

## 3. Opta 预测系统

### 核心方法论
- **双重特征**：博彩市场赔率 + Opta Power Rankings
- **Opta Power Rankings**：覆盖 13,500+ 俱乐部的全球排名系统，基于历史+近期表现
- **蒙特卡洛模拟**：用 match outcome probabilities 模拟剩余赛程数千次，统计联赛最终排名概率
- **实时数据**：Opta 是 FIFA 官方数据合作伙伴，提供实时 event stream（射门、传球、控球、压迫等）
- **Supercomputer**：Opta 超级计算机结合 Power Rankings + 模拟引擎做全赛季预测

### 与 Onside 4 的差距
| 维度 | Opta | Onside 4 |
|------|------|----------|
| 排名系统 | 13,500+ 俱乐部实时排名 | FIFA 排名（月更新，国家队级别） |
| 底层数据 | 实时 event stream + xG | 赛果 + 赔率（ESPN 单源） |
| 覆盖 | 3,900+ 赛事 | 有限赛事 |
| MC 模拟 | 全赛季/淘汰赛完整模拟 | 简化世界杯/联赛模拟 |
| 技术栈 | 商业不公开 | 纯 stdlib Python |

### 开源实现
- Opta 数据可通过 StatsPerform 商业获取
- Opta Power Rankings 历史曲线可视化：`fotcalc.com/opta-power-rankings-chart`

---

## 4. 博彩赔率隐含概率模型（Betfair/Pinnacle）

### 核心方法论
- **Pinnacle 黄金标准**：Pinnacle 收盘赔率（closing line）是学术界公认的「最准确的无偏概率估计」。TransferScience 验证其概率校准曲线几乎完美贴合 45° 线
- **Betfair Exchange**：去中心化交易所，赔率反映市场聚合智慧，不包含传统博彩公司的 margin
- **Sharpe Ratio 方法**：将模型概率 vs 博彩赔率 → 寻找正期望（positive EV）
- **去水（Vig Removal）**：三种主流方法——(a) 简单比例法 (`home/total`)，(b) Shin 模型（最准确，处理博彩公司偏误），(c) 对数法

### 核心特征
- **博彩赔率本质上是 xG 的替代**：高水平的博彩公司（如 Pinnacle）的内部模型已经聚合了 xG、伤病、天气等所有公开信息
- **ML + Spread + Total 三市场联动**：三个市场的一致性本身是一个预测信号——当 ML 与 spread 一致时信号最强
- **Betfair 数据更纯**：Betfair 的赔率几乎不含 vig（交易所模式），更接近真实概率

### 与 Onside 4 的差距
| 维度 | Betfair/Pinnacle | Onside 4 (ESPN) |
|------|------------------|-----------------|
| 赔率质量 | 世界上最准的收盘赔率 | DraftKings（ESPN API 内嵌），质量未知 |
| 去水方法 | Shin 模型（学术界最优） | 简单比例法（`home/total`） |
| 数据时效 | 实时更新至开球前最后秒 | 静态，ESPN API 更新频率低 |
| 市场类型 | 1X2 + AH + O/U + 角球 + 球员 | 仅 ML + spread + total |

### 开源实现
- `football-data.co.uk`：免费提供 Pinnacle 收盘赔率（多个联赛历史数据）
- `the-odds-api.com`：聚合 80+ 博彩公司实时赔率 API
- `penaltyblog`（Python）：内含去水工具、Shin 模型、赔率比较

---

## 5. Kaggle 足球预测比赛获奖方案

### 核心竞赛

#### 5.1 Football Match Probability Prediction（2023）
- **任务**：预测 150,000+ 场比赛的 H/D/A 概率
- **输入**：各队最近 10 场比赛序列
- **典型方案**：时间序列特征 + XGBoost/LightGBM
- **关键发现**：序列编码（LSTM/Transformer）优于手工特征

#### 5.2 Google Research Football with Manchester City F.C.
- **Kaggle 合作赛**：DeepMind × Man City
- **任务**：从比赛 replay 数据预测结果
- **获奖方案**：Dmitry & Tom 的方法——状态表示 + 强化学习
- **关键技巧**：从 embedding 到 match outcome 的映射用 XGBoost 效果好于 DL

#### 5.3 一般 Kaggle 足球模式
Kaggle 足球竞赛的常规工作流：
1. **特征工程**：滚窗特征（mean/goals/points last 5 games）、Elo 评分、主客场差异、休息天数
2. **模型**：XGBoost ≈ LightGBM > Random Forest > Logistic Regression > Poisson
3. **验证**：时间序列交叉验证（不能随机 shuffle——时间泄露）
4. **Blending**：Stack 多个模型（XGBoost + Poisson + Elo）比单一模型效果更好

### 与 Onside 4 的差距
| 维度 | Kaggle 获奖方案 | Onside 4 |
|------|----------------|----------|
| 模型类型 | XGBoost/LightGBM（梯度提升树） | 手工加权评分 + 泊松 |
| 特征量 | 50-200+ 个特征 | ~10 个特征 |
| 特征工程 | 滚窗统计、Elo、休息天数、转会数据 | 简单 form/record 评分 |
| 验证方案 | 时序交叉验证 | 无正式验证 |
| 可复制性 | 完全开源的 Kaggle Notebook | 专有项目 |

---

## 6. 学术界经典模型

### 6.1 泊松回归（Poisson Regression）

**Maher (1982)** — 独立泊松模型（BP）
```
P(H=h, A=a) = Poisson(h, λ_home) × Poisson(a, λ_away)
λ_home = exp(α_i + β_j + γ)  # i=主队, j=客队
λ_away = exp(α_j + β_i)
```
- α: 进攻强度，β: 防守强度，γ: 主场优势
- 用 MLE（GLM）拟合 attack/defense 参数
- **优势**：简洁、可解释、参数有意义（进攻/防守分离）
- **劣势**：假设独立性、不能处理过度离散、低估 0-0/1-1 平局

**当前项目的差距**：Onside 4 没有用历史数据 MLE 拟合 attack/defense 参数，而是用启发式 `raw_strength × 2.8` 计算 λ。学术界标准的做法是用过去赛季的比分数据通过 GLM 回归拟合每个队的 α_i 和 β_j。

### 6.2 Dixon-Coles（1997）扩展

**两个关键改进**：
1. **tau 修正**：`τ(x,y,λ,μ,ρ)` 修正 0-0, 1-0, 0-1, 1-1 的概率，ρ 通过 MLE 拟合
2. **时间衰减**：`φ(t) = exp(-ξ·t)`，ξ 通过滚动预测验证优化

**Dixon-Coles 学术公式**：
```
L(α,β,ρ,γ) = Π τ(λ_k,μ_k,x_k,y_k) × Poisson(x_k,λ_k) × Poisson(y_k,μ_k)
```
- 联合 MLE 同时优化 α_i, β_j, γ, ρ 四个参数集
- 拟合 scipy.optimize.minimize（梯度下降）

**当前项目的差距**：
- 当前实现：ρ 使用独立网格搜索（用总体均值做 λ 估算），而非联合 MLE
- 没有拟合 attack/defense 参数（α_i, β_j），只用了整体加权评分
- 没有时间衰减权重 ξ（当前只用 form 的线性衰减，非指数衰减）
- 正确的实现应该：`λ_home = exp(α_home + β_away + γ)`, `λ_away = exp(α_away + β_home)`

### 6.3 Karlis & Ntzoufras (2003) — Bivariate Poisson

**Bivariate Poisson 改进**：
```
BP(x,y|λ1,λ2,λ3) = exp(-(λ1+λ2+λ3)) × (λ1^x/x!) × (λ2^y/y!) × Σ(min(x,y)) ...
```
- 第三个参数 λ3 建模两队进球之间的**正相关**
- 比 Dixon-Coles 的 tau 修正更自然的数学框架
- 被引用 668 次，是足球预测统计模型的核心文献

**当前项目的差距**：Bivariate Poisson 公式在 D-C 的 tau 修正之上进一步改进了平局概率建模——但需要额外的 λ3 参数，拟合更复杂。

### 6.4 Negative Binomial（负二项）

**处理过度离散**：Poisson 假设均值=方差，但足球进球数据方差>均值（overdispersion）。负二项通过额外离散参数解决此问题。

**penaltyblog 示例**：
```python
clf = pb.models.NegativeBinomialGoalModel(goals_home, goals_away, team_home, team_away)
clf.fit()
```
- 输出：attack/defense 参数 + dispersion 参数 + home_adv
- **Log-Likelihood vs Poisson**: 更低（更好），AIC 更低

**当前项目的差距**：没有处理过度离散——Poisson 模型在进球方差的估计上可能不够准确（尤其对弱队），负二项是已知的更好的替代。

### 6.5 机器学习方法（XGBoost/Random Forest/Logistic）

**比较研究结果**：
- **XGBoost 在足球预测中通常最优**：多个独立研究证实 XGBoost > LightGBM > Random Forest
- **XGBoost 在低分差场景优势明显**：足球结果稀疏（多数比赛只有 0-3 球），XGBoost 的梯度提升对这类离散分布建模更好
- **特征有效性排序**（Kaggle 调查）：Elo 评分 > 近期滚窗均分 > 主客场差异 > 休息天数 > 伤病 > 转会
- **Logistic 回归在特定场景超越 XGBoost**：2026 年的一项独立实验显示，当特征数量少且信噪比低时，Logistic 回归的泛化能力好于 XGBoost

**研究论文关键发现**（2017-2026）：
- *Predicting Football Results using Archetype Analysis and XGBoost*：将球队风格分类（Archetype）作为 XGBoost 输入，准确率 55-60%
- *A Predictive Analytics Framework* (ScienceDirect 2024)：一种综合框架——特征提取（滚窗+Elo）→ XGBoost → Poission 比分校准 → 最终概率输出
- *Which ML Model Performs Best* (2025)：XGBoost 在 5 个欧洲联赛上全面超越 DL 和传统 ML

### 6.6 Log-Linear 回归的「Bivariate 变体」混合方法

学术界的综合方案往往结合多个模型：
1. 用 XGBoost 预测**比赛方向**（胜/平/负）
2. 用 Poisson/D-C/Bivariate Poisson 预测**比分分布**
3. 用 Elo 评分作为补充特征
4. 最终概率通过 **Bayesian Model Averaging** 或简单平均合成

---

## 7. xG（预期进球）模型

### 核心概念
xG 是「一次射门转化为进球的概率」，基于历史的数千次类似射门训练得出。关键特征：
- 射门位置（坐标 x, y）— 最重要的特征
- 射门身体部位（脚/头/其他）
- 射门方式（open play/set piece/penalty/free kick）
- 助攻类型（cross/through ball/rebound）
- 防守压力（距离最近防守球员）
- 比赛状态（是否落后追分）

### 开源实现

#### 7.1 soccer_xg（ML-KULeuven）
```
pip install soccer-xg
```
- GitHub: `github.com/ML-KULeuven/soccer_xg`
- 支持 Opta/Wyscout/StatsBomb 数据格式
- 预训练模型：`openplay_xgboost_advanced`, `openplay_logreg_basic`
- 可自定义 pipeline（feature config + model selection）

#### 7.2 StatsBomb Open Data
- GitHub: `github.com/statsbomb/open-data`
- 免费提供世界杯、女足世界杯、顶级联赛的事件数据
- 含 StatsBomb 自己的 xG 模型输出
- 学术引用 > 100 篇论文

#### 7.3 FBref xG
- FBref（Sports Reference）免费提供历史 xG 数据
- 覆盖英超、西甲、德甲、意甲、法甲、MLS
- 可直接用于预测模型的输入特征

### 与 Onside 4 的差距
| 维度 | xG 模型 | Onside 4 |
|------|---------|----------|
| 数据粒度 | 射门/事件级（每秒更新） | 比赛结果级（赛后） |
| 特征 | 坐标、角度、方式、防守压力等 10+ 维 | 无射门级特征 |
| 模型 | XGBoost/Logistic Regression 训练 | 手工加权 |
| 数据源 | 需要 event stream（商业数据） | ESPN 免费 API |
| 准确率 | xG 预测团队进球 vs 实际进球 R² ~0.3-0.4 | 无对标 |

---

## 8. 开源实现索引（可直接参考）

| 项目 | 语言 | 覆盖模型 | GitHub/链接 |
|------|------|----------|-------------|
| **penaltyblog** | Python | Poisson、Bivariate Poisson、Dixon-Coles、Negative Binomial、Zero-Inflated Poisson、Weibull Copula | `github.com/martineastwood/penaltyblog` |
| **goalmodel** | R | Poisson、Dixon-Coles、负二项、Weibull | `github.com/opisthokonta/goalmodel` |
| **regista** | R | Dixon-Coles（完整 MLE 实现） | `github.com/Torvaney/regista` |
| **soccer_xg** | Python | xG (XGBoost, Logistic) | `github.com/ML-KULeuven/soccer_xg` |
| **StatsBomb Open Data** | - | 免费事件数据 + xG | `github.com/statsbomb/open-data` |
| **dashee87/blogScripts** | Python | Poisson、Dixon-Coles（教学级实现） | `github.com/dashee87/blogScripts` |
| **FiveThirtyEight SPI** | CSV | SPI 历史数据集 2016-2023 | `github.com/fivethirtyeight/data/soccer-spi` |
| **football-data.co.uk** | CSV | 免费赔率数据（含 Pinnacle） | `football-data.co.uk` |

---

## 9. 差距分析总结

### 当前项目（Onside 4）离业界前沿的差距

| 层次 | 当前项目 | 业界前沿 | 差距量级 |
|------|---------|---------|----------|
| **数据源** | ESPN 单源（DraftKings 赔率） | 多源聚合（Pinnacle+Betfair+Opta） | 中等 |
| **赔率去水** | 简单比例法（`home/total`） | Shin 模型 / 对数法 | 低 |
| **队伍强度** | 综合加权评分（10 个特征聚合） | attack/defense 分离 MLE 拟合 | **高** |
| **λ 计算** | `raw_strength × 2.8`（启发式） | `exp(α_i + β_j + γ)`（MLE 回归） | **高** |
| **D-C ρ 拟合** | 独立网格搜索（λ 用均值估算） | 联合 MLE（α,β,γ,ρ 同时优化） | **高** |
| **时间衰减** | form 字符串线性衰减（5 场） | 指数衰减 `exp(-ξ·t)`，ξ 验证优化 | 中 |
| **特征维度** | ~10 个手工特征 | 50-200（滚窗+Elo+xG+其他） | **高** |
| **模型类型** | 手工加权评分 | XGBoost / Gradient Boosting | **高** |
| **xG 信号** | 无 | 核心驱动力 | **高** |
| **过度离散** | 不考虑 | 负二项处理 | 中 |
| **MC 模拟** | 简化（分组固定，剔除赛平局 50% 随机） | 完整 Bracket + 加时/点球模型 | 中 |
| **验证** | 无 | 时序交叉验证 / 回测框架 | **高** |
| **实时性** | 静态（ESPN 更新后） | 收盘赔率实时更新至开球 | 中 |

### 可低成本借鉴的技术点（排序从易到难）

1. **时间衰减**：将 form 的线性衰减改为指数衰减 `exp(-ξ·t)`，在 football-data.co.uk 历史数据上验证 ξ 最优值
2. **去水方法**：从比例法改为 Shin 模型（penaltyblog 有现成实现，约 30 行 Python）
3. **赔率多源**：接入 `football-data.co.uk` 的 Pinnacle 赔率，替代 ESPN API 的 DraftKings 数据
4. **ρ 联合 MLE**：将 ρ 拟合改为完整 `scipy.optimize.minimize`（需引入 scipy 依赖）
5. **Elo 评分**：实现一个 Elo 系统作为第 5 个 Onside 信号（可完全 stdlib，~50 行）
6. **负二项模型**：在泊松基础上增加离散参数（需引入 scipy）
7. **attack/defense MLE 拟合**：用历史比分数据独立拟合 α_i, β_j 参数
8. **XGBoost 模型**：引入 xgboost 包，用特征工程训练方向预测模型
9. **xG 信号**：接入 FBref 或 StatsBomb 免费 xG 数据作为额外信号
10. **完整验证框架**：实现时序交叉验证，衡量 Brier Score / Log Loss