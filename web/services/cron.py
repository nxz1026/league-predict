"""web.services.cron — apscheduler 可选件（M3，默认关闭）。

- 仅当 config.ENABLE_CRON=true 才启动；try-import，缺依赖 → 日志降级，绝不阻碍启动。
- 每日 BJT CRON_HOUR 触发一次全联赛预测（argv=[]，白名单语义=全部联赛默认参数）。
- 触发经 jobs.trigger_predict：配额守卫 + 并发守卫都在那里，cron 只负责定时投递。
"""
from __future__ import annotations

import logging
import threading

from web import config
from web.services import jobs

logger = logging.getLogger("web.cron")

_scheduler = None
_started = False
_lock = threading.Lock()


def _cron_tick() -> None:
    """定时触发的回调：守卫放 jobs 层，这里只记结果。"""
    try:
        job, reason = jobs.trigger_predict([], trigger="cron")
        if job is not None:
            from web.routers.jobs import _executor
            _executor.submit(jobs.run_job, job["id"])
            logger.info("cron 触发预测 job=%s", job["id"])
        else:
            logger.info("cron 触发被守卫拒绝: %s", reason)
    except Exception as exc:
        logger.exception("cron 触发异常（不影响主流程）: %s", exc)


def start_scheduler(app) -> None:
    """启动每日计划任务（幂等）。app 参数保留用于未来注册关闭钩子。"""
    global _scheduler, _started
    with _lock:
        if _started:
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.warning("apscheduler 未安装，cron 已停用（可选件，可忽略）")
            return
        _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        _scheduler.add_job(
            _cron_tick,
            CronTrigger(hour=config.CRON_HOUR, minute=0),
            id="daily_predict",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        _scheduler.start()
        _started = True
        logger.info("cron 已启动: 每日 %02d:00 (BJT)", config.CRON_HOUR)


def shutdown_scheduler() -> None:
    """优雅关闭（shutdown(wait=False) 立即返回，不阻塞 web 关闭）。"""
    global _started
    with _lock:
        if _started and _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _started = False
            logger.info("cron 已停止")