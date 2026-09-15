"""collector_pull 原子性回归锁：全程假连接（零 DB、不许 skip）——B2 提交早于归档 / B3 有外层事务就炸 / B4 失败件不拖累同批 / B5 main() 用裸 pg.connect。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ingest import collector_pull  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402


class _Ctx:
    """假游标／假事务合体：只把事件记进 ev，不做任何 IO；kind="tx" 的 exit 就是提交点。"""

    rowcount = 0

    def __init__(self, ev, kind):
        self.ev, self.kind = ev, kind

    def __enter__(self):
        self.ev.append((self.kind, "enter"))
        return self

    def __exit__(self, *exc):
        if self.kind == "tx":
            self.ev.append(("tx", "exit"))
        return False

    def execute(self, sql, params=None):
        self.ev.append(("sql", sql.split("ops.")[1].split()[0], params))


def _conn(ev, status=TransactionStatus.IDLE):
    """假连接：cursor()/transaction() 返回 _Ctx，pgconn.transaction_status 供 _load 的守卫读。"""
    return SimpleNamespace(pgconn=SimpleNamespace(transaction_status=status), transaction=lambda: _Ctx(ev, "tx"),
                           cursor=lambda: _Ctx(ev, "cur"), close=lambda: ev.append(("close",)))


def _prep(monkeypatch, tmp_path, *names, status=TransactionStatus.IDLE):
    """摆 incoming/h/jczq_offer/<name>.jsonl + .done；换掉 _archive（只记事件）与 load_file（含 boom 的抛异常）。"""
    ev: list = []

    def archive(data, marker, incoming, done, bad, clean):
        ev.append(("archive", data.name, clean))
        return str(done)

    def load(conn, data, topic):
        ev.append(("load", data.name))
        if "boom" in data.name: raise RuntimeError("boom: 模拟装载失败")  # noqa: E701
        return {"rows_in": 1, "rows_ups": 1, "rejected_n": 0, "rejected": []}
    monkeypatch.setattr(collector_pull, "_archive", archive)
    monkeypatch.setattr(collector_pull, "load_file", load)
    root = tmp_path / "incoming" / "h" / "jczq_offer"
    root.mkdir(parents=True)
    for name in names:
        (root / name).write_text('{"src_hash": "a"}\n', encoding="utf-8")
        (root / f"{name}.done").touch()
    return ev, _conn(ev, status), tmp_path / "incoming", tmp_path / "done", tmp_path / "bad"


def test_commit_exit_precedes_archive(monkeypatch, tmp_path):
    """提交（事务 exit）必须严格早于 _archive：归档不回滚，先动文件就是「原件进 done 而库回滚」的无痕丢数据。"""
    ev, conn, inc, done, bad = _prep(monkeypatch, tmp_path, "a.jsonl")
    assert [r["src_file"] for r in collector_pull.run(conn, inc, done, bad, commit=True)] == ["a.jsonl"]
    assert [e for e in ev if e[0] in ("tx", "load", "archive")] == [("tx", "enter"), ("load", "a.jsonl"),
                                                                   ("tx", "exit"), ("archive", "a.jsonl", True)]


def test_guard_refuses_outer_transaction(monkeypatch, tmp_path):
    """commit=True 且连接非 IDLE（外层已有事务）→ 立刻 RuntimeError 且不装载不归档；commit=False 不看该状态。"""
    ev, conn, inc, done, bad = _prep(monkeypatch, tmp_path, "a.jsonl", status=TransactionStatus.INTRANS)
    with pytest.raises(RuntimeError, match="SAVEPOINT"):
        collector_pull.run(conn, inc, done, bad, commit=True)
    assert not [e for e in ev if e[0] in ("load", "archive")]  # 守卫先炸：一个文件都没动
    assert collector_pull.run(conn, inc, done, bad, commit=False)[0]["rows_ups"] == 1  # False 走调用方边界


def test_failed_file_does_not_stop_batch(monkeypatch, tmp_path):
    """第 2 个文件装载抛异常：第 1、3 个照常各自提交 + 归档（顺序不断），失败件单独留痕 ok=false 并进 bad/。"""
    ev, conn, inc, done, bad = _prep(monkeypatch, tmp_path, "a.jsonl", "boom.jsonl", "c.jsonl")
    reports = collector_pull.run(conn, inc, done, bad, commit=True)
    assert [r["src_file"] for r in reports] == ["a.jsonl", "boom.jsonl", "c.jsonl"]
    assert [e[:2] for e in ev if e[0] in ("load", "archive")] == \
        [(f, n) for n in ("a.jsonl", "boom.jsonl", "c.jsonl") for f in ("load", "archive")]
    assert [e[1] for e in ev if e[0] == "archive" and e[2] is False] == ["boom.jsonl"]  # 失败件进 bad/
    bad_log = [e[2] for e in ev if e[0] == "sql" and e[1] == "ingest_log" and e[2][-1] is False]
    assert len(bad_log) == 1 and bad_log[0][1:4] == ("boom.jsonl", 0, 0) and "boom" in bad_log[0][4].obj[0]["reason"]


def test_main_opens_bare_connection(monkeypatch, tmp_path):
    """main() 必须用裸 pg.connect（外套 pg.write_conn 会让逐文件提交退化成 SAVEPOINT）——A1 的回归锁。"""
    monkeypatch.setattr(collector_pull.pg, "write_conn", lambda *a, **k: pytest.fail("main 不许再套外层事务"))
    monkeypatch.setattr(collector_pull.pg, "connect", lambda role: _conn([]) if role == "ing" else pytest.fail(role))
    argv = ["--incoming", str(tmp_path / "in"), "--done", str(tmp_path / "do"), "--bad", str(tmp_path / "ba")]
    assert collector_pull.main(argv) == 0  # 空 incoming：只验工厂函数选择与收尾 close
