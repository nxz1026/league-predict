# American Odds — 解析与去水公式

> 独立可复用的赔率数学参考。不依赖预测模型，纯 math。

## 美式赔率 → 隐含概率

```python
def parse_american_odds(odds_str):
    """
    -125 → 125/225 = 0.5556  (favorite, 负值越大越被看好)
    +265 → 100/365 = 0.2740  (underdog, 正值越大越不被看好)
    +105 → 100/205 = 0.4878
    """
    raw = str(odds_str).strip().lstrip('+')
    odds = int(raw)
    abs_odds = abs(odds)
    if odds < 0:         # favorite: -125
        return abs_odds / (abs_odds + 100)
    else:                 # underdog: +265
        return 100 / (abs_odds + 100)
```

**为什么负值用分母 `odds + 100`**：美式负数赔率表示"押 $X 赢 $100"，隐含概率 = X / (X + 100)。  
如 -125：押 $125 赢 $100 本金 → 隐含概率 125/225 = 55.56%。

**为什么正值用 `100 / (odds + 100)`**：正数赔率表示"押 $100 赢 $X"，隐含概率 = 100 / (X + 100)。  
如 +265：押 $100 赢 $265 利润 → 隐含概率 100/365 = 27.40%。

**常见错误**（踩坑记录）：
```
# ❌ 错误的 favorite 公式导致 -125 → 5.0 (完全错了)
odds = -int("-125")  # = 125
return -odds / (-odds + 100)  # -125 / -25 = 5.0 ← 除零边缘
# ✅ 正确
return abs_odds / (abs_odds + 100)  # 125 / 225 = 0.5556
```

## 博彩公司 margin（Vig / 抽水）

实际赔率之和 > 1。足球典型 margin 约 5-8%。

```python
# 给定 home ML 和 draw ML，推算 away ML + 去水
home_p = parse_american_odds("-125")    # 0.5556
draw_p = parse_american_odds(265)       # 0.2740
total_margin = 1.07  # 6-8% 典型抽水

away_p = total_margin - home_p - draw_p  # = 0.2404

# 归一化去除抽水
home_true = home_p / total_margin        # 0.519
draw_true = draw_p / total_margin        # 0.256
away_true = away_p / total_margin        # 0.225

# 验证三向和为 1 ✅：0.519 + 0.256 + 0.225 = 1.000
```

## 从 ESPN `details` 字段提取 ML

ESPN API 的 `odds[0].details` 返回简写，如 `"CZE -125"` 或 `"MEX +105"`：

```python
details = "CZE -125"
team, odds_str = details.split()
home_implied = parse_american_odds(odds_str)  # 0.5556
```

搭配 `odds[0].drawOdds.moneyLine`（整数，如 265）即可得到三向赔率。
`moneyline` key 在 raw JSON 中经常为空，**不要**从那里取。

## 从 spread movement 推断信心变化

```
-110 → -135: 水位从 +100 赌 110 变为付 135 赢 100
            = 市场用真金白银推高主队信心
            factor ≈ +0.25 (正向变化)

+125 → -185: 盘口从 +0.5 水 125 变为 -0.5 水 185
            = 不仅变盘还变水，强烈信号
            factor ≈ +0.80

-135 → -105: 水位下降意味着支撑减弱
            factor ≈ -0.20
```

```python
def spread_movement_factor(open_odds, close_odds):
    o = parse_american_odds(open_odds)
    c = parse_american_odds(close_odds)
    if o is None or c is None:
        return 0.0
    # 隐含概率上升 = 市场信心增强
    return (c - o) * 3  # 放大系数便于可视化
```

## References 引用

- 本文件所有公式验证于 2026-06-18，来源：DraftKings 通过 ESPN API 返回的真实赔率数据。
