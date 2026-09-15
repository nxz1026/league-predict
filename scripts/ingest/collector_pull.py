"""incoming/ 中带 .done 标记的文件 → stg 装载 → ops 留痕 → 归档 done/（零拒绝）或 bad/（有拒绝；league_ing 无 DELETE，坏样本必须留证）。
归档规则：零拒绝 → 原件与 .done 都进 done/；有拒绝 → 原件进 bad/、标记仍进 done/（标记语义=已处理）；无 .done 的数据文件一律
不动（抗半包）；未知 topic 连同 .done 挪进 bad/_unknown/。三个目录都是函数/CLI 参数（默认 /srv/league-staging/{incoming,done,bad}，
测试传 tmp）。用法：cd scripts && python -m ingest.collector_pull [--incoming|--done|--bad DIR]。main() 刻意不用 pg.write_conn 包
run()：逐文件提交必须处在确定无外层事务的连接上（否则 conn.transaction() 退化成 SAVEPOINT、提交不发生），_load 的断言钉死它。
"""

from __future__ import annotations

import argparse
import shutil
from contextlib import nullcontext
from pathlib import Path

from psycopg import Connection, pq
from psycopg.types.json import Jsonb

from core.log import logger
from store import pg
from store.upsert_official import STG_TABLES, load_file

INCOMING = Path("/srv/league-staging/incoming")
DONE = Path("/srv/league-staging/done")
BAD = Path("/srv/league-staging/bad")
INGEST_LOG_SQL = ("INSERT INTO ops.ingest_log (topic, src_file, rows_in, rows_ups, rejected, ok) VALUES"
                  " (%s, %s, %s, %s, %s, %s)")
FILE_ARRIVAL_SQL = ("INSERT INTO ops.file_arrival (topic, src_file, bytes, rows, done_marker)"
                    " VALUES (%s, %s, %s, %s, true) ON CONFLICT (topic, src_file) DO UPDATE SET"
                    " arrived_at = now(), bytes = EXCLUDED.bytes, rows = EXCLUDED.rows, done_marker = true")


def _archive(data: Path, marker: Path, incoming: Path, done: Path, bad: Path, clean: bool) -> str:
    """原件按 clean 进 done/ 或 bad/，.done 标记恒进 done/；返回原件落地目录。"""
    target = (done if clean else bad) / data.relative_to(incoming)
    for src, dst in ((data, target), (marker, done / marker.relative_to(incoming))):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    return str(target.parent)


def _load(conn: Connection, data: Path, topic: str, incoming: Path, commit: bool, reason: str | None = None) -> dict:
    """单文件一个独立事务：stg 装载 + 两处留痕，提交成功才返回（失败整体回滚）；reason 非空则不装载、只写失败留痕。"""
    if commit and conn.pgconn.transaction_status != pq.TransactionStatus.IDLE:  # 合法环境只有 pg.connect 的裸连接
        raise RuntimeError("run(commit=True) 外层已有事务 → conn.transaction() 退化成 SAVEPOINT、提交不发生：归档后回滚即无痕丢数据")
    with conn.transaction() if commit else nullcontext(), conn.cursor() as cur:
        if reason:
            cur.execute(INGEST_LOG_SQL, (topic, data.name, 0, 0, Jsonb([{"reason": reason}]), False))
            return {"rows_in": 0, "rows_ups": 0, "rejected_n": 1, "rejected": []}
        result = load_file(conn, data, topic)
        cur.execute(FILE_ARRIVAL_SQL, (topic, str(data.relative_to(incoming)), data.stat().st_size, result["rows_in"]))
        cur.execute(INGEST_LOG_SQL, (topic, data.name, result["rows_in"], result["rows_ups"],
                                     Jsonb(result["rejected"]), result["rejected_n"] == 0))
    return result


def _one(conn: Connection, marker: Path, incoming: Path, done: Path, bad: Path, commit: bool) -> dict:
    """处理一个就绪文件：未知 topic / 装载失败都留痕 ok=false 并进 bad/，绝不把异常抛给调用方。"""
    data = marker.with_suffix("")
    topic = data.parent.name  # topic = 数据文件所在目录名（incoming/<host>/<topic>/<file>.jsonl）
    try:
        reason = "unknown topic" if topic not in STG_TABLES else None  # 未知 topic：不再每轮重复告警
        result = _load(conn, data, topic, incoming, commit, reason)
    except Exception as exc:  # 单文件失败不中断整批：留痕 ok=false → 原件进 bad/、标记进 done/
        logger.error("collector_pull: %s 未装载：%s", data.name, exc)
        result = _load(conn, data, topic, incoming, commit, reason=str(exc))
    roots = (bad / "_unknown", bad / "_unknown") if reason else (done, bad)
    archived = _archive(data, marker, incoming, *roots, result["rejected_n"] == 0)
    logger.info("collector_pull: %s in=%d up=%d rej=%d", data.name, result["rows_in"],
                result["rows_ups"], result["rejected_n"])
    return {**result, "topic": topic, "src_file": data.name, "archived_to": archived}


def run(conn: Connection, incoming: Path = INCOMING, done: Path = DONE, bad: Path = BAD,
        commit: bool = False) -> list[dict]:
    """扫一遍 incoming 处理全部就绪文件（就绪 = 存在同名 .done 标记的数据文件），返回逐文件报告。

    commit=True：每文件一个独立事务、**提交成功才归档**——shutil.move 不随事务回滚，整批共用事务会在后续文件失败时把前一个文件已落库的
    stg/ops 回滚掉、原件却已进 done/（无痕丢数据）；_load 的断言锁死它：外层非 IDLE 即 RuntimeError，不再靠"碰巧 IDLE"；commit=False 归调用方。"""
    return [_one(conn, marker, incoming, done, bad, commit) for marker in
            sorted(m for m in incoming.rglob("*.done") if m.with_suffix("").is_file())]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="incoming 中 .done 文件 → stg 装载 + ops 留痕 + 归档")
    parser.add_argument("--incoming", type=Path, default=INCOMING)
    parser.add_argument("--done", type=Path, default=DONE)
    parser.add_argument("--bad", type=Path, default=BAD)
    args = parser.parse_args(argv)
    conn = pg.connect("ing")  # 裸连接：run(commit=True) 自己开逐文件事务，外面再套事务会让提交退化成 SAVEPOINT
    try:
        logger.info("collector_pull: %d file(s) processed",
                    len(run(conn, args.incoming, args.done, args.bad, commit=True)))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
