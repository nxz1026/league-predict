"""fact/ref 只读接口（下游 app/ro 角色用；本层只发 SELECT，不做任何写）。用途：回填自检（league_season_count）、
票面/模型取数（fixtures_between、fixture_with_result）、翻译补全待办（unmatched_teams）、认队体检
（team_identity_audit）；conn 由调用方给（store.pg.connect("app"/"ro")）。
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from store.team_identity import AUDIT_SQL

FIXTURE_COLS = ("fixture_id, league_key, season, round, kickoff_at, home_team_id, away_team_id, status, venue")
RESULT_COLS = "source, ft_h, ft_a, ht_h, ht_a, elapsed_ht, status, confirmed_at"
UNTRANSLATED = "[一-鿿]"  # name_cn 里一个 CJK 都没有 ⇒ 仍是原名（to_cn 未命中），供后续翻译补全


def _rows(conn: Connection, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def fixtures_between(conn: Connection, start, end, league_key: str | None = None) -> list[dict[str, Any]]:
    """[start, end) 内的赛程（含未开赛）；league_key=None 时跨联赛。"""
    query = f"SELECT {FIXTURE_COLS} FROM fact.fixture WHERE kickoff_at >= %s AND kickoff_at < %s"
    params: list[Any] = [start, end]
    if league_key:
        query, params = query + " AND league_key = %s", [*params, league_key]
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


def source_coverage(conn: Connection) -> dict[str, Any]:
    """双源覆盖自审：AF 场数 / FD 场数 / 双源重叠场数 / 最近一次 FD 未对齐数（读 ops.ingest_log）。"""
    row = _rows(conn, """
        SELECT count(*) FILTER (WHERE source = 'api_football') AS af_rows,
               count(*) FILTER (WHERE source = 'football_data') AS fd_rows,
               count(DISTINCT fixture_id) FILTER (WHERE n_src = 2) AS both
          FROM (SELECT fixture_id, source, count(*) OVER (PARTITION BY fixture_id) AS n_src
                  FROM fact.fixture_result) s""")[0]
    last = _rows(conn, "SELECT coalesce(jsonb_array_length(rejected), 0) AS unmatched FROM ops.ingest_log"
                       " WHERE topic = 'fd_align' ORDER BY id DESC LIMIT 1")
    return {**row, "fd_unmatched": last[0]["unmatched"] if last else 0}


def unmatched_fd(conn: Connection, limit: int = 20, *, src_file: str | None = None,
                 fd_ids: set[int] | None = None) -> list[dict[str, Any]]:
    """FD 对齐失败明细（ops.ingest_log.topic='fd_align'）的作用域读法，供人工复核；无留痕返回 []。

    src_file 等值过滤留痕来源（生产写 'raw.fd_raw'；调用方可传本批唯一标记）；fd_ids 只保留 rejected 里
    fd_id 落在该集合的条目（= **本批**哨兵 id，测试/回填自证用）。两者都给取交集；**都不给＝最新一条**
    （生产读法：会被任何更新的留痕顶掉，测试与 CLI 汇总不许依赖）。本层只 SELECT，不写 ops.ingest_log。
    """
    where, params = ["topic = 'fd_align'"], []
    if src_file is not None:
        where.append("src_file = %s")
        params.append(src_file)
    latest = f"SELECT rejected FROM ops.ingest_log WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 1"
    if fd_ids is None:  # 生产读法：整条最新留痕
        rows = _rows(conn, latest, tuple(params))
        return list(rows[0]["rejected"] or [])[:limit] if rows else []
    entries = (f"SELECT e.entry FROM ({latest}) s, LATERAL jsonb_array_elements(s.rejected)"
               " WITH ORDINALITY AS e(entry, ord) WHERE e.entry->>'fd_id' = ANY(%s::text[])")
    return [row["entry"] for row in _rows(conn, entries + " ORDER BY e.ord LIMIT %s",
                                          (*params, [str(fid) for fid in fd_ids], limit))]


def team_identity_audit(conn: Connection) -> dict[str, Any]:
    """认队体检（只读）：dup_af/dup_fd 是按 (sport, 源 id) 分组的裂行数，**必须恒 0**（team_af_key/team_fd_key
    两个 partial unique 兜底）；orphan=未被任何 fact.fixture 引用的队，可 >0。SQL 恒量在 store.team_identity。"""
    return _rows(conn, AUDIT_SQL)[0]
