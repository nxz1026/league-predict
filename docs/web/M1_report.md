# M1 交付报告 — Web 骨架 + 会话认证
> 写作模式：网关降级期，证据全部由队长实测并口述，agent 誊录落盘。裁决=流水线闸门复跑+队长晨审。
SEG2
## 交付物清单（wc -l 队长实测）
web/__init__.py 1 | api.py 72 | auth.py 110 | config.py 65 | errors.py 66 | session_store.py 81 | tests/web/test_m1_auth.py 203 | static/login.html 82 | .env.example 35 | requirements-web.txt 7。
pyproject.toml 仅追加 [project.optional-dependencies].web 与 [tool.fastapi] entryPoint="web.api:app"；按票暂不加 apscheduler（M3）。
SEG3
## 验收点自测（均为队长实测，命令可复跑）
- A 启动：uvicorn web.api:app 实启 → GET /health 200；GET / 未登录 302。
- B 路由边界：GET /login → 302 → /static/login.html 200（实现为一跳重定向替代工单"直 200"，功能等价，队长知悉记录）；未登录 GET /api/v1/me → 401 {"code":"unauthorized",...} 统一错误结构。
- C 登录矩阵：httponly/samesite cookie、登录后 /me 200、错口令 401 不发 cookie、连错 5 次第 6 次 429、logout 后失效——test_m1_auth.py 全覆盖；python3 -m pytest tests/web -q → 15 passed in 2.87s（两次复跑一致）。
- E 敏感值：grep 全 web/ static/ tests/web/ .env.example → 0 命中，测试值均 unit-test- 前缀。
SEG4
## 本票修复的缺陷（冷启动）
web/api.py lifespan 在建表前调用 _purge_expired → sqlite3.OperationalError: no such table: sessions。TestClient fixture 先建表故 pytest 无法暴露；队长冷启动复现并验证修复。修法：_connect → _init_db → _purge_expired（由交卷命令 C1 执行）。
SEG5
## 红线复核（D）
git status --porcelain -- scripts/ ai/ analysis/ references/ output/ SKILL.md .agents → 空；无 pandas/numpy/sklearn；每函数 <50 行；会话过期时间 UTC epoch、展示换算 BJT。
SEG6
## 移交队长晨审事项
1. AUTH_PASSWORD 在 config.py 有安全占位 fallback 默认值：生产部署（M5）必须强制注入并禁止缺省启动。
2. 基础设施：OMP 网关当前仅第一回合可用且响应预算约 1KB（多回合/大入参必断），本票以一次性交卷模式完成，验收时请以闸门机械复跑为准。
