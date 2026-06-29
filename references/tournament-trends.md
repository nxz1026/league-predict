# 2026 世界杯 Tournament Trends（实时更新）

> 每次预测运行后更新此文件。记录 observable 的比赛模式、热门队表现趋势、联合会表现差异等，供下次 step 0 校准直接引用。

## Group Stage — Matchday 1（06/11–06/18）

### 核心模式：热门队普遍不胜（"Big Team Draw"模式）

截至 2026-06-16，已完成 16 场小组赛。最显著的模式：

| 热门队 | 对手 | 赛果 | 场次 |
|--------|------|------|------|
| Mexico | South Africa | ? | 1 |
| South Korea | Czechia | ? | 1 |
| Canada | Bosnia | ? | 1 |
| USA | Paraguay | ? | 1 |
| Brazil | Morocco | 1-1 **DRAW** | 1 |
| Spain | Cape Verde | 0-0 **DRAW** | 1 |
| Belgium | Egypt | 1-1 **DRAW** | 1 |
| Netherlands | Japan | 2-2 **DRAW** | 1 |
| Uruguay | Saudi Arabia | 1-1 **DRAW** | 1 |
| Iran | New Zealand | 2-2 **DRAW** | 1 |

**连续 6 场热门队平局**（Spain 0-0 → Belgium 1-1 → Saudi 1-1 → Netherlands 2-2 → Brazil 1-1 → Iran 2-2）。
这是世界杯小组赛极为罕见的现象——不存在单场爆冷，而是系统性的"强队无法赢盘"。

**可能的根因**：
- 48 队扩军后强弱差距被小组赛制度抹平（弱队死守拿 1 分有价值）
- 强队首轮状态慢热（世界杯常见，但这次尤其突出）
- 夏季天气/旅行疲劳（跨北美 3 国）

### 对预测的启示

1. **任何热门队的 ML 赔率即使被市场看好，也必须考虑"这个锦标赛的 draw 惯性"**。在本届世界杯，平局不应该被视为冷门。
2. **⭐⭐⭐⭐ 信心的定义需要收紧**：即使盘口+基本面+临场都支持，锦标赛自身趋势也构成反向信号。
3. **挪威 -245→-475** 是唯一出现巨量正向 movement 的热门队——市场用真金白银投票的方向可能打破 draw 模式。
4. **法国/阿根廷/奥地利 ML 全部走弱**（初盘→当前赔率上升），即使基本面看似碾压，也应降信心。

### 比分模式

| 特征 | 数据 |
|------|------|
| 0-0 场次 | Spain vs Cape Verde |
| 1-1 场次 | Brazil-Morocco, Belgium-Egypt, Saudi-Uruguay |
| 2-2 场次 | Netherlands-Japan, Iran-New Zealand |
| 大胜场次 | Sweden 5-1 Tunisia, Germany 7-1 Curaçao, Australia 2-0 Turkey |
| **规律** | 实力差距巨大的比赛正常出大比分；实力差距中等的比赛全平 |

### 联合会表现

| 联合会 | 表现 |
|--------|------|
| UEFA (欧洲) | 强队不稳但碾压局正常出（Germany 7-1, Sweden 5-1） |
| CAF (非洲) | 防守型闷平（Egypt 1-1, Morocco 1-1, Tunisia 1-5） |
| AFC (亚洲) | 有竞争力（Iran 2-2, Japan 2-2, Saudi 1-1, Australia 2-0） |
| CONMEBOL (南美) | 未见统治力（Brazil 1-1, Uruguay 1-1） |
| CONCACAF (北美/加勒比) | Curaçao 1-7, 其他待赛 |

## 更新记录

| 日期 | 新增内容 |
|------|----------|
| 2026-06-16 | 初始记录。Hot-favorite draw 模式（6 连平）。联赛制扩军影响初步判断。 |
| 2026-06-18 | Matchday 1+2 滚动结果。新增 Colombia 3-1 Uzbekistan 客胜。近 24h 5 场: 3 主胜 1 平 1 客胜 (60% / 20% / 20%)。England 4-2 Croatia 大球出，Portugal 1-1 DR Congo 热门平局延续。待预测 4 场：捷克 vs 南非 16:00、瑞士 vs 波黑 19:00、加拿大 vs 卡塔尔 22:00、墨西哥 vs 韩国 01:00。 |
| 2026-06-21 | Matchday 2 滚动。4 场已结束: 瑞典vs荷兰 5-1（荷兰主胜大球），科特迪瓦vs德国 2-1（德国主胜），库拉索vs厄瓜多尔 0-0（平局），日本vs突尼斯 0-4（突尼斯客胜大胜）。本轮主胜50% 平25% 客胜25%。大球（4球+）出现2/4场。待预测 5 场：沙特vs西班牙、伊朗vs比利时、佛得角vs乌拉圭、埃及vs新西兰、奥地利vs阿根廷。 |
| 2026-06-27 | **全量校准**。66 场已结束比赛（6/11-6/26）完整统计：主胜 48% (32/66)、平 29% (19/66)、客胜 23% (15/66)。平局比例显著高于历史平均（通常 ~25%），确认本届世界杯「强队难赢盘」模式持续。无 ML 数据（过去比赛无赔率），odds_accuracy=0。 |
