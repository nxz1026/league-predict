# M4 报告 · 单文件 SPA 前端

## 交付物
| 文件 | 内容 | 证据 |
|---|---|---|
| `static/index.html` | 单文件 SPA（22,335B <120KB） | `wc -c static/index.html` → 22335 |
| `web/api.py` | 最小接线 1 行：已登录 `/` 302 → `/static/index.html`（原指向 `/login`） | `git diff web/api.py` 仅 +2/-2 |

## 验收点自测（A~E）

### A. 文件存在且 <120KB
`wc -c static/index.html` → **22335 bytes** ✓

### B. 无新增外链、无构建物
`grep -oE 'https?://…' static/index.html` → 仅 1 条：
`https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js` ✓
无 package.json/vite/react；无内联 base64 大图。

### C. tab 数=5 且每个 tab 有 fetch 调用对应端点
`grep -c data-tab=` → **5**（today/history/champ/accuracy/ops）✓
fetch 端点覆盖（`api()` 调用 14 处）：
- today → `/predictions/today` + `/ai/status` + `/ai/details`（AI 折叠区）
- history → `/predictions/{date}`
- champ → `/championship`
- accuracy → `/accuracy`
- ops → `/sources/status` + `/jobs` + `/jobs/predict` + `/jobs/{id}`（轮询）

### D. 未登录打开 → 跳 /login（双保险实测）
本地起服 `uvicorn web.api:app --port 8765` 后 curl 取证：
```
未登录 GET /                   → 302 → http://127.0.0.1:8765/login
未登录 GET /api/v1/predictions/today → {"code":"unauthorized","message":"未登录或会话已过期"} 401
登录 POST /api/v1/login         → 200 {"message":"ok"}
已登录 GET /                    → 302 → http://127.0.0.1:8765/static/index.html
```
前端 fetch 层另设 `res.status===401 → location.href='/login'` 兜底（双保险）✓

### E. 浏览器实机走查（部分完成）
**浏览器守护不可用**（`omp.browser.headless failed exit=127`，机器无 Chromium 二进制），
改以三层替代验证：
1. **JS 语法**：提取内联 script（15,892B）用 esprima 解析，除 ES2020 `??`（3 处，解析器仅支持 ES2017）外全部通过；`??`→`||` 替换后 esprima 全绿。括号配对独立校验 OK。
2. **端点真实数据**：已登录遍历 `/ai/status`→`{"available":true,"matches":102,…}`、`/ai/details`→102 条富化（含 "Frosinone Calcio vs 尤文图斯" 65 分）、`/sources/status`→football-data 已配置/api-football 未配置、`/jobs`→任务列表；`/predictions/today` 当日空窗口 → 前端显示"该联赛今日无预测数据"占位。
3. **渲染路径**：占位态（空数据/失败重试钮/降级提示）在骨架中硬编码检查 28 处相关 class；ECharts 图表在数据为空时不渲染（`if(!keys.length){ placeholder(...); return; }`）。

**未尽事项（队长走查点）**：实机浏览器视觉确认（本环境无可用浏览器）；冠军概率/准确率图表需真实 monte_carlo/accuracy_summary 数据产出后查看图形（当前产物为空 dict，前端已正确显示"等待首次预测"）。

## 其他自查
- `python3 -m pytest tests/web -q` → **56 passed**（零回归）
- `git status` web 区仅 `web/api.py` 修改；scripts/core/tests/static/login.html 零 diff
- JS 中 `??` 为 ES2020 空值合并（3 处 λ 字段回退），现代浏览器原生支持

## 前端功能清单
- 顶栏：用户名（GET /me）+ 退出（POST /logout → /login）
- 今日赛程：BJT 比赛日标注 + 联赛分组卡片（方向/信心星/比分TOP/大小BTTS/λ）；AI 折叠区（available:false 显示降级原因，成功展示富化文本）
- 历史预测：日期控件默认 BJT 今日（`toLocaleString timeZone=Asia/Shanghai`），按联赛过滤
- 冠军概率：ECharts 堆叠条（Top8 队 × 联赛）+ 明细表（sims/窗口）
- 准确率：ECharts 折线（各联赛命中率指标交集轴）+ 明细表
- 任务与数据源：POST jobs/predict（429 配额/409 并发提示）、jobs/{id} 3s 轮询状态徽标、当日配额用量条、数据源 enabled 徽标、最近任务表