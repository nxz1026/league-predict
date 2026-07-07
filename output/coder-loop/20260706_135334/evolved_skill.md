---
name: coder-loop
description: >
  把编码任务自动丢给 coder 并进入 kanban 审核循环。
  触发词："丢给coder去干"、"coder 来做"、"交给码师"、"丢给码师"。
  流程：创建 kanban 任务 → coder profile 用 Reasonix 实现 → 自动转 auditor 审核 →
  打回则回到 coder，直到通过。进出 Reasonix 时自动走 Headroom 压缩。
---

## 触发

用户消息包含以下任一触发词时，自动进入本 skill：

- 丢给coder去干
- coder 来做
- 交给码师
- 丢给码师
- coder 实现
- 交给 coder

## Headroom 压缩

coder-loop 的所有进出点默认走 Headroom 压缩，减少 token。

压缩脚本：`/root/.hermes/scripts/headroom_compress.py`

用法：
```bash
echo '{"content":"...","role":"tool"}' | python3 /root/.hermes/scripts/headroom_compress.py
```

输出 JSON：
```json
{
  "compressed": "...",
  "tokens_before": N,
  "tokens_after": N,
  "transforms": [...]
}
```

压缩时机：
- 发送给 coder 的任务描述：压缩后写入 kanban comment
- coder 返回的实现结果/transcript：压缩后再写入 kanban comment
- 所有 kanban comment 写入前统一压缩
- auditor 输入：coder 产物压缩后送审，保留哈希标记，需要细节时 retrieve
- auditor 输入必须保留 headroom 哈希标记，支持按需 retrieve 原文

## 流程

### Step 0：Orchestrator 就位

推荐由 `orchestrator` profile 驱动本 skill，而不是 default profile。
Orchestrator 职责：拆需求、建 task、盯 coder/auditor 状态、做路由、控循环、ESCALATE。
禁止 orchestrator 自己写代码或审 diff。

### Step 1：创建任务

推荐由 `orchestrator` profile 驱动本 skill，而不是 default profile。
Orchestrator 职责：拆需求、建 task、盯 coder/auditor 状态、做路由、控循环、ESCALATE。
禁止 orchestrator 自己写代码或审 diff。

### Step 1：创建任务

```bash
hermes kanban create "<goal>" \
  --assignee coder \
  --json
```

提取 `task_id`。

### Step 2：通知 coder

压缩需求后写入 comment，要求 coder：
- comment `done`
- 调用 `kanban_block`
- assign 给 auditor

### Step 3：等待 coder 完成

定期 `hermes kanban show <task_id>`。

当检测到 coder comment 包含 `done` / `完成` / `finished` 时：
1. 提取 coder 输出
2. Headroom 压缩后存档
3. 执行 `hermes kanban block <task_id> "awaiting auditor review"`
4. `hermes kanban assign <task_id> auditor`
5. 写入 auditor 审核指令

**注意**：`kanban block` 没有 `--reason` 参数，正确用法是 `hermes kanban block <task_id> <reason>`。

### Step 4：处理审核结果

Auditor comment 关键词判断结果：
- **通过**：`通过` / `pass` / `approved`
- **打回**：`打回` / `reject` / `需修改`

分支：
- 通过 → Step 5
- 打回 → Step 6

### Step 5：完成

auditor 已调用 `kanban_complete`，向用户报告结果。

### Step 6：打回循环

```bash
hermes kanban unblock <task_id>
hermes kanban assign <task_id> coder
hermes kanban comment <task_id> "打回重改。 auditor 意见：<结论>。修改后 comment 'done'，调用 kanban_block，然后 assign 给 auditor。"
```

回到 Step 3，继续等待 coder 完成。

循环上限：最多 3 轮。超过 3 轮仍未通过，Orchestrator 必须 ESCALATE，不自动重试。

### Step 7：Auditor 未自动触发时的降级路径

如果 `kanban assign <task_id> auditor` 后 auditor worker 没有被 spawn，
任务停留在 `blocked` 或 `running` 状态超过预期时间，Orchestrator 应：

1. 检查 auditor profile 的 `platform_toolsets.cli` 是否包含 `kanban`
2. 检查 task 是否已被 coder 误调 `kanban_complete` 进入 `done` 状态
3. 若 task 已 `done` 且 auditor 未执行：转为 **manual audit override**
   - 读取 coder 产出文件/comment
   - 直接给出 auditor 结论
   - 不依赖 kanban 状态回退
4. 若 task 未 `done` 但 auditor 不接：运行 `hermes kanban dispatch` 或 `hermes kanban unblock` + `assign` 重试一次
5. 仍失败：ESCALATE 到用户，附上 task_id 和诊断信息

### Step 7：Auditor 未自动触发时的降级路径

如果 `kanban assign <task_id> auditor` 后 auditor worker 没有被 spawn，
任务停留在 `blocked` 或 `running` 状态超过预期时间，Orchestrator 应：

