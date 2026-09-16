"""契约 v1.4 盘口全历史解析器硬数测试（零 DB、零网络；夹具 = tests/fixtures/odds_history/**，
真探针回传样，一个字节不许改；硬数 C1~C8 见 P0-COLLECT3b 工单，不许改成"看着像"的值）。"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from store import parse_odds_hist as poh  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "odds_history"
FIN = "finished_卡塔尔亚vs韩国亚__2041482.jsonl"
ONS = "onsale_柏太阳神__2041495.jsonl"


def env_of(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


RS = poh.parse_env(env_of(FIN), FIN) + poh.parse_env(env_of(ONS), ONS)


def sel(rs, play=None, src=None):
    return [r for r in rs if (play is None or r["play_type"] == play)
            and (src is None or r["src_file"] == src)]


def test_c1_c2_totals_and_split():
    fin, ons = sel(RS, src=FIN), sel(RS, src=ONS)
    assert len(RS) == 34
    assert len(fin) == 29
    assert len(ons) == 5
    exp_all = {"had": 7, "hhad": 9, "crs": 6, "ttg": 6, "haf": 6}
    exp_fin = {"had": 6, "hhad": 8, "crs": 5, "ttg": 5, "haf": 5}
    exp_ons = {"had": 1, "hhad": 1, "crs": 1, "ttg": 1, "haf": 1}
    for s, exp in ((RS, exp_all), (fin, exp_fin), (ons, exp_ons)):
        assert {p: len(sel(s, p)) for p in exp} == exp
    assert all(r["src_hash"] == env_of(FIN)["src_hash"] for r in fin)
    assert all(r["src_hash"] == env_of(ONS)["src_hash"] for r in ons)


def test_c3_seq_no_oldest_zero():
    assert {r["seq_no"] for r in sel(RS, "had", FIN)} == {0, 1, 2, 3, 4, 5}
    assert {r["seq_no"] for r in sel(RS, "hhad", FIN)} == {0, 1, 2, 3, 4, 5, 6, 7}
    for p in ("crs", "ttg", "haf"):
        assert {r["seq_no"] for r in sel(RS, p, FIN)} == {0, 1, 2, 3, 4}
    assert {r["seq_no"] for r in sel(RS, src=ONS)} == {0}


def test_c4_timestamps_are_beijing_wall_clock():
    fin = sel(RS, "had", FIN)
    first = next(r for r in fin if r["seq_no"] == 0)
    last = next(r for r in fin if r["seq_no"] == 5)
    assert first["update_ts"] == datetime(2026, 9, 15, 1, 39, 39, tzinfo=timezone.utc)
    assert last["update_ts"] == datetime(2026, 9, 15, 10, 9, 0, tzinfo=timezone.utc)
    for r in (first, last):
        assert r["update_ts"].utcoffset() == timedelta(0)


def test_c5_first_and_close_flags():
    assert sum(r["is_first"] for r in RS) == 10
    assert sum(r["is_close"] for r in RS) == 0


def test_c6_goal_lines_and_odds_keys():
    with_line = [r for r in RS if r["goal_line"] is not None]
    assert len(with_line) == 9
    assert all(r["play_type"] == "hhad" for r in with_line)
    assert all(isinstance(r["goal_line_value"], float) for r in with_line)
    for r in RS:
        assert not ({"updateDate", "updateTime", "goalLine"} & r["odds"].keys())
    for p in ("had", "hhad"):
        assert all(set(r["odds"]) == {"h", "hf", "d", "df", "a", "af"} for r in sel(RS, p))


def test_c7_league_id():
    assert all(r["league_id"] == 83 for r in sel(RS, src=FIN))
    assert all(r["league_id"] == 1 for r in sel(RS, src=ONS))
    payload = dict(env_of(FIN)["payload"], leagueId="abc")
    rows = poh.parse_history(payload)
    assert rows and all(r["league_id"] is None for r in rows)


def test_c8_never_raises():
    assert poh.parse_history({}) == []
    base = env_of(FIN)["payload"]
    no_had = {k: v for k, v in base.items() if k != "hadList"}
    assert len(poh.parse_history(no_had)) == 23
    assert len(poh.parse_history(dict(base, hadList=[]))) == 23
    rec = dict(base["hadList"][0])
    del rec["updateTime"]
    assert len(poh.parse_history(dict(base, hadList=[rec] + base["hadList"][1:]))) == 28
    assert poh.parse_env({}) == []
    assert poh.parse_env({"payload": None}) == []
