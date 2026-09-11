"""M2 存储层测试：PredictionStore 语义（验收点 C 结构性 / D 容错）。

覆盖：
- 扫描/解析：目录缺失、空目录、坏 JSON → 跳过不抛穿；
- 每联赛最新（契约 §3.3）：按 generated_at 取最大，同小时覆盖坑；
- data_window 紧凑格式解析、covers_date 边界；
- results 读取、calibration 状态读取；
- 输出 UTC→BJT 换算只在出口（store 内为 naive/aware 混合安全比较）。
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import web.services.store as store_mod  # noqa: E402


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """临时引擎产物目录，monkeypatch 后重建模块单例指向它。"""
    d = tmp_path / "scripts"
    monkeypatch.setattr(store_mod, "OUTPUT_DIR", d)
    # 重新绑定模块级依赖，避免真实 scripts/ 干扰。
    monkeypatch.setattr(store_mod, "iter_prediction_files", store_mod.iter_prediction_files)
    return d


def _pred_doc(league: str, generated_at: str, data_window="20260724-20260726",
              predictions=None, status="ok", **extra):
    base = {
        "generated_at": generated_at,
        "data_window": data_window,
        "status": status,
        "league": league,
        "predictions": predictions if predictions is not None else [],
    }
    base.update(extra)
    return base


# --- 扫描/解析 ------------------------------------------------------------

def test_missing_predictions_dir_ok(data_dir):
    docs = store_mod.load_prediction_docs()
    assert docs == []


def test_empty_predictions_dir_ok(data_dir):
    (data_dir / "predictions").mkdir(parents=True)
    assert store_mod.load_prediction_docs() == []


def test_bad_json_skipped_with_warning(data_dir, caplog):
    pdir = data_dir / "predictions"
    pdir.mkdir(parents=True)
    (pdir / "prediction_2026-07-21_10.json").write_text("{bad json", encoding="utf-8")
    (pdir / "prediction_2026-07-21_11.json").write_text("[]", encoding="utf-8")
    (pdir / "prediction_2026-07-21_12.json").write_text("{}", encoding="utf-8")
    import logging
    with caplog.at_level(logging.WARNING, logger="web.store"):
        docs = store_mod.load_prediction_docs()
    assert docs == []
    assert any("坏 JSON" in r.message for r in caplog.records)


def test_non_dict_json_skipped(data_dir, caplog):
    pdir = data_dir / "predictions"
    pdir.mkdir(parents=True)
    (pdir / "prediction_2026-07-21_10.json").write_text("[1,2]", encoding="utf-8")
    import logging
    with caplog.at_level(logging.WARNING, logger="web.store"):
        docs = store_mod.load_prediction_docs()
    assert docs == []


# --- 每联赛最新（§3.3）----------------------------------------------------

def test_latest_by_league_uses_generated_at_max(data_dir):
    pdir = data_dir / "predictions"
    _write_json(pdir / "prediction_2026-07-21_10.json",
                _pred_doc("epl", "2026-07-21T10:00:00+08:00", predictions=[{"match": "a"}]))
    _write_json(pdir / "prediction_2026-07-21_13.json",
                _pred_doc("epl", "2026-07-21T13:00:00+08:00", predictions=[{"match": "b"}]))
    latest = store_mod.latest_by_league()
    assert set(latest) == {"epl"}
    assert latest["epl"]["data"]["predictions"][0]["match"] == "b"


def test_latest_tolerates_utc_suffix_and_naive(data_dir):
    """generated_at 可带 +00:00（旧版产物）或全 naive（BJT），比较不炸。"""
    pdir = data_dir / "predictions"
    _write_json(pdir / "prediction_2026-07-21_10.json",
                _pred_doc("epl", "2026-07-21T10:00:00+00:00", predictions=[{"match": "u"}]))
    _write_json(pdir / "prediction_2026-07-21_12.json",
                _pred_doc("epl", "2026-07-21T12:00:00+08:00", predictions=[{"match": "bjt"}]))
    latest = store_mod.latest_by_league()
    assert latest["epl"]["data"]["predictions"][0]["match"] == "bjt"


def test_latest_missing_generated_at_falls_back_mtime(data_dir):
    pdir = data_dir / "predictions"
    f1 = pdir / "prediction_2026-07-21_10.json"
    f2 = pdir / "prediction_2026-07-21_11.json"
    _write_json(f1, _pred_doc("epl", None, predictions=[{"match": "old"}]))
    _write_json(f2, _pred_doc("epl", None, predictions=[{"match": "new"}]))
    # 强制 mtime 顺序可辨
    import os
    os.utime(f1, (1_000_000, 1_000_000))
    os.utime(f2, (2_000_000, 2_000_000))
    latest = store_mod.latest_by_league()
    assert latest["epl"]["data"]["predictions"][0]["match"] == "new"


def test_multi_league_grouped_and_filtered(data_dir):
    pdir = data_dir / "predictions"
    _write_json(pdir / "prediction_2026-07-21_10.json",
                _pred_doc("epl", "2026-07-21T10:00:00+08:00", predictions=[{"match": "e"}]))
    _write_json(pdir / "prediction_2026-07-21_11.json",
                _pred_doc("laliga", "2026-07-21T11:00:00+08:00", predictions=[{"match": "l"}]))
    latest = store_mod.latest_by_league(["epl"])
    assert set(latest) == {"epl"}


# --- data_window 覆盖 ------------------------------------------------------

def test_covers_date_inclusive(data_dir):
    p = _pred_doc("epl", "2026-07-21T10:00:00+08:00", data_window="20260724-20260726")
    assert store_mod.covers_date(p, date(2026, 7, 24))
    assert store_mod.covers_date(p, date(2026, 7, 25))
    assert store_mod.covers_date(p, date(2026, 7, 26))
    assert not store_mod.covers_date(p, date(2026, 7, 27))
    assert not store_mod.covers_date(p, date(2026, 7, 23))


def test_covers_date_bad_window_returns_false(data_dir):
    for bad in ("abc", "20260724", "20260724-", "20260724-xxxx", "20260230-20260301"):
        assert store_mod.covers_date(_pred_doc("epl", "x", data_window=bad), date(2026, 7, 25)) is False


# --- results / calibration -------------------------------------------------

def test_results_for_date_missing_dir_empty(data_dir):
    assert store_mod.results_for_date("2026-07-21") == []


def test_results_read_matches(data_dir):
    _write_json(data_dir / "results" / "result_2026-07-21.json",
                {"date": "2026-07-21", "matches": [{"id": "m1", "home_score": 1}]})
    matches = store_mod.results_for_date("2026-07-21")
    assert [m["id"] for m in matches] == ["m1"]


def test_results_bad_json_empty(data_dir):
    rdir = data_dir / "results"
    rdir.mkdir(parents=True)
    (rdir / "result_2026-07-21.json").write_text("{oops", encoding="utf-8")
    assert store_mod.results_for_date("2026-07-21") == []


def test_calibration_states_reads_hidden_files(data_dir):
    _write_json(data_dir / "references" / ".calibration_state_epl.json",
                {"total_matches": 5, "home_win_rate": 0.4})
    states = store_mod.calibration_states()
    assert states["epl"]["total_matches"] == 5


def test_calibration_states_missing_dir_empty(data_dir):
    assert store_mod.calibration_states() == {}


# --- bjt_today -------------------------------------------------------------

def test_bjt_today_is_aware_date(data_dir):
    d = store_mod.bjt_today()
    assert isinstance(d, date)
    assert d == datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date()