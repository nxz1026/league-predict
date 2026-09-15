"""fact/ref 只读接口（下游 app/ro 角色用；本层只发 SELECT，不做任何写）。

用途：回填自检（league_season_count）、票面/模型取数（fixtures_between、fixture_with_result）、
翻译补全待办（unmatched_teams）。conn 由调用方给（store.pg.connect("app"/"ro")）。
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

FIXTURE_COLS = ("fixture_id, league_key, season, round, kickoff_at, home_team_id, away_team_id, status, venue")
RESULT_COLS = "source, ft_h, ft_a, ht_h, ht_a, elapsed_ht, status, confirmed_at"
# 中文判定：name_cn 里一个 CJK 字符都没有 ⇒ 仍是原名（to_cn 未命中），供后续翻译补全
UNTRANSLATED = "[一-鿿]"


def _rows(conn: Connection, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def fixtures_between(conn: Connection, start, end, league_key: str | None = None) -> list[dict[str, Any]]:
    """[start, end) 内的赛程（含未开赛）；league_key=None 时跨联赛。"""
    query = f"SELECT {FIXTURE_COLS} FROM fact.fixture WHERE kickoff_at >= %s AND kickoff_at < %s"
    params: list[Any] = [start, end]
    if league_key:
        query += " AND league_key = %s"
        params.append(league_key)
    return _rows(conn, query + " ORDER BY kickoff_at, fixture_id", tuple(params))


def fixture_with_result(conn: Connection, fixture_id: int) -> dict[str, Any] | None:
    """单场：fixture 字段 + "results" 列表（每源一行，含半场）；查无此场返回 None。"""
    fixture = _rows(conn, f"SELECT {FIXTURE_COLS} FROM fact.fixture WHERE fixture_id = %s", (fixture_id,))
    if not fixture:
        return None
    results = _rows(conn, f"SELECT {RESULT_COLS} FROM fact.fixture_result WHERE fixture_id = %s ORDER BY source",
                    (fixture_id,))
    return {**fixture[0], "results": results}


def league_season_count(conn: Connection) -> list[dict[str, Any]]:
    """回填自检：每联赛×赛季的场次数 / 有赛果场次数 / 有半场的赛果行数（HT 非空率的分子）。"""
    return _rows(conn, """
        SELECT f.league_key, f.season,
               count(DISTINCT f.fixture_id) AS fixtures,
               count(DISTINCT r.fixture_id) AS with_result,
               count(*) FILTER (WHERE r.ht_h IS NOT NULL) AS ht_rows
          FROM fact.fixture f LEFT JOIN fact.fixture_result r USING (fixture_id)
         GROUP BY f.league_key, f.season ORDER BY f.league_key, f.season""")


def unmatched_teams(conn: Connection) -> list[dict[str, Any]]:
    """name_cn 至今无中文（= to_cn 未命中）的队伍，供后续翻译补全；只读，不改 ref.team。"""
    return _rows(conn, f"SELECT team_id, name_cn, aliases FROM ref.team WHERE name_cn !~ '{UNTRANSLATED}'"
                       " ORDER BY team_id")
