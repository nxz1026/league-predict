"""P0-COLLECT2eA 写手：三个"写指令" topic（jc_issue / jc_issue_result / lottery_draw）
解析器已返回同形写指令 {"table","pk","row","notes"} ⇒ 一套通用 upsert_issue_instruction。
COLUMNS 为 dict 形态双职责（§9-74）：列白名单 + jc-cols-check 静态列核对。
调用方持有连接与事务（§9-83）；未知表/未登记列/主键缺列 ⇒ 响亮 ValueError，不静默跳过。"""
from __future__ import annotations

from psycopg import sql
from psycopg.types.json import Json

# 表 → 允许列（字面 dict，列 ⊆ DDL；审计尾 first_seen_at 由 DDL 默认值管，last_seen_at 由 now() 管）
COLUMNS = {
    "fact.jc_issue": ("game_num", "issue_no", "game_name", "sale_begin", "sale_end", "draw_at",
                      "n_matches", "draw_num_list", "raw_head"),
    "fact.jc_issue_draw": ("game_num", "issue_no", "game_key", "game_name", "draw_result", "pool_after",
                           "sales", "pool_after_rj", "sales_rj", "paid_begin", "paid_end",
                           "is_delay", "delay_remark"),
    "fact.lottery_draw": ("game_num", "issue_no", "game_name", "draw_date", "status", "numbers_raw",
                          "numbers", "pool", "prizes", "equipment_count"),
}
_PK = ("game_num", "issue_no")  # 三表主键同形；期号跨玩法重号，绝不可只用 issue_no
_JSONB = frozenset({"draw_num_list", "raw_head", "numbers", "prizes"})

def _validate(table: str, row: dict) -> dict:
    """三道闸（全 ValueError）：未知表 → 未登记列 → 主键缺列；通过 ⇒ 空串归一（""→None）后的 row。"""
    cols = COLUMNS.get(table)
    if cols is None:
        raise ValueError(f"未知写指令目标表 {table!r}")
    extra = set(row) - set(cols)
    if extra:
        raise ValueError(f"指令含未登记列 {sorted(extra)} → {table}")
    missing = [c for c in _PK if c not in row]
    if missing:
        raise ValueError(f"主键缺列 {missing} → {table}")
    return {k: (None if v == "" else v) for k, v in row.items()}


def _build_sql(table: str, cols: list, pk: dict) -> sql.Composed:
    """整条 UPSERT（psycopg.sql）：冲突键=sorted(ins["pk"])；SET=所有非主键列 c=EXCLUDED.c + last_seen_at=now()；
    first_seen_at 绝不进 SET（首见时间只能由 DDL 默认值在真正插入那一次落定）。"""
    schema, name = table.split(".")
    set_parts = [sql.SQL(f"{c} = EXCLUDED.{c}") for c in cols if c not in pk]
    set_parts.append(sql.SQL("last_seen_at = now()"))
    return sql.SQL("insert into {t} ({c}) values ({p}) on conflict ({k}) do update set {s}").format(
        t=sql.Identifier(schema, name),  # 两参拆开：单参 "fact.jc_issue" 会把点吃进引号 ⇒ UndefinedTable
        c=sql.SQL(", ").join(map(sql.Identifier, cols)),
        p=sql.SQL(", ").join([sql.Placeholder()] * len(cols)),
        k=sql.SQL(", ").join(map(sql.Identifier, sorted(pk))),
        s=sql.SQL(", ").join(set_parts))


def upsert_issue_instruction(cur, ins: dict, src_hash: str, src_file: str) -> int:
    """一条写指令 → 一行 UPSERT；表名/列名不在 COLUMNS 登记内 ⇒ ValueError（响亮，别静默跳过）；
    返回受影响行数(0/1)。不开事务、不 commit、不 catch 一切异常（连接归调用方，§9-83）。
    jsonb 列 dict/list 须 Json(...) 包裹（psycopg3 不自动适配 dict，实测 ProgrammingError）；
    timestamp/date/text 直接绑参数，不 str() 强转。"""
    table = ins["table"]
    row = _validate(table, ins["row"])
    cols = list(row) + ["src_hash", "src_file"]
    vals = [Json(v) if c in _JSONB else v for c, v in row.items()] + [src_hash, src_file]
    cur.execute(_build_sql(table, cols, ins["pk"]), vals)
    return cur.rowcount or 0
