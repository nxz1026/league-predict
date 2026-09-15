"""契约 v1.1 值换算器与共享件（纯函数：零 DB、零网络、零副作用，只用 stdlib）：
need/dec/clock/pair/split_numbers 值换算 + build 规格表造行 + out 统一返回体 + canonical_src_hash。
§5.0 口径「采集机是搬运工」：官方原值列一律照抄——"取消" / "3＋,1" / "---" 不清洗、不改名、不换算；
数字与时间只写进新列（kickoff_bj 由 matchDate+matchTime 拼、ft_h 由 sectionsNo999 拆、goal_line_value 由 goalLineValue 转），原值列同排保留。
规格表写法 "官方键[:转换码]>规范列"，转换码见 CAST；带 :c 的时间列缺/空/解析不了一律 None。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def need(payload: dict, key: str, kind: Any) -> Any:
    """必需键（身份/结构）：缺键、类型不符、空值（""/0 不许当身份）→ raise ValueError 点名该键。"""
    value = payload.get(key)
    if not isinstance(value, kind) or (not value and not isinstance(value, (dict, list))):
        raise ValueError(f"字段 {key} 缺失或类型不对：{value!r}，期望 {kind}")
    return value


def dec(value: Any) -> Decimal | None:
    """官方数字串（"1.45" / "-1.00" / "+4"）→ Decimal；空串/非数字 → None，绝不补 0。"""
    try:
        return Decimal(value.strip()) if isinstance(value, str) and value.strip() else None
    except InvalidOperation:
        return None


def clock(value: Any) -> datetime | date | None:
    """官方北京时间裸串（"2026-09-15 19:45" 带时刻 / "2026-09-15" 仅日期）→ datetime/date；解析不了 → None。"""
    text = value.strip() if isinstance(value, str) else ""
    try:
        return (datetime.fromisoformat(text) if ":" in text else date.fromisoformat(text)) if text else None
    except ValueError:
        return None


def pair(value: Any) -> tuple[int | None, int | None]:
    """官方比分原值 "2:1" → (2, 1)；"取消"/""/非比分串 → (None, None)（解析不了就空，绝不改 0）。"""
    head, colon, tail = value.partition(":") if isinstance(value, str) else ("", "", "")
    return (int(head), int(tail)) if colon and head.isdigit() and tail.isdigit() else (None, None)


def split_numbers(game_num: str, raw: str) -> dict | None:
    """号码串 → numbers 解析列：大乐透（85）= 前区 5 + 后区 2；其余彩种按位数原序存（不重排不去重）。"""
    balls = raw.split()
    if not balls:
        return None
    return {"front": balls[:5], "back": balls[5:]} if game_num == "85" and len(balls) == 7 else {"digits": balls}


CAST: dict[str, Any] = {"p0": lambda value: pair(value)[0], "p1": lambda value: pair(value)[1], "d": dec, "c": clock,
                        "i": lambda value: value if isinstance(value, int) else None,
                        "n": lambda value: len(value) if isinstance(value, list) else None}


def build(payload: dict, spec: str) -> dict:
    """按 "官方键[:转换码]>规范列"（空格分隔）造行：无转换码 = 原值照抄，缺键一律 None（不补 0、不清洗）。"""
    row = {}
    for item in spec.split():
        source, _, col = item.partition(">")
        key, _, code = source.partition(":")
        row[col] = CAST[code](payload.get(key)) if code else payload.get(key)
    return row


def out(table: str, pk: dict, row: dict, notes: list[str] | None = None, **extra: Any) -> dict:
    """统一返回体 {table, pk, row, notes}（+ 表专属附加行，如 jczq_offer 的 match）。"""
    return {"table": table, "pk": pk, "row": row, "notes": list(notes or []), **extra}


def canonical_src_hash(payload: dict) -> str:
    """§5.0 官方序列化式的 sha256（小写十六进制）：幂等键只认本地复算，不采信采集机算的值。"""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
