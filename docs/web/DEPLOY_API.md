# DEPLOY_API · FastAPI Cloud 部署调研笔记（队长，2026-09-10）

来源：fastapicloud.com 官方文档（CLI deploy/env/logs/login、Deploy Tokens、Env Variables、Install Dependencies、Configuring FastAPI）。

## 结论 TL;DR
1. **没有公开 REST 部署 API；官方自动化路径 = `fastapi` CLI + Deploy Token**（CLI 内含在 `fastapi[standard]`，≥0.9.0 支持 token）。
2. **无头部署完全可行**：`export FASTAPI_CLOUD_TOKEN=<dashboard建> FASTAPI_CLOUD_APP_ID=<app页眉UUID>` 后 `fastapi deploy [PATH]` 全程免交互。**从任意分支/工作树打包上传——不必先合 main，也不再需要 GHA**（修正早期"默认分支才部署"的担忧，那只属于 GitHub 集成路径）。
3. 打包**尊重 `.gitignore`**，可加 `.fastapicloudignore` 精细控制；云端负责 install+build+零停机切换+验证。本地生成 `.fastapicloud/` 目录 → 进 .gitignore。
4. **env 全 CLI**：`fastapi cloud env set [--secret] NAME VALUE`；⚠️ **改 env 不自动重部署**（下次 deploy 才生效）；secret 类型创建后不可转换、值丢失只能删了重建。
5. **日志可编程**：`fastapi cloud logs --tail N --since 30m/2h/2d [--no-follow]`——M5 冒烟检查（启动后拉 30s 日志找 ERROR）可以脚本化。
6. **login 用 OAuth 设备码流**：无头机跑 `fastapi login` 出 URL+code，手机授权即可；凭证持久（用户级），覆盖 env/logs 等账号级操作（deploy token 只管 deploy）。

## 一次性人工操作（用户，5 分钟）
- dashboard → 目标 App → 复制 **App ID**（页眉 UUID，不是名字/slug）
- 该 App → Deploy Tokens → Create（**有效期设 365 天**，默认 90 要记得轮转；只显示一次）
- 手机/浏览器完成 coder 机 `fastapi login` 的设备授权（登录态长期复用）

## ⚠️ 我们的专属坑：依赖装不上
云端安装优先级：`pyproject [project.dependencies]`（支持 uv/uv.lock）→ `pylock.toml` → `requirements.txt` → 都没有才默认装 fastapi[standard]。**全文档未提 optional extras 会被安装**——我们的 web 依赖恰恰都放在 `[project.optional-dependencies].web` + `requirements-web.txt`（引擎零依赖红线）。
**解法（推荐）：staging 部署目录**——发布时组装 `/root/build/league-web/`：`pyproject.toml`（dependencies=web 六件套，requires-python≥3.11，`[tool.fastapi] entrypoint="web.api:app"`）+ `web/` + `static/` + 需要的数据种子，`fastapi deploy /root/build/league-web`。仓库依赖面一字不动，红线保住。（发布脚本归 M5 工单。）

## 数据冷启动彩蛋
`predictions/`、`results/` 是 git tracked → 会被打包上传 = **天然种子数据**，登录即可见内容；云端首跑再靠 M3 惰性刷新续命（scale-to-zero 文件系统是临时的，写回云端不算持久化——数据真相仍在 GHA/本地，云端只读消费，与既定架构一致）。

## M5 执行清单草案（届时进 WO-M5）
1. 用户完成上面一次性操作（token/app-id 交给我，只进 `/root/.config-priv/`，绝不入库）
2. coder 机 `fastapi login` 设备流（用户手机点一次）
3. `fastapi cloud env set`：会话密钥、单账号凭据（--secret）、CORS/域名、ENABLE_CRON=false 等，全按 `.env.example` 清单
4. 组装 staging 目录 → `fastapi deploy --no-wait` → `fastapi cloud logs --since 5m --no-follow` 冒烟
5. 实机走查：/health 200、登录 302/401 矩阵、五 tab 渲染、一次手动触发（吃配额 1 次）
6. GHA prediction cron 下线（前提：M1–M5 全 PASS + 用户点头）
7. 提醒：token 365d 到期日历；重部署=再跑 deploy；换 secret 值走 delete+create

## 与既有决策的一致性核对
✅ "不在本机也不再GHA"（deploy 由 coder 机 CLI 直发）✅ Hobby 缩零→惰性刷新为主 ✅ AI 扩展不阻塞 ✅ 引擎零 diff（staging 方案保 pyproject 主段不动）⚠️ 服务名/域名占位 → 用户 inbox 待办依旧。
