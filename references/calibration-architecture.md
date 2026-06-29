# Calibration Architecture

## 关键决策：build_calibration() 不反馈脚本

`predict_wc.py` 的 `build_calibration()` 只输出统计数字到 JSON，**从不修改预测参数**。这是有意的设计。

### 为什么

1. **样本量不足**：66 场/48 队杯赛，Wilson 95% CI 宽度 ±11pp，不足以精确调参
2. **CI 大区间重叠**：主胜[37-60%] vs 平局[20-41%] vs 客胜[15-35%]，不能可靠地确定"真值"
3. **信号已被隐式包含**：spread 25% + form 20% 的权重已经吸收了 tournament-level 的方向性信息
4. **过拟合风险**：tournament 前半程的特化信号可能不适用于后半程

### calibration 数据的真正用途

| 用途 | 实现 | 消费者 |
|------|------|--------|
| 人类复盘参考 | 写入 JSON → tournament-trends.md | 分析师回看 |
| LLM soft calibration | cron prompt 读取 trends.md | LLM 在格式化文本时提醒读者 |
| Auditor 审计依据 | Auditor 卡读 calibration 字段 | P1 驳回时举证 |

## Soft Calibration 规则（LLM cron prompt 使用）

LLM 在格式化输出时必须检查 tournament-trends.md，应用以下软判断：

```
|  tournament 信号         | 本场 ML 信号           | LLM 行为 |
|-------------------------|------------------------|----------|
| draw_rate > 25%         | ML draw_prob < 30%     | 添加 ⚠️ 备注 tournament 平局率偏高 |
| home_rate(48%)>>away     | spread 无强烈信号+主场  | 添加倾向主场备注 |
| 联合会差异               | 对阵所属联赛            | CAF对CAF→小比分；UEFA维持 |
| odds_accuracy=0          | ML vs spread 矛盾      | 优先信 spread |
```

## 信号可用性评估（截至 6/27）

| 信号 | 可用？ | 原因 |
|------|--------|------|
| draw_rate > 历史平均 | ✅ | 29% vs 25%，确认强队难赢盘 |
| home_rate >> away_rate | ✅ | 48% vs 23%，差距显著 |
| odds_accuracy | ❌ | ESPN API 无 ML open 字段 |
| 联合会差异 | ❌ | 描述性统计，样本不足做条件预测 |
| 挪威 ML movement | ❌ | 单队信号不可泛化 |

## 踩坑

- **build_calibration 输出无关预测**：曾在 6/28 让用户误以为回填 66 场校准了算法，实际代码中 build_calibration() 与 calculate_prediction() 是完全独立的两个函数
- **send_cron_card.sh shell 脚本损坏**：line 25 语法错误（python3 -c 在 $() 嵌套引号冲突），应使用 send_cron_card.py 替代
