# WO-M1 · Web 骨架 + 会话认证（工单）

前提：M0a 已验收（契约 §1–4）；本工单不依赖 M0b 结果。
参照：`docs/web/PLAN.md` §2/§4/§5；welfare_predict 的实现范式（单入口 app、会话存储、全局异常处理）——只参照行为，不得复制代码。

## 目标
本地可 `uvicorn` 启动的 FastAPI 骨架 + 单账号会话认证闭环 + 登录页 + 健康检查。**不做**业务数据端点（M2 范围）。

## 交付物清单（全部为新增路径；pyproject 只许追加）
| 文件 | 职责 | 约束 |
|---|---|---|
| `web/api.py` | app 创建（title/version）、`/health`（免鉴权）、静态挂载、未登录 `/`→302 `/login`、路由注册、异常处理接线、`__main__` 开发入口（host/port 读 env） | 目标 <120 行 |
| `web/config.py` | **唯一 env 读取点**（python-dotenv；模块常量）；会话 TTL / CORS / 是否走 https 的开关 env 均在此定义；默认值必须安全（默认仅本机可访、https 下 cookie secure 开） | 不 import 引擎模块 |
| `web/session_store.py` | SQLite 会话存储（仅 stdlib sqlite3）：token(uuid4hex)/created/expires（默认 12h）/主动失效；过期行懒惰清理；db 路径 env，默认 `web/.data/`（**不得**落引擎数据目录） | |
| `web/auth.py` | 路由：`POST /api/v1/login`、`POST /api/v1/logout`、`GET /api/v1/me`；恒定时间比较；登录限速（连续失败 5 次 → 10 分钟内 429）；cookie httponly+samesite=lax（secure 随 env）；导出 `require_auth` Depends 供 M2/M3 用 | |
| `web/errors.py` | 统一 JSON 错误 `{code,message,detail?}`；绝不泄漏堆栈；404/405/422/500 接线 | |
| `static/login.html` | 单文件 vanilla 页面（无构建、无外链 CDN），错误提示位、Enter 提交 | |
| `.env.example` | 全部 env 键的占位与注释（清单**唯一出处**，文档不写具体值） | 全占位 |
| `requirements-web.txt` | `fastapi[standard]`、uvicorn、pydantic、python-dotenv、loguru | **暂不加 apscheduler**（M3 再加）；禁 pandas/sklearn |
| `pyproject.toml` | 仅追加 `[project.optional-dependencies] web=[...]` 与 `[tool.fastapi] entryPoint="web.api:app"` | requires-python ≥3.11 |
| `tests/web/test_m1_auth.py` | fastapi TestClient 覆盖下方验收 B/C 全部矩阵 | fixture 值用 `unit-test-` 前缀 dummy |

## 红线（任一违反即返工）
1. `scripts/`、`core/` 零 diff。
2. 仓库任何文件（含测试、.env.example、报告）不得出现真实敏感值，只许占位符。
3. 除上表清单外零新增、零改动（requirements.txt、引擎配置不许碰）。
4. 每函数 <50 行；超限须注释说明理由。
5. 语法兼容 Python 3.11（GHA 3.11 / coder 3.12）。
6. 时间存储一律 UTC epoch，展示换算 BJT（Asia/Shanghai）——本票只有会话过期时间，照此纪律写。

## 验收点（队长逐条实测）
- **A** 全新 venv `pip install -r requirements-web.txt` 成功；`uvicorn web.api:app` 可起。
- **B** `GET /health`→200 免鉴权；未登录 `GET /`→302 `/login`；`GET /login`→200；未登录 `GET /api/v1/me`→401（统一 JSON 错误结构）。
- **C** 正确 env 值登录→Set-Cookie（httponly/lax）；随后 `me`→200；错误值→401 不发 cookie；连续 5 错后第 6 次→429；`logout` 后 `me` 回 401。
- **D** `git diff` 复核红线；`pytest tests/web` 全绿。
- **E** grep 全仓无敏感值。

## 交付与自报
完成后写 `docs/web/M1_report.md`（做了什么 / 逐验收点自测证据 / 未尽事项）；哨兵 `docs/web/logs/M1.done` 写 `M1-DONE` + UTC 时间——唯一完成信号。
**不要 git commit/push**（提交由队长做）。

## 执行纪律
流水线增量落盘（写完一个文件立即保存再看下一个）；禁止以纯文字总结结束回合；不需要请示，直接执行。
