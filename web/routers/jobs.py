"""web.routers.jobs — 任务触发端点 + 惰性刷新（WO-M3）。

端点：
- POST /api/v1/jobs/predict   require_auth；参数白名单透传（league/dates 等），
  禁任意字符串注入 argv；无预算 → 429；已有运行 → 409/202 语义；
  提交后异步执行（线程池），立即返回 202 + job。
- GET  /api/v1/jobs/{id}      require_auth；状态机可轮询到终态。
- GET  /api/v1/jobs           require_auth；最近任务列表。

惰性刷新：predictions/today 缺数据时，fire-and-forget 后台任务（经同一把锁
与配额守卫；同日去重，一天至多自动触发一次）。
"""
from __future__ import annotations

import concurrent.futures
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from web import config, errors
from web.auth import require_auth
from web.services import jobs, store
from web.services.datasource import LEAGUES

router = APIRouter(prefix="/api/v1", tags=["jobs"])

# 线程池：引擎子进程执行不阻塞请求线程（fire-and-forget 语义）。
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# 参数白名单（契约 §1.1 安全子集）：固定取值域校验，杜绝任意字符串注入 argv。
_FLAG_ARGS = {
    "--all": False,
    "--monte-carlo": False,
    "--no-dc": False,
    "--no-ml": False,
    "--dashboard": False,
}
_VALUE_ARGS = {
    "--league": sorted(LEAGUES),
    "--data-source": ("football-data", "espn", "api-football", ""),
    "--n-simulations": None,  # 正整数，单独校验
    "--dates": None,          # YYYYMMDD-YYYYMMDD，正则校验
}
_FORBIDDEN = {"--backtest", "--cleanup", "--train-ml", "--no-fetch", "--update-rankings", "--help"}


def _validate_args(params: dict) -> list[str]:
    """白名单校验 → argv 列表；非法参数抛 400（code=invalid_params）。"""
    unknown = set(params) - {"league", "dates", "data_source", "monte_carlo",
                             "n_simulations", "no_dc", "no_ml", "dashboard", "all"}
    if unknown:
        raise errors.ApiError("invalid_params", f"未知参数: {sorted(unknown)}")
    argv: list[str] = []
    if params.get("all"):
        argv.append("--all")
    league = params.get("league")
    if league is not None:
        if league not in LEAGUES:
            raise errors.ApiError("invalid_params", f"未知联赛: {league}")
        argv += ["--league", str(league)]
    source = params.get("data_source")
    if source is not None:
        if source not in _VALUE_ARGS["--data-source"]:
            raise errors.ApiError("invalid_params", f"未知数据源: {source}")
        if source:
            argv += ["--data-source", str(source)]
    dates = params.get("dates")
    if dates is not None:
        if not isinstance(dates, str) or len(dates) != 17 or dates[8] != "-":
            raise errors.ApiError("invalid_params", "dates 须为 YYYYMMDD-YYYYMMDD")
        try:
            datetime.strptime(dates[:8], "%Y%m%d")
            datetime.strptime(dates[9:], "%Y%m%d")
        except ValueError:
            raise errors.ApiError("invalid_params", "dates 须为 YYYYMMDD-YYYYMMDD")
        argv += ["--dates", dates]
    n_sim = params.get("n_simulations")
    if n_sim is not None:
        if not isinstance(n_sim, int) or n_sim < 1:
            raise errors.ApiError("invalid_params", "n_simulations 须为正整数")
        argv += ["--n-simulations", str(n_sim)]
    for flag, _ in _FLAG_ARGS.items():
        key = flag[2:].replace("-", "_")
        if params.get(key):
            argv.append(flag)
    return argv


def _job_view(job: dict) -> dict:
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "trigger": job.get("trigger"),
        "args": job.get("args", []),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "exit_code": job.get("exit_code"),
        "error": job.get("error"),
    }


@router.post("/jobs/predict", status_code=202)
def jobs_predict(body: dict | None, request: Request,
                 _: None = Depends(require_auth)) -> JSONResponse:
    """提交预测任务（队列语义：返回 202 + job；并发时 409 + already_running）。"""
    params = body or {}
    argv = _validate_args(params)
    job, reason = jobs.trigger_predict(argv, trigger="manual")
    if reason == "quota_exhausted":
        usage = jobs.quota_usage()
        raise errors.ApiError("quota_exhausted",
                              f"今日预测配额已用尽（{usage['used']}/{usage['limit']}）",
                              http_status=429)
    if reason == "already_running":
        return JSONResponse(status_code=409, content={
            "code": "already_running",
            "message": "已有预测任务在运行，请稍后再试",
            "job": _job_view(job),
        })
    # 异步执行（fire-and-forget：失败只写状态文件，绝不抛回请求线程）。
    _executor.submit(jobs.run_job, job["id"])
    return JSONResponse(status_code=202, content={"job": _job_view(job)})


@router.get("/jobs/{jid}")
def jobs_get(jid: str, request: Request,
             _: None = Depends(require_auth)) -> dict:
    """查询任务状态（可轮询到终态）。"""
    job = jobs.get_job(jid)
    if job is None:
        raise errors.ApiError("job_not_found", f"任务不存在: {jid}", http_status=404)
    view = _job_view(job)
    view["log_tail"] = jobs.read_job_log(jid)
    return {"job": view}


@router.get("/jobs")
def jobs_list(request: Request, _: None = Depends(require_auth)) -> dict:
    """最近任务列表（按创建时间倒序）。"""
    return {"jobs": [_job_view(j) for j in jobs.list_jobs(limit=20)]}


# --- 惰性刷新（predictions/today 缺数据兜底）-----------------------------

def _today_has_data() -> bool:
    """今天各联赛预测是否齐全（任一联赛有 today 窗口数据即视为有数据）。"""
    day = store.bjt_today()
    for league, doc in store.latest_by_league().items():
        if league in LEAGUES and store.covers_date(doc.get("data", {}), day):
            return True
    return False


def _lazy_auto_trigger() -> dict:
    """同日去重的自动触发：成功/已触发 → 200 语义；配额/并发 → 说明。"""
    marker = config.DATA_DIR / "auto_refresh_last.json"
    today = datetime.now(timezone.utc).date().isoformat()
    if marker.is_file():
        try:
            payload = json.loads(marker.read_text() or "{}")
        except (ValueError, OSError):
            payload = {}
        if payload.get("day") == today:
            return {"triggered": False, "reason": "already_today"}
    if not config.AUTO_REFRESH_DAILY:
        return {"triggered": False, "reason": "disabled"}
    job, reason = jobs.trigger_predict([], trigger="auto")
    if reason == "quota_exhausted":
        return {"triggered": False, "reason": "quota_exhausted"}
    if reason == "already_running":
        return {"triggered": False, "reason": "already_running"}
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"day": today, "job": job["id"]}, ensure_ascii=False))
    _executor.submit(jobs.run_job, job["id"])
    return {"triggered": True, "job": job["id"]}


@router.get("/jobs/auto/refresh")
def jobs_auto(request: Request, _: None = Depends(require_auth)) -> dict:
    """惰性刷新入口：today 有数据 → 不触发；缺 → 同日去重自动触发。"""
    if _today_has_data():
        return {"triggered": False, "reason": "data_available", "auto": False}
    result = _lazy_auto_trigger()
    result["auto"] = True
    return result