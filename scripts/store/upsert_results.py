"""raw 落地块 → fact.fixture_result（每源一行，PK(fixture_id,source)；两源谁也不覆盖谁）。

与 upsert_fixtures 同源同解析：沿用它的 SOURCES/read_blocks，保证"表→源名→解析函数"只有一份定义。
fixture 缺失（例如该行 league_key 未知、上一层已跳过）时 SELECT ... WHERE EXISTS 直接不落行 → 外键不破。
raw 列存该场原始节点，解析出问题不必回头再请求；elapsed_ht 只认 AF 半场快照（见 parse_api._af_row）。
事务归调用方持有（测试靠它整体 rollback）；本模块不 commit。
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from core.log import logger
from store.upsert_fixtures import SOURCES, league_maps, read_blocks

RESULT_SQL = (
    "INSERT INTO fact.fixture_result (fixture_id, source, ft_h, ft_a, ht_h, ht_a, elapsed_ht, status,"
    " confirmed_at, raw) SELECT %(fid)s, %(src)s, %(ft_h)s, %(ft_a)s, %(ht_h)s, %(ht_a)s, %(elapsed)s,"
    " %(status)s, now(), %(raw)s WHERE EXISTS (SELECT 1 FROM fact.fixture WHERE fixture_id = %(fid)s)"
    " ON CONFLICT (fixture_id, source) DO UPDATE SET ft_h = EXCLUDED.ft_h, ft_a = EXCLUDED.ft_a,"
    " ht_h = EXCLUDED.ht_h, ht_a = EXCLUDED.ht_a, elapsed_ht = EXCLUDED.elapsed_ht,"
    " status = EXCLUDED.status, confirmed_at = EXCLUDED.confirmed_at, raw = EXCLUDED.raw")


def _params(row: dict, source: str) -> dict[str, Any]:
    return {"fid": row["fixture_id"], "src": source, "ft_h": row["ft_h"], "ft_a": row["ft_a"], "ht_h": row["ht_h"],
            "ht_a": row["ht_a"], "elapsed": row["elapsed_ht"], "status": row["status"],
            "raw": Jsonb(row["raw_node"])}


def run(conn: Connection, params_hashes: list[str] | None = None) -> dict[str, Any]:
    """raw 的 200 块 → fact.fixture_result；返回 {rows, results, orphans, conflicts}。"""
    stats: dict[str, Any] = {"rows": 0, "results": 0, "orphans": 0}
    af_map, fd_map = league_maps(conn)  # 与 upsert_fixtures 同一份联赛真相（DB），避免两路径口径分叉
    with conn.cursor() as cur:
        for spec in SOURCES:
            leagues = af_map if spec["map"] == "af" else fd_map
            for body in read_blocks(conn, spec["table"], params_hashes):
                for row in spec["parse"](body, leagues):
                    stats["rows"] += 1
                    cur.execute(RESULT_SQL, _params(row, spec["source"]))
                    stats["results" if cur.rowcount else "orphans"] += 1
    conflicts = conn.execute("SELECT count(*) FROM fact.v_result_conflict").fetchone()[0]
    logger.warning(f"[fact.fixture_result] 写入 {stats['results']} 行，{stats['orphans']} 行因 fixture 缺失未落；"
                   f"两源分歧 {conflicts} 场（fact.v_result_conflict）")
    return {"rows": stats["rows"], "results": stats["results"], "orphans": stats["orphans"], "conflicts": conflicts}
