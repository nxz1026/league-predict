# WO-M2 · 只读数据 API

前提：M1 已交付骨架（本工单在 api.py 已注册路由的框架下扩展）。**数据语义一律以 `docs/web/DATA_CONTRACT.md` §2/§3/§4 为准**（含：now_utc 别名陷阱、文件名 BJT 小时粒度、同小时多联赛覆盖坑、§3.3 最新选取规则）。

## 交付物
| 文件 | 职责 |
|---|---|
| `web/services/store.py` | 引擎产物唯一读取层：扫描/解析 predictions、results、backtest、calibration JSON；「每联赛最新一次运行」按契约 §3.3 规则实现（含同小时覆盖应对）；坏文件/缺目录跳过+log，永不抛穿 |
| `web/routers/predictions.py` | `GET /api/v1/predictions/today`（BJT 比赛日口径、按联赛分组）、`/predictions/{date}`、`/championship`、`/accuracy`、`/history` —— 全部 `require_auth`，响应 key 冻结为前端契约（M4 消费） |
| `web/routers/sources.py` | `GET /api/v1/sources/status` 静态部分（配置了哪些上游、env 键名是否存在——绝不回传值） |
| `tests/web/test_m2_*.py` | fixture 造假数据目录（tmp_path），覆盖验收点 |

## 红线
只许动 web/ tests/web/（requirements/pyproject 可必要追加）；引擎零 diff；不触发子进程、不打外部 API；未登录一律 401；输出 UTC→BJT 换算只在出口做；函数 <50 行；3.11 兼容。

## 验收点（闸门+队长）
A pytest 全绿；B 未登录 5 端点全 401；C fixture 目录下 today 返回按联赛分组结构且字段与契约 §2 对齐；D 空目录/坏 JSON 全部 200+空态（不许 500）；E 响应无敏感值。

## 完成信号
`docs/web/M2_report.md`（逐点证据）+ `docs/web/logs/M2.done` 写 `M2-DONE` + UTC。不许 git 操作。
