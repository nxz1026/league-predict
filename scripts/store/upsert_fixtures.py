"""raw 落地块 → ref.team + fact.fixture（fixture_id 用源自己的 id：AF 权威口径，跨源对齐留给后续单）。
路径：raw.{af_raw,fd_raw}（只认 200，403 绝不当数据）→ parse_api → ref.team（UNIQUE(sport,name_cn) 命中合并 aliases）
→ fact.fixture（ON CONFLICT DO UPDATE）；未知 league_key / 缺 season → skipped + logger.warning，不静默丢也不崩批。
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection, sql
from psycopg.types.json import Jsonb

from core.i18n import to_cn
from core.log import logger
from store.parse_api import af_fixtures, fd_fixtures

SPORT = "football"
# (raw 块表, 结果源名, 解析函数, 源队伍 id 字段, league 映射)；队伍 id 是 (主队, 客队) 二元组，aliases 要两队源 id
SOURCES = (
    {"table": "af_raw", "source": "api_football", "parse": af_fixtures, "ids": "af_team_id", "map": "af"},
    {"table": "fd_raw", "source": "football_data", "parse": fd_fixtures, "ids": "fd_team_id", "map": "fd"},
)
TEAM_SQL = ("INSERT INTO ref.team (sport, name_cn, aliases) VALUES (%s, %s, %s) ON CONFLICT (sport, name_cn)"
            " DO UPDATE SET aliases = ref.team.aliases || EXCLUDED.aliases RETURNING team_id")
FIXTURE_SQL = (
    "INSERT INTO fact.fixture (fixture_id, league_key, season, round, kickoff_at, home_team_id, away_team_id,"
    " status, venue, source_ids) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    " ON CONFLICT (fixture_id) DO UPDATE SET league_key = EXCLUDED.league_key, season = EXCLUDED.season,"
    " round = EXCLUDED.round, kickoff_at = EXCLUDED.kickoff_at, home_team_id = EXCLUDED.home_team_id,"
    " away_team_id = EXCLUDED.away_team_id, venue = COALESCE(EXCLUDED.venue, fact.fixture.venue),"
    " status = CASE WHEN EXCLUDED.status = 'unknown' THEN fact.fixture.status ELSE EXCLUDED.status END,"
    " source_ids = fact.fixture.source_ids || EXCLUDED.source_ids, updated_at = now()")


def league_maps(conn: Connection) -> tuple[dict[int, str], dict[str, str]]:
    """ref.league.ids → ({AF league id: key}, {FD competition code: key})；联赛真相只在 DB，代码里不复制第二份。"""
    rows = conn.execute("SELECT league_key, ids->>'api_football', ids->>'football_data' FROM ref.league").fetchall()
    return ({int(af): key for key, af, _ in rows if af}, {fd: key for key, _, fd in rows if fd})


def read_blocks(conn: Connection, table: str, params_hashes: list[str] | None = None) -> list[dict]:
    """取该块表 http_status=200 的 body；params_hashes 非空时只取这些块（重跑/测试用）。"""
    if table not in [spec["table"] for spec in SOURCES]:
        raise ValueError(f"unknown raw block table {table!r}; expected af_raw/fd_raw")
    tail = " AND params_hash = ANY(%s)" if params_hashes else ""
    query = sql.SQL("SELECT body FROM raw.{} WHERE http_status = 200" + tail + " ORDER BY id").format(
        sql.Identifier(table))
    return [body for (body,) in conn.execute(query, (params_hashes,) if params_hashes else ()).fetchall()]


def _team_id(cur, name: str | None, source: str, team_id: int | None) -> int | None:
    """队伍按 UNIQUE(sport,name_cn) upsert；中文名一律 to_cn（未命中=原名，本模块不造中文名）。"""
    if not name or team_id is None:
        return None
    cur.execute(TEAM_SQL, (SPORT, to_cn(name), Jsonb({source: team_id})))
    return cur.fetchone()[0]


def _store_row(cur, row: dict, spec: dict, known: set[str], stats: dict) -> None:
    """一行：两队 upsert → fact.fixture upsert；league_key 不可认的行只计数（不写库）。"""
    if row["league_key"] not in known or row["season"] is None:
        stats["skipped"] += 1
        stats["unknown"].add(row["league_key"])
        return
    home, away = row[spec["ids"]] or (None, None)
    cur.execute(FIXTURE_SQL, (row["fixture_id"], row["league_key"], row["season"], row["round"], row["kickoff_at"],
                              _team_id(cur, row["home_name"], spec["source"], home),
                              _team_id(cur, row["away_name"], spec["source"], away), row["status"], row["venue"],
                              Jsonb({spec["source"]: row["fixture_id"]})))
    stats["fixtures"] += 1


def run(conn: Connection, params_hashes: list[str] | None = None) -> dict[str, Any]:
    """raw 的 200 块 → ref.team + fact.fixture；返回 {rows, fixtures, skipped, unknown_leagues}。"""
    af_map, fd_map = league_maps(conn)
    known = set(af_map.values()) | set(fd_map.values())
    stats: dict[str, Any] = {"rows": 0, "fixtures": 0, "skipped": 0, "unknown": set()}
    with conn.cursor() as cur:
        for spec in SOURCES:
            leagues = af_map if spec["map"] == "af" else fd_map
            for body in read_blocks(conn, spec["table"], params_hashes):
                for row in spec["parse"](body, leagues):
                    stats["rows"] += 1
                    _store_row(cur, row, spec, known, stats)
    if stats["skipped"]:
        logger.warning(f"[fact.fixture] 跳过 {stats['skipped']} 行：league_key 不在 ref.league 或 season 缺失，"
                       f"league_key={sorted(map(str, stats['unknown']))}")
    logger.info(f"[fact.fixture] 解析 {stats['rows']} 行 → 写入 {stats['fixtures']} 行，跳过 {stats['skipped']} 行")
    return {"rows": stats["rows"], "fixtures": stats["fixtures"], "skipped": stats["skipped"],
            "unknown_leagues": sorted(map(str, stats["unknown"]))}
