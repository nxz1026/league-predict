"""P0-JCSPLIT 纯搬家：jc_load.py 的"每 topic 怎么落库"（_ops/load_topic）原样移入；零行为变化。"""
from pathlib import Path

from core.log import logger
from ingest import jc_write
from ingest.jc_read import read_lines
from psycopg.types.json import Json
from store.parse_collector import parse_line

WRITE = ("jczq_offer", "jczq_result")


def _ops(cur, topic: str, rel: str, size: int | None, n: int, ups: int,
         rej: list, gap: bool, done: bool) -> None:
    cur.execute("insert into ops.file_arrival (topic,src_file,bytes,rows,done_marker) values "
                "(%s,%s,%s,%s,%s) on conflict (topic,src_file) do update set bytes=excluded.bytes,"
                "rows=excluded.rows,done_marker=excluded.done_marker",
                (topic, rel, size, n, done))
    cur.execute("insert into ops.ingest_log (topic,src_file,rows_in,rows_ups,rejected,ok) "
                "values (%s,%s,%s,%s,%s,%s)",
                (topic, rel, n, ups, Json(rej) if rej else None, not rej or gap))


def load_topic(cur, root: Path, marker: Path, topic: str, path: Path | None, state: str) -> dict:
    rel = f"{topic}/{path.name}" if path else f"{marker.stem}/{topic}#MISSING"
    lines = read_lines(path) if path and state in ("jsonl", "orphan") else []
    n, ups, rej = len(lines), 0, []
    if topic in WRITE:
        for i, env in enumerate(lines, 1):
            p = parse_line(env)
            if p is None:
                rej.append({"line": i, "reason": "parse_none"})
                continue
            snap, src = env["snap_ts"], {"src_hash": env["src_hash"], "src_file": rel}
            if topic == "jczq_offer":
                jc_write.upsert_jc_match(cur, p["match"], snap, src, None, None)
                ups += jc_write.upsert_jc_offer(cur, p["row"], snap, src)
            else:
                ups += jc_write.upsert_jc_result(cur, p["row"], snap, src, None, None)
    else:
        logger.info("skip %s n=%d (2e 范围)", topic, n)
    gap, done = state == "missing", state != "missing" and state != "orphan"
    _ops(cur, topic, rel, path.stat().st_size if path else 0, n, ups, rej, gap, done)
    return {"topic": topic, "lines": n, "ups": ups, "gap": gap}
