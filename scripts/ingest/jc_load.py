"""P0-COLLECT2i 真包 JSONL → fact.jc_match/jc_offer/jc_result + ops 留痕；批↔文件按文件名时间戳窗口归属；同窗口多文件逐个装载（C 条修复）。"""
import argparse
from contextlib import closing
from pathlib import Path

from core.log import logger
from ingest import jc_write
from ingest.jc_read import files_for_batch, iter_markers, read_lines
from psycopg.types.json import Json
from store import pg
from store.parse_collector import parse_line

TOPICS = ("jczq_offer", "jczq_result", "jc_issue", "jc_issue_result",
          "lottery_draw", "jclq_offer", "jclq_result")
WRITE = ("jczq_offer", "jczq_result")
TABLES = ("jc_match", "jc_offer", "jc_result", "jc_issue", "jc_issue_draw",
          "jc_issue_match", "jc_issue_prize", "lottery_draw")


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


def load_batch(conn, root: Path, marker: Path) -> dict:
    topics, errors = [], []
    try:
        with conn.cursor() as cur:
            for topic, cands in files_for_batch(root, marker, TOPICS).items():
                for path, state in cands or [(None, "missing")]:
                    topics.append(load_topic(cur, root, marker, topic, path, state))
        conn.commit()
    except Exception as e:
        conn.rollback()
        errors.append(f"{marker.name}:{type(e).__name__}:{e}")
    return {"marker": marker.name, "topics": topics, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--batch")
    args = ap.parse_args(argv)
    root = Path(args.dir)
    with closing(pg.connect("ing")) as conn:
        for m in iter_markers(root, args.batch):
            r = load_batch(conn, root, m)
            logger.info("batch %s ups=%d errors=%s", r["marker"],
                        sum(t["ups"] for t in r["topics"]), r["errors"])
        seen = {p for m in iter_markers(root, args.batch)
                for cs in files_for_batch(root, m, TOPICS).values() for p, _ in cs or [] if p}
        orph = [p for t in TOPICS for p in sorted((root / t).glob("*.jsonl")) if p not in seen]
        try:
            with conn.cursor() as cur:
                for p in orph: load_topic(cur, root, Path("orphan"), p.parent.name, p, "orphan")
            conn.commit()
        except Exception:
            conn.rollback()
        logger.info("orphan 装载 n=%d 文件=%s", len(orph),
                    ",".join(p.name for p in orph[:5]) + ("…" if len(orph) > 5 else "") or "-")
        with conn.cursor() as cur:
            vals = [cur.execute(f"select count(*) from fact.{t}").fetchone()[0] for t in TABLES]
        conn.commit()
        logger.info("count jc_match=%d jc_offer=%d jc_result=%d jc_issue=%d jc_issue_draw=%d "
                    "jc_issue_match=%d jc_issue_prize=%d lottery_draw=%d", *vals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
