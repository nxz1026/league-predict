"""L3a 玩法注册表用例：5 个已实现键的分派形状、未实现键点名拒绝、hhad 缺线拒绝（纯算术零依赖）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from derive import goals4, scores31, totals  # noqa: E402
from derive.grid import dc_grid  # noqa: E402
from derive.handicap import probs  # noqa: E402
from derive.registry import PLAYS, derive_play  # noqa: E402


@pytest.fixture(scope="module")
def grid9():
    return dc_grid(1.5, 0.8, 0.2, 8)


def test_only_implemented_plays_registered():
    """注册表恰好这 5 个键：不许塞 haf 之类占位实现或均匀分布假兜底。"""
    assert set(PLAYS) == {"had", "hhad", "crs", "ttg", "jqc"}
    assert "haf" not in PLAYS
    assert all(callable(fn) for fn in PLAYS.values())


def test_dispatch_shapes(grid9):
    """形状 + 概率归一：had/hhad 3 键、crs 31 键、ttg 8 键、jqc 2 个 8 档两侧各自 Σ=1。"""
    for tri in (derive_play("had", grid9), derive_play("hhad", grid9, -1)):
        assert set(tri) == {"home", "draw", "away"}
        assert sum(tri.values()) == pytest.approx(1.0, abs=1e-12)
    crs, ttg = derive_play("crs", grid9), derive_play("ttg", grid9)
    assert len(crs) == 31 and sum(crs.values()) == pytest.approx(1.0, abs=1e-6)
    assert len(ttg) == 8 and sum(ttg.values()) == pytest.approx(1.0, abs=1e-6)
    home, away = derive_play("jqc", grid9)
    assert len(home) == len(away) == 8
    assert all(sum(side.values()) == pytest.approx(1.0, abs=1e-6) for side in (home, away))


def test_had_is_line_zero_and_hhad_threads_line(grid9):
    """had 固定 0 线三向；hhad 必须把 line 真透传下去（不能被吞成 0）。"""
    assert derive_play("had", grid9) == pytest.approx(probs(grid9, 0), abs=1e-12)
    assert derive_play("hhad", grid9, -2) == pytest.approx(probs(grid9, -2), abs=1e-12)
    assert abs(derive_play("hhad", grid9, -2)["home"] - derive_play("hhad", grid9, 0)["home"]) > 0.1


def test_passthrough_matches_source_modules(grid9):
    """crs 键空间 == scores31.KEYS（31 项）；ttg/jqc 与源模块逐项一致（含两端 8 档）。"""
    assert set(derive_play("crs", grid9)) == set(scores31.KEYS) and len(scores31.KEYS) == 31
    assert derive_play("ttg", grid9) == pytest.approx(totals.buckets(grid9), abs=1e-12)
    got_home, got_away = derive_play("jqc", grid9)
    want_home, want_away = goals4.team_buckets(grid9)
    assert got_home == pytest.approx(want_home, abs=1e-12)
    assert got_away == pytest.approx(want_away, abs=1e-12)


def test_haf_and_unknown_rejected_with_pointer():
    """haf（P1 半全场，待 FD halfTime 回填）与未知键 → KeyError，文案点名未实现 + 禁 0.0 占位。"""
    for bad in ("haf", "unknown", "had2"):
        with pytest.raises(KeyError) as ei:
            derive_play(bad, [[0.5, 0.5], [0.5, 0.5]])
        msg = str(ei.value)
        assert "未实现" in msg and "0.0" in msg and bad in msg


def test_hhad_requires_int_line(grid9):
    """hhad 缺 line → TypeError；给了 float 线也拒（继承 handicap 的 int 硬约束）。"""
    with pytest.raises(TypeError):
        derive_play("hhad", grid9)
    with pytest.raises(TypeError):
        derive_play("hhad", grid9, 1.0)
