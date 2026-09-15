"""Dixon-Coles 攻防强度拟合：λ_home = γ·atk_home·def_away、λ_away = atk_away·def_home（纯算术，零 DB/io）。

口径（与队长独立实现逐值钉死，勿改；`def_` 带下划线，def 是关键字）：
  · 约束 = 攻击参数几何平均 ≡ 1（Π atk = 1）⇒ def_ 与 γ 无自由度，γ 由数据一次定死、不进迭代：
    γ = Σ主队进球 / Σ客队进球（收敛点上 = Σλ主/Σλ客；进迭代会在"全是主场进球"这类退化输入上发散）
  · 固定点（γ 乘在"主队分母的主场项"与"客队分母的客场项"上，放错位置在对称数据上看不出来）：
    atk_t = GF_t / (γ·Σ_{t主}def_opp + Σ_{t客}def_opp)；def_t = GA_t / (Σ_{t主}atk_opp + γ·Σ_{t客}atk_opp)
  · 停机 max|Δatk| + max|Δdef| < TOL(=1e-15，比工单的 1e-12 严，理据见报告 §偏差) + 上限 MAX_ITER 轮，
    超限抛 ConvergenceError；Σ客队进球 == 0 ⇒ γ=1.0（黄金 1）；GF 或 GA 为 0 的队 ⇒ ValueError 带队名（不兜底）
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

MAX_ITER = 5000
TOL = 1e-15
Match = tuple[str, str, float, float]


class ConvergenceError(RuntimeError):
    """固定点迭代超限：宁可炸，也不返回未收敛的强度。"""


@dataclass(frozen=True)
class LeagueFit:
    """一次拟合：atk/def_ 为"队名→强度"（`def_` 带下划线，def 是关键字），gamma 即主场优势。"""

    atk: dict[str, float]
    def_: dict[str, float]
    gamma: float
    n_matches: int


def _rows(matches: Sequence[Match], teams: Sequence[str] | None) -> list[Match]:
    """入参校验：空集 / 非 str 或未知队名 / 主客同队 / 非数值或负进球一律 ValueError，消息里点名。"""
    known = None if teams is None else set(teams)
    rows: list[Match] = []
    for home, away, gh, ga in matches:
        for name in (home, away):
            if not isinstance(name, str) or (known is not None and name not in known):
                raise ValueError(f"队名非法 {name!r}：须为 str 且在 teams={sorted(known) if known else '未限定'} 内")
        if home == away:
            raise ValueError(f"主客同队 {home!r}：一场比赛必须 2 支球队参与")
        for g in (gh, ga):
            if isinstance(g, bool) or not isinstance(g, (int, float)) or not math.isfinite(g) or g < 0:
                raise ValueError(f"{home} vs {away} 进球数非法：{g!r}（须有限且非负数值）")
        rows.append((home, away, float(gh), float(ga)))
    if not rows:
        raise ValueError("matches 为空：没有比赛就没有强度可拟合")
    return rows


def _terms(rows: list[Match], names: Sequence[str]) -> tuple:
    """一趟出 GF / GA / 两支分母的"加权对手表"（atk 分母主场项带 γ、def 分母客场项带 γ）+ γ；零进球队拒收。"""
    gf, ga = dict.fromkeys(names, 0.0), dict.fromkeys(names, 0.0)
    atk_terms: dict[str, list[tuple[str, float]]] = {t: [] for t in names}
    def_terms: dict[str, list[tuple[str, float]]] = {t: [] for t in names}
    away_goals = math.fsum(row[3] for row in rows)
    gamma = 1.0 if away_goals == 0.0 else math.fsum(row[2] for row in rows) / away_goals
    for home, away, gh, ga_ in rows:
        gf[home] += gh
        ga[home] += ga_
        gf[away] += ga_
        ga[away] += gh
        atk_terms[home].append((away, gamma))
        atk_terms[away].append((home, 1.0))
        def_terms[home].append((away, 1.0))
        def_terms[away].append((home, gamma))
    for team in names:
        if gf[team] <= 0.0 or ga[team] <= 0.0:
            raise ValueError(f"球队 {team!r} 的 GF={gf[team]} / GA={ga[team]} 含 0：强度不可辨识（不许默认 1.0）")
    return gf, ga, atk_terms, def_terms, gamma


def fit_attack_defense(matches: Sequence[Match], teams: Sequence[str] | None = None) -> LeagueFit:
    """交替固定点拟合攻防强度；超限抛 ConvergenceError，强度不可辨识抛 ValueError。"""
    rows = _rows(matches, teams)
    names = sorted({name for row in rows for name in row[:2]})
    gf, ga, atk_terms, def_terms, gamma = _terms(rows, names)
    atk, def_ = dict.fromkeys(names, 1.0), dict.fromkeys(names, 1.0)
    for _ in range(MAX_ITER):
        new_atk = {t: gf[t] / sum(w * def_[o] for o, w in atk_terms[t]) for t in names}
        shift = math.exp(math.fsum(math.log(v) for v in new_atk.values()) / len(names))
        new_atk = {t: v / shift for t, v in new_atk.items()}
        new_def = {t: ga[t] / sum(w * new_atk[o] for o, w in def_terms[t]) for t in names}
        delta = max(abs(new_atk[t] - atk[t]) for t in names) + max(abs(new_def[t] - def_[t]) for t in names)
        atk, def_ = new_atk, new_def
        if delta < TOL:
            return LeagueFit(atk=atk, def_=def_, gamma=gamma, n_matches=len(rows))
    raise ConvergenceError(f"{MAX_ITER} 轮未达 max|Δatk|+max|Δdef| < {TOL}：{len(rows)} 场 / {len(names)} 队")


def match_lambdas(fit: LeagueFit, home: str, away: str) -> tuple[float, float]:
    """一场比赛的 (λ_home, λ_away)；未知队名 ValueError（不外推、不给默认强度）。"""
    unknown = [name for name in (home, away) if name not in fit.atk]
    if unknown:
        raise ValueError(f"未知队名 {unknown[0]!r}：不在本次拟合的 {len(fit.atk)} 支球队里")
    return fit.gamma * fit.atk[home] * fit.def_[away], fit.atk[away] * fit.def_[home]
