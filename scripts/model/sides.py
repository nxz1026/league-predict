"""walk 的零件（零 DB/零网络）：λ（含未见队联盟平均先验）、jqc 两侧 4 档、commit 短哈希。"""

from __future__ import annotations

import subprocess

from derive.registry import derive_play

PRIOR = 1.0  # 未见队（当季升班马）的联盟平均先验：atk = def = PRIOR
_JQC_MERGE = {"0": "0", "1": "1", "2": "2", "3": "3+", "4": "3+", "5": "3+", "6": "3+", "7+": "3+"}


def lambdas(fit, home: str, away: str) -> tuple[float, float, str, str]:
    """(λ_h, λ_a, 主队来源, 客队来源)：未见队回落联盟平均先验；γ 只乘主队侧（与 fit 口径一致）。

    未见队的已知偏差：升班马整体弱于联盟平均 ⇒ 其主场 λ 被系统性高估，回测须按 fallback/fit 分组评估。
    """
    seen_h, seen_a = home in fit.atk, away in fit.atk
    atk_h, def_h = (fit.atk[home], fit.def_[home]) if seen_h else (PRIOR, PRIOR)
    atk_a, def_a = (fit.atk[away], fit.def_[away]) if seen_a else (PRIOR, PRIOR)
    return (fit.gamma * atk_h * def_a, atk_a * def_h,
            "fit" if seen_h else "league_avg_prior", "fit" if seen_a else "league_avg_prior")


def jqc_sides(grid: list[list[float]]) -> dict[str, float]:
    """jqc 两侧共 8 个 option_code（h:0|h:1|h:2|h:3+|a:0|…）：goals4 的 8 档归并成 3+（≥3 全并）。

    映射表硬编码 8 档 ⇒ goals4 若改档位这里直接 KeyError（宁可炸，也不静默丢概率）；每侧四档和 == 该侧边际。
    """
    out: dict[str, float] = {}
    for side, probs in zip(("h", "a"), derive_play("jqc", grid)):
        merged: dict[str, float] = {"0": 0.0, "1": 0.0, "2": 0.0, "3+": 0.0}
        for code, p in probs.items():
            merged[_JQC_MERGE[code]] += p
        out |= {f"{side}:{code}": p for code, p in merged.items()}
    return out


def commit_sha() -> str | None:
    """当前 git 短哈希（供 pred_run.commit 留痕）；不在 git 工作区/无 git ⇒ None，绝不因此失败。"""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None
