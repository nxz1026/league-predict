"""P0-JCGATE1 封闭清单闸门：只决定"进不进模型"，不决定"进不进库"。

清单外联赛照旧入库当走势资料；模型侧一律拒绝（红线：宁可不插，不可插错）。
"""

# 用户 09-16 06:55 定死：足球 六大联赛 + 篮彩 NBA/CBA，共 8 个缩写
ALLOW_ABBR: frozenset[str] = frozenset({"英超", "西甲", "意甲", "德甲", "法甲", "中超", "NBA", "CBA"})

# 已实测确认的数字 league_id（fact.jc_match）：今天只有 西甲=62；
# 新观测到的联赛 id 由队长增补，工人不许自己加（猜测放行=插错）
ALLOW_IDS: frozenset[int] = frozenset({62})


def is_predictable(league_abbr: str | None, league_id: int | None = None) -> bool:
    """封闭清单判定：缩写精确命中 ALLOW_ABBR，或 id 命中 ALLOW_IDS ⇒ True；未知/空/异常一律 False。"""
    if not isinstance(league_abbr, str):
        return league_id in ALLOW_IDS
    if league_abbr.strip() in ALLOW_ABBR:
        return True
    return league_id in ALLOW_IDS


def partition(rows) -> tuple[list, list]:
    """rows = [{league_abbr, league_id}, ...] ⇒ (可预测, 不可预测)，保持原顺序。"""
    ok, blocked = [], []
    for row in rows:
        target = ok if is_predictable(row.get("league_abbr"), row.get("league_id")) else blocked
        target.append(row)
    return ok, blocked