1. 检查 auditor profile 的 `platform_toolsets.cli` 是否包含 `kanban`
2. 检查 task 是否已被 coder 误调 `kanban_complete` 进入 `done` 状态
3. 若 task 已 `done` 且 auditor 未执行：转为 **manual audit override**
   - 读取 coder 产出文件/comment
   - 直接给出 auditor 结论
   - 不依赖 kanban 状态回退
4. 若 task 未 `done` 但 auditor 不接：运行 `hermes kanban dispatch` 或 `hermes kanban unblock` + `assign` 重试一次
5. 仍失败：ESCALATE 到用户，附上 task_id 和诊断信息

## 输出格式

每轮完成后，向用户汇报：
```
[kanban <task_id>] <状态>
- coder: <摘要>
- auditor: <结论>
- 轮次: <N>/5
- headroom: 压缩前 <X> tokens → 压缩后 <Y> tokens
```

## 工具调用规则

- 所有 `hermes kanban ...` 命令通过 `terminal` 工具执行
- coder / auditor 都是独立 profile，命令自动走对应环境
- 不直接调用 Reasonix，Reasonix 由 coder profile 自行决定何时用
- 本 skill 只管 kanban 路由和循环，不管代码内容
- Headroom 压缩脚本路径固定为 `/root/.hermes/scripts/headroom_compress.py`
- 所有 kanban comment 写入前必须走 Headroom 压缩，无一例外
- auditor 输入必须保留 headroom 哈希标记，支持按需 retrieve 原文

## 流程

### Step 0：Orchestrator 就位

推荐由 `orchestrator` profile 驱动本 skill，而不是 default profile。
Orchestrator 职责：拆需求、建 task、盯 coder/auditor 状态、做路由、控循环、ESCALATE。
禁止 orchestrator 自己写代码或审 diff。

### Step 1：创建任务
- **auditor 是唯一可以调用 `kanban_complete`** 的角色
- **auditor 打回时**：`kanban_unblock` + assign 回 coder，不要 complete
- 任务流转：`ready` → coder working → `blocked` → auditor working → `done`
- **如果 coder 已经调用了 `kanban_complete`**：任务已进入 `done`，无法 reopen。此时由 orchestrator 直接进入 manual audit：读取 coder 产出，人工或另建审核任务完成 sign-off，不依赖 kanban 状态回退。

## 前置条件

1. **skill 路径**：`coder-loop` 必须复制到每个 profile 的 `skills/` 目录
   ```bash
   cp -r ~/.hermes/skills/coder-loop ~/.hermes/profiles/coder/skills/coder-loop
   cp -r ~/.hermes/skills/coder-loop ~/.hermes/profiles/auditor/skills/coder-loop
   cp -r ~/.hermes/skills/coder-loop ~/.hermes/profiles/orchestrator/skills/coder-loop
   ```
2. **platform_toolsets**：coder、auditor、orchestrator 的 `config.yaml` 都必须在 `platform_toolsets.cli` 里包含 `kanban`
3. **model 配置**：每个 profile 的 `config.yaml` 顶部必须可解析；自定义 provider 用 `provider: custom` + `base_url`，不要写不存在的 provider 名。示例见 `references/provider-config-template.yaml`
4. **gateway 生效**：修改 profile 配置后，用户必须重启 gateway，agent 不能代为 restart
5. **fixture 依赖**：`--no-fetch` 测试依赖本地 `/tmp/espn_wc.json`，测试时需提供 fixture 或仓库内 `references/espn_wc_fallback.json`
6. **Git 认证**：push 前确认远程 URL 和凭据可用；`.env` 中的 `GITHUB_TOKEN` 若不能直接用于 git push，需改用 HTTPS PAT 或 SSH key
7. **Orchestrator 配置**：orchestrator profile 必须配 Ponytail mode（SOUL.md 嵌入或 `.env` 设置 `PONYTAIL_DEFAULT_MODE=full`）；orchestrator worker 需要能稳定启动，若 crash 优先检查 `config.yaml` 模型配置和 toolset 是否合法

## 常见坑

- `hermes kanban block` 没有 `--reason` 参数，用法是 `hermes kanban block <task_id> <reason>`
- coder worker 如果没调用 `kanban_block`，orchestrator 需要补 `block` + `assign`，否则 auditor 不会自动接
- 已完成的任务不能 reopen；如果 coder 误调 `kanban_complete`，只能新建任务或手动 audit
- `--no-fetch` 模式依赖 `/tmp/espn_wc.json`，测试时需提供 fixture 或 fallback
- orchestrator worker crash 时先看 `errors.log`：401 说明 key 无效，404/empty model 说明 provider 名不合法或 YAML 解析失败，`pid not alive` 是上述错误导致的二次症状
- provider 名只在配置里注册过的才有效；若不确定，先在 coder profile 验证一个已知可用的 `provider/base_url/api_key` 组合，再复制到 orchestrator

## 参考文件

- `references/provider-config-template.yaml`：已知可用 provider 配置模板，复制到 profile `config.yaml` 顶部即可

## 安全红线

- 任务未创建成功时，不进入下一步
- coder / auditor 执行失败时，直接报错并停止循环
- 超过循环上限时，必须人工介入，不自动重试
- 压缩失败不阻断流程，降级为原文传递
