from __future__ import annotations

"""Output: save results and cleanup old files."""

import json
import time
from datetime import datetime, timezone
from typing import Any

from core.config import PREDICTIONS_DIR, RESULTS_DIR
from core.log import logger


def cleanup_old_files(days: int = 7) -> int:
    """清理超过 N 天的 predictions/ 和 results/ 文件"""
    cutoff = time.time() - days * 86400
    removed = 0
    for directory in [PREDICTIONS_DIR, RESULTS_DIR]:
        if not directory.exists():
            continue
        for f in directory.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
                logger.info(f"Cleaned up: {f.name}")
    if removed > 0:
        logger.info(f"Cleanup complete: removed {removed} files older than {days} days")
    return removed


def save_results(past_matches: list[dict[str, Any]]) -> None:
    """将已结束比赛结果保存到 results/ 目录，每天一份。"""
    scored = [m for m in past_matches if m.get("score") and "-" in m.get("score","")]
    if not scored:
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = RESULTS_DIR / f"result_{today}.json"
    if path.exists():
        return
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        matches: list[dict[str, Any]] = []
        for m in scored:
            parts = m["score"].split("-")
            if len(parts) == 2:
                matches.append({
                    "id": m.get("name",""),
                    "kickoff_utc": m.get("kickoff_utc",""),
                    "home": m.get("home_en", m.get("home","")),
                    "away": m.get("away_en", m.get("away","")),
                    "home_score": int(parts[0]),
                    "away_score": int(parts[1]),
                    "status": m.get("status",""),
                })
        with open(path, "w") as f:
            json.dump({"date": today, "matches": matches}, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved results: {path} ({len(matches)} matches)")
    except Exception as e:
        logger.info(f"save_results error: {e}")
