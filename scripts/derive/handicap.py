"""竞彩让球胜平负（hhad）：让球线加在主队身上，"主-1" 即 line=-1（与官方口径一致）。"""

from __future__ import annotations

from derive.grid import renormalize

KEYS = ("home", "draw", "away")


def _check_line(line: int) -> None:
    """让球线必须恰为 int：float（哪怕 1.0）与 bool（True 会被当 1 混入）一律拒收。"""
    if isinstance(line, bool) or not isinstance(line, int):
        raise TypeError(f"让球线必须为 int，得到 {type(line).__name__}: {line!r}")


def probs(grid: list[list[float]], line: int) -> dict[str, float]:
    """判定 (h + line) 与 a：> 主胜、== 平、< 客胜；矩阵先 renormalize ⇒ 三向和恒 == 1。

    越界线（如 ±10）不报错：9×9 网格翻不动，自然落到全主胜/全客胜退化边界。
    """
    _check_line(line)
    norm = renormalize(grid)
    out: dict[str, float] = dict.fromkeys(KEYS, 0.0)
    for h, row in enumerate(norm):
        for a, p in enumerate(row):
            if h + line > a:
                out["home"] += p
            elif h + line == a:
                out["draw"] += p
            else:
                out["away"] += p
    return out
