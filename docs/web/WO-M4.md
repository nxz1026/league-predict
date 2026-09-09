# WO-M4 · 单文件 SPA 前端

前提：M1–M3 端点齐活。**字段以 web/routers 实际响应为准**（读码，不臆造）。样式自拟（深色/浅色皆可，别用构建工具）。

## 交付物
`static/index.html` 单文件（vanilla + ECharts 5.4.3 CDN 唯一外链，参照 welfare 行为不复制代码）：
- 五 tab：**今日赛程 / 历史预测 / 冠军概率 / 准确率 / 任务与数据源**（PLAN §4 口径）
- 统一 fetch 层：`credentials:'same-origin'`，401→`location='/login'`；每请求错误态占位（空数据文案/失败重试钮）
- 日期控件默认 BJT 今日；联赛分组卡片；championship/accuracy 用 ECharts（堆叠条/折线），无数据不渲染图表
- 任务 tab：POST jobs/predict 按钮（429/配额提示）、jobs/{id} 轮询状态徽标、sources 配额用量条
- AI 折叠区：available:false 显示降级原因；成功则展示富化文本
- 顶栏用户名 + 退出登录（POST logout → /login）

## 红线
1. 只许动 static/index.html（web/api.py 仅允许静态挂载顺序/版本注入的最小改动）。
2. 无 package.json/构建器/框架；除 ECharts 外零外链；禁内联 base64 大图（体积 <120KB）。
3. 全部真实数据来自 /api/v1；代码里不得写死比赛/球队数据（fixture 仅允许在注释示例）。
4. 禁 git。

## 验收点
A 文件存在且 <120KB；B grep 无新增外链、无构建物；C tab 数=5 且每个 tab 有 fetch 调用对应端点；D 未登录打开→跳 /login（行为由后端 302/前端 401 双保险）；E 队长晨间实机走查（登录→五 tab 真实渲染→触发一次任务）。

## 完成信号
`docs/web/M4_report.md`（自测证据）+ 哨兵 `docs/web/logs/M4.done`=`M4-DONE`+UTC。
