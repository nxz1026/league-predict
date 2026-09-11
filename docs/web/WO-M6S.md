# WO-M6S：AI 摘要按名对齐（修 analyses 位置错配）

## 缺陷（线上实证 2026-09-11）
`ai/batch_pipeline.py::analyse_batch` 用位置配对 LLM 返回的 analyses；
模型顺序漂移即整批摘要与对阵错位（云端已复现：水晶宫条目配了伯恩茅斯摘要）。

## 修法（只许动 ai/batch_pipeline.py + 测试文件）
1. `_build_prompt` 的 `# Instructions` 里 Return 模板改为每条 analysis 必须带 `"match"` 字段：
   `Return: {"analyses": [{"match": "<对应条目的 name 原样照抄>", "score": <0-100>, "summary": "<2 sentences>", "notes": ""}]}`
   并加一行：`analyses 必须覆盖全部条目，match 原样照抄，不得改写。`
2. `analyse_batch` 配对逻辑改为**按名 join**：
   - 把返回 analyses 建成 `{a["match"]: a}` 字典；
   - 每个 item 用 `item.get("name")` 查字典；查到→填 ai_* 字段，查不到→原样 append（不瞎配）；
   - **兼容回退**：若所有 analysis 都没有 match 键且 len(analyses)==len(batch)，退回现有位置配对。
   - 每个函数保持 <50 行（超了就拆 `_pair_by_name` 小函数）。
3. `tests/web/test_m6_ai_enrich.py` 追加 1 用例：mock analyse_batch 的 LLM 层
   （monkeypatch generate/内部调用，参考现有 mock 风格）返回**乱序带 match 键**的 analyses
   → 断言按名配对正确；再返回**缺一条**→ 断言缺失项无 ai_ 字段而不串位。
   （若 mock 内部太深，可直接单测配对辅助函数 `_pair_by_name`。）
4. 报告：docs/web/M6_report.md 追加 M6S 节（根因一行、diff 摘要、pytest 尾行）。

## 完成定义
pytest tests/web 全绿 → echo M6S-DONE > docs/web/logs/M6S.done
禁：git commit/push；碰清单外文件；改中文指令行。
