# Owen891.cc.cd Provider Quirks

Owen891 (→ Api891.cc.cd) 是一个 OpenAI 兼容 API 代理，路由多种模型。
注：config.yaml 中 `custom_providers[].name` 在 2026-06-15 从 `Owen891.cc.cd` 改为 `Api891.cc.cd`。文件名保留历史名，实际引用用 `Api891.cc.cd`。

## 已知行为

### 1. 模型名映射
发送 `model: claude-opus-4-5`，API 响应里的 `model` 字段返回 `gpt-5.5`（不是 `claude-opus-4-5`）。
这是端侧模型路由策略——**不影响实际推理质量**，API 响应体里的 model 名不可信。

### 2. Provider 名
在 Hermes config 中定义为 `custom:Owen891.cc.cd`。
key 在 config.yaml 的 `custom_providers[].api_key` 中（非 .env 文件）。

### 3. 限流行为
Owen891 有 per-user 429 限流。长时间未用后第一次请求通常成功，连续请求可能触发。
应对：cron 单次单请求，不用该 provider 做连续多轮对话。

### 4. 曾验证通过
- 2026-06-15: `claude-opus-4-5` → `gpt-5.5`，7.5s 延迟，20 tokens 响应 ✅
