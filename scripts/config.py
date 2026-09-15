"""源开关与配额策略的唯一配置层（README §2-D9）：收费/挂外部 key 的源默认关闭、功能保留，开关一律走 env。

落点说明：**不放在 `core/config.py`** —— 那里已有 v1 兼容再导出层（20 处 `from core.config import …` 在用），且验收器
league-accept.sh 把 `scripts/core/` 整段当冻结区（任何增删改判 FAIL）；故配置层作为 scripts/ 顶层模块 `config` 落地。
值只从 os.environ 读（repo/.env 已由 core.constants 在 import 时载入，真实 env 优先）；本模块不读文件、不联网、
不 import 任何 v1 模块（纯 stdlib）。

用法：`spend_allowed(source)` —— 关闭或付费未放行的源在**取 key/发请求之前**就抛 SourceDisabled，报错点名控制的 env
变量；`describe()` 给 --plan 打印当前全源策略（§9-33：开关状态必须看得见）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

TRUE_VALUES = frozenset({"1", "true", "on", "yes"})
FALSE_VALUES = frozenset({"0", "false", "off", "no"})


@dataclass(frozen=True)
class SourcePolicy:
    """一个源当前生效的策略：enabled 是否可用、daily_cap 每日上限、key_env key 变量名、paid 是否收费。"""

    source: str
    enabled: bool
    daily_cap: int
    key_env: str
    paid: bool


class SourceDisabled(RuntimeError):
    """该源当下不可花配额（关闭，或付费未放行）；why 里点名是哪个 env 变量说了算。"""

    def __init__(self, source: str, why: str) -> None:
        self.source, self.why = source, why
        super().__init__(f"{source} 不可用：{why}")


DEFAULTS: dict[str, SourcePolicy] = {  # 默认表写死在代码里，env 可覆盖（README §2-D9）
    "api_football": SourcePolicy("api_football", True, 100, "API_FOOTBALL_KEY", False),
    "football_data": SourcePolicy("football_data", True, 30, "FOOTBALL_DATA_API_KEY", False),
    "odds_api": SourcePolicy("odds_api", False, 0, "NBA_API_KEY", True)}  # P0-MARKET2 外部盘口：功能在、默认关


def flag(name: str, default: bool = False) -> bool:
    """读 LEAGUE_<NAME>：1/0、true/false、on/off、yes/no（大小写不敏感、去空白）；空值＝未设；其余 ValueError。"""
    raw = os.environ.get(f"LEAGUE_{name.upper()}", "").strip().lower()
    if not raw:
        return default
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise ValueError(f"LEAGUE_{name.upper()}={raw!r} 无法识别：只认 1/0、true/false、on/off、yes/no")


def source_policy(source: str) -> SourcePolicy:
    """默认表 + env 覆盖：LEAGUE_SOURCE_<SOURCE>=on|off、LEAGUE_QUOTA_CAP_<SOURCE>=非负整数（非法即 ValueError）。"""
    if source not in DEFAULTS:
        raise ValueError(f"unknown source {source!r}; expected {sorted(DEFAULTS)}")
    base = DEFAULTS[source]
    raw_cap = os.environ.get(f"LEAGUE_QUOTA_CAP_{source.upper()}", "").strip()
    if raw_cap and not raw_cap.isdigit():
        raise ValueError(f"LEAGUE_QUOTA_CAP_{source.upper()}={raw_cap!r} 必须是非负整数")
    return SourcePolicy(base.source, flag(f"SOURCE_{source.upper()}", base.enabled),
                        int(raw_cap) if raw_cap else base.daily_cap, base.key_env, base.paid)


def spend_allowed(source: str) -> None:
    """关闭或付费未放行 ⇒ 抛 SourceDisabled（why 点名 env 变量）；可用则静默返回 None。"""
    policy = source_policy(source)
    if not policy.enabled:
        raise SourceDisabled(source, f"已被 LEAGUE_SOURCE_{source.upper()}=off 关闭"
                                     f"（打开：LEAGUE_SOURCE_{source.upper()}=on）")
    if policy.paid and not flag("ALLOW_PAID"):
        raise SourceDisabled(source, "付费源需单次放行（LEAGUE_ALLOW_PAID=on 或 run_backfill --allow-paid）")


def allow_paid_once() -> None:
    """--allow-paid：只放行本次进程（写进程内 env，不落 .env、不影响并发进程）。"""
    os.environ["LEAGUE_ALLOW_PAID"] = "on"


def describe() -> list[dict]:
    """全源当前生效策略（供 --plan 打印）：spend 是否可花、why 关闭原因（点名 env 变量）。"""
    rows = []
    for source in DEFAULTS:
        policy = source_policy(source)
        try:
            spend_allowed(source)
            why = ""
        except SourceDisabled as exc:
            why = exc.why
        rows.append({"source": source, "enabled": policy.enabled, "daily_cap": policy.daily_cap,
                     "key_env": policy.key_env, "paid": policy.paid, "spend": not why, "why": why})
    return rows
