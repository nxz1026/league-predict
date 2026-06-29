# ESPN API match 字段格式说明

## 问题

ESPN API 的 `event.name` 字段格式为 **"Away at Home"**（客队在前，主队在后），如：
- `"卡塔尔 vs 波黑"` → away=卡塔尔, home=波黑

但 `predicted_score` 字段格式为 **"home-away"**（主队进球-客队进球），如：
- `"0-1"` → home 进 0 球, away 进 1 球 → 客队胜

## 矛盾示例

如果 LLM 把 `match` 字段直接当 "主队 vs 客队" 展示：
- 展示：`卡塔尔 vs 波黑 | 卡塔尔 胜 | 0-1`
- 读者理解：主队卡塔尔 0 - 客队波黑 1 → 客队胜
- 但方向写的是 "卡塔尔胜"（主队胜）→ 矛盾！

## 修复

`predict_wc.py` 输出 JSON 已新增三个 display 字段（2026-06-24）：
- `match_display`: "主队 vs 客队"（基于 home/away 字段正确排序）
- `score_display`: 与 match_display 一致的主队-客队比分
- `direction_display`: 方向推荐（队名与 match_display 一致）

**LLM 格式化时必须用 display 字段，不要用原始 match 字段。**

## 相关

- predict_wc.py 脚本路径：`/root/.hermes/scripts/predict_wc.py`
- cron job ID：`84d210ffeedc`
