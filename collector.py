#!/usr/bin/env python3
"""国内采集机：取官方 JSON → 落 JSONL → 推远端（契约 v1.1，2026-09-15 冻结）。

定位：独立小工具，只做取数/落盘/推送。不连 DB、不解析 HTML、不装重型依赖。
仅 stdlib（urllib/json/hashlib/pathlib/subprocess/tarfile/argparse）。

契约 v1.1（单一真源：doc/国内采集机实施文档-v1.md §5）：
- 通用行外壳：{"kind","topic","snap_ts","fetched_at","endpoint","http_status",
  "collector_host","payload","src_hash"}
- snap_ts = 请求发出时刻（UTC 带 Z），同批同值；官方更新时间留 payload 原样
- kind="error"：errorCode != "0" 或 success != true 时必须产行（失败响应无 value 键）
- payload 官方键名原样，不许改名/清洗/判奖
- src_hash = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
  separators=(",",":")).encode("utf-8")).hexdigest()

用法：
  python collector.py --probe            # 探针模式（v1 遗留，契约冻结后仅复探用）
  python collector.py --collect <topic>  # 采集指定 topic 落 JSONL
  python collector.py --collect-all      # 采集全部 7 topic
  python collector.py --push             # 打包 out/ → scp+sudo 推 oracle + .done
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CN_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

UA = CONFIG["ua"]
REFERER = CONFIG["referer"]
QPS = float(CONFIG["qps_interval"])
RETRIES = int(CONFIG["retries"])
BACKOFF = [float(x) for x in CONFIG["backoff"]]
HEAD_BYTES = int(CONFIG["probe_head_bytes"])
HOST = CONFIG["collector_host"]
SSH_ALIAS = CONFIG["push"]["ssh_alias"]
REMOTE_ROOT = CONFIG["push"]["remote_root"]
CONTRACT = "v1.1"

# 玩法块 → 官方 poolCode（§5.1 实测）
_POOL_CODE = {"had": "HAD", "hhad": "HHAD", "crs": "CRS", "ttg": "TTG", "hafu": "HAFU"}
_OFFER_BLOCKS = ("had", "hhad", "crs", "ttg", "hafu")
_ISSUE_GAMES = ("sfc", "jqc", "bqc")


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fname_ts() -> str:
    """文件名用 UTC 时间戳（冒号换 -，Windows 兼容）：2026-09-15T13-30Z。"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%MZ")


def src_hash(payload: dict) -> str:
    """官方式子（§5.0）：sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",",":")))。"""
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _req(url: str, ua: str, referer: str, timeout: int = 20) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Referer": referer,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return resp.status, resp.headers.get("Content-Type", ""), body


def fetch(url: str) -> dict:
    """带重试的 GET（指数退避 5/15/45s，QPS 节流）。返回探针记录。"""
    rec = {"url": url, "fetched_at": now_utc()}
    last_err = ""
    for attempt in range(RETRIES):
        try:
            time.sleep(QPS)
            status, ctype, body = _req(url, UA, REFERER)
            rec.update({"http_status": status, "content_type": ctype,
                        "body": body, "attempts": attempt + 1})
            return rec
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    rec.update({"http_status": 0, "content_type": "", "body": b"", "error": last_err,
                "attempts": RETRIES})
    return rec


def _ok(j: dict) -> bool:
    """成功判据（§5.0）：errorCode == "0"（字符串）且 success == true。"""
    return str(j.get("errorCode")) == "0" and j.get("success") is True


def _envelope(topic: str, url: str, rec: dict, snap_ts: str, payload: dict) -> dict:
    return {"kind": "line", "topic": topic, "snap_ts": snap_ts, "fetched_at": now_utc(),
            "endpoint": url, "http_status": rec.get("http_status", 0),
            "collector_host": HOST, "payload": payload, "src_hash": src_hash(payload)}


def _error_row(topic: str, url: str, rec: dict, snap_ts: str, body: bytes) -> dict:
    """失败行（§5.0）：errorCode != "0" 或 success != true。payload 原样放四键（失败响应无 value）。"""
    try:
        j = json.loads(body.decode("utf-8", errors="replace"))
        payload = {k: j.get(k) for k in ("errorCode", "errorMessage", "emptyFlag", "dataFrom")}
    except (ValueError, UnicodeDecodeError):
        payload = {"errorCode": "", "errorMessage": "non-json body", "emptyFlag": None, "dataFrom": None}
    return {"kind": "error", "topic": topic, "snap_ts": snap_ts, "fetched_at": now_utc(),
            "endpoint": url, "http_status": rec.get("http_status", 0),
            "collector_host": HOST, "payload": payload, "src_hash": src_hash(payload)}


def _offer_payload(sub: dict, block: str) -> dict:
    """§5.1：一场 × 一个玩法。官方键原样，options 整块 + oddsHistory 原样。"""
    return {
        "matchId": sub.get("matchId"), "matchNum": sub.get("matchNum"),
        "matchNumStr": sub.get("matchNumStr"), "matchNumDate": sub.get("matchNumDate"),
        "businessDate": sub.get("businessDate"), "matchDate": sub.get("matchDate"),
        "matchTime": sub.get("matchTime"), "leagueId": sub.get("leagueId"),
        "leagueAllName": sub.get("leagueAllName"), "leagueAbbName": sub.get("leagueAbbName"),
        "homeTeamId": sub.get("homeTeamId"), "awayTeamId": sub.get("awayTeamId"),
        "homeTeamAllName": sub.get("homeTeamAllName"), "awayTeamAllName": sub.get("awayTeamAllName"),
        "homeTeamAbbName": sub.get("homeTeamAbbName"), "awayTeamAbbName": sub.get("awayTeamAbbName"),
        "homeRank": sub.get("homeRank"), "awayRank": sub.get("awayRank"),
        "matchStatus": sub.get("matchStatus"), "sellStatus": sub.get("sellStatus"),
        "bettingSingle": sub.get("bettingSingle"), "bettingAllUp": sub.get("bettingAllUp"),
        "poolCode": _POOL_CODE[block], "block": block,
        "options": sub.get(block) or {}, "oddsHistory": sub.get("oddsList") or [],
    }


def parse_jczq_offer(url: str, rec: dict, snap_ts: str) -> list:
    j = json.loads(rec["body"].decode("utf-8", errors="replace"))
    if not _ok(j):
        return [_error_row("jczq_offer", url, rec, snap_ts, rec["body"])]
    rows = []
    for mi in (j.get("value") or {}).get("matchInfoList") or []:
        for sub in mi.get("subMatchList") or []:
            for block in _OFFER_BLOCKS:
                rows.append(_envelope("jczq_offer", url, rec, snap_ts, _offer_payload(sub, block)))
    return rows


def parse_jczq_result(url: str, rec: dict, snap_ts: str) -> list:
    j = json.loads(rec["body"].decode("utf-8", errors="replace"))
    if not _ok(j):
        return [_error_row("jczq_result", url, rec, snap_ts, rec["body"])]
    return [_envelope("jczq_result", url, rec, snap_ts, m)
            for m in (j.get("value") or {}).get("matchResult") or []]


def parse_jc_issue(url: str, rec: dict, snap_ts: str) -> list:
    j = json.loads(rec["body"].decode("utf-8", errors="replace"))
    if not _ok(j):
        return [_error_row("jc_issue", url, rec, snap_ts, rec["body"])]
    value = j.get("value") or {}
    dm = value.get("drawMatch") or {}
    payload = {
        "lotteryGameNum": dm.get("lotteryGameNum"), "lotteryGameName": dm.get("lotteryGameName"),
        "lotteryDrawNum": dm.get("lotteryDrawNum"),
        "lotterySaleBeginTime": dm.get("lotterySaleBeginTime"),
        "lotterySaleEndTime": dm.get("lotterySaleEndTime"),
        "lotteryDrawTime": dm.get("lotteryDrawTime"),
        "drawNumList": value.get("drawNumList") or [],
        "matchList": dm.get("matchList") or [],
    }
    return [_envelope("jc_issue", url, rec, snap_ts, payload)]


def parse_jc_issue_result(url: str, rec: dict, snap_ts: str) -> list:
    j = json.loads(rec["body"].decode("utf-8", errors="replace"))
    if not _ok(j):
        return [_error_row("jc_issue_result", url, rec, snap_ts, rec["body"])]
    value = j.get("value") or {}
    rows = []
    for key in _ISSUE_GAMES:
        detail = value.get(f"{key}Detail")
        if detail:
            payload = dict(detail)
            payload["gameKey"] = key
            rows.append(_envelope("jc_issue_result", url, rec, snap_ts, payload))
    return rows


def parse_jclq_offer(url: str, rec: dict, snap_ts: str) -> list:
    """§5.5：v1.1 不冻结。空（仅 vtoolsConfig）→ 无行（.empty）；首次非空 → 按 §5.1 结构产行 + 状态标记 + 回传探针包。"""
    j = json.loads(rec["body"].decode("utf-8", errors="replace"))
    if not _ok(j):
        return [_error_row("jclq_offer", url, rec, snap_ts, rec["body"])]
    value = j.get("value") or {}
    if not value.get("matchInfoList"):
        return []
    rows = []
    for mi in value.get("matchInfoList") or []:
        for sub in mi.get("subMatchList") or []:
            for block in _OFFER_BLOCKS:
                rows.append(_envelope("jclq_offer", url, rec, snap_ts, _offer_payload(sub, block)))
    st = _load_status()
    if st.get("jclq_offer") != "unverified-shape":
        _update_status(jclq_offer="unverified-shape")
        _pack_probe(rec, "jclq_offer_first_nonempty")
        print("[jclq_offer] 首次抓到非空：已标记 unverified-shape 并回传探针包")
    return rows


def parse_jclq_result(url: str, rec: dict, snap_ts: str) -> list:
    j = json.loads(rec["body"].decode("utf-8", errors="replace"))
    if not _ok(j):
        return [_error_row("jclq_result", url, rec, snap_ts, rec["body"])]
    return [_envelope("jclq_result", url, rec, snap_ts, m)
            for m in (j.get("value") or {}).get("matchResult") or []]


def parse_lottery_draw(url: str, rec: dict, snap_ts: str) -> list:
    j = json.loads(rec["body"].decode("utf-8", errors="replace"))
    if not _ok(j):
        return [_error_row("lottery_draw", url, rec, snap_ts, rec["body"])]
    return [_envelope("lottery_draw", url, rec, snap_ts, it)
            for it in (j.get("value") or {}).get("list") or []]


_PARSERS = {
    "jczq_offer": parse_jczq_offer, "jczq_result": parse_jczq_result,
    "jc_issue": parse_jc_issue, "jc_issue_result": parse_jc_issue_result,
    "jclq_offer": parse_jclq_offer, "jclq_result": parse_jclq_result,
    "lottery_draw": parse_lottery_draw,
}


def _load_status() -> dict:
    p = ROOT / "collector.status.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (ValueError, OSError):
        return {}


def _update_status(**kw) -> None:
    st = _load_status()
    st.update(kw)
    st["contract_version"] = CONTRACT
    (ROOT / "collector.status.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _pack_probe(rec: dict, tag: str) -> None:
    """单独回传一份探针包（§5.5 首次非空 / 复探用）。"""
    out = ROOT / "probe"
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    name = f"{tag}_{fname_ts()}.json"
    (raw / name).write_bytes(rec["body"])
    summary = {"generated_at": now_utc(), "collector_host": HOST, "tag": tag,
               "results": [{"topic": "jclq_offer", "url": rec["url"],
                            "http_status": rec.get("http_status", 0),
                            "content_type": rec.get("content_type", ""),
                            "raw_file": f"raw/{name}"}]}
    (out / "probe_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    pack = out / f"probe_{tag}_{fname_ts()}.tar.gz"
    with tarfile.open(pack, "w:gz") as tf:
        tf.add(out / "probe_results.json", arcname="probe_results.json")
        tf.add(raw / name, arcname=f"raw/{name}")
    subprocess.run(["scp", "-o", "BatchMode=yes", str(pack),
                    f"{SSH_ALIAS}:/tmp/{pack.name}"], capture_output=True, text=True, timeout=120)
    subprocess.run(["ssh", "-o", "BatchMode=yes", SSH_ALIAS,
                    f"sudo -n mkdir -p {REMOTE_ROOT}/{HOST} && "
                    f"sudo -n mv /tmp/{pack.name} {REMOTE_ROOT}/{HOST}/ && "
                    f"sudo -n chown league:league {REMOTE_ROOT}/{HOST}/{pack.name}"],
                   capture_output=True, text=True, timeout=60)


def write_batch(topic: str, rows: list) -> Path:
    """落 out/<topic>/<utc>__<batch>.jsonl；0 行产 .empty。追加不覆盖（batch 序号递增）。"""
    out_dir = ROOT / "out" / topic
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = fname_ts()
    batch = 1
    while (out_dir / f"{ts}__{batch:03d}.jsonl").exists():
        batch += 1
    if rows:
        path = out_dir / f"{ts}__{batch:03d}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        path = out_dir / f"{ts}__{batch:03d}.empty"
        path.touch()
    return path


def collect(topic: str) -> int:
    spec = CONFIG["topics"].get(topic)
    if not spec:
        print(f"[collect] 未知 topic: {topic}")
        return 1
    snap_ts = now_utc()
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    yesterday = (datetime.now(CN_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    rows = []
    for url in spec["candidates"]:
        url = url.replace("{today}", today).replace("{yesterday}", yesterday)
        rec = fetch(url)
        rows.extend(_PARSERS[topic](url, rec, snap_ts))
    path = write_batch(topic, rows)
    _update_status(last_collect=topic, last_collect_at=now_utc())
    print(f"[collect] {topic}: {len(rows)} 行 → {path}")
    return 0


def collect_all() -> int:
    rc = 0
    for topic in CONFIG["topics"]:
        rc |= collect(topic)
    return rc


def probe() -> int:
    """探针模式（v1 遗留）：逐个 GET 候选端点；反爬 HTML 换 UA/Referer 重试 2 次；BLOCKED 标记。"""
    out_dir = ROOT / "probe"
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    results = []
    alt_uas = [
        UA,
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    ]
    alt_refs = [REFERER, "https://www.sporttery.cn/", "https://static.sporttery.cn/"]
    idx = 0
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    yesterday = (datetime.now(CN_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    for topic, spec in CONFIG["topics"].items():
        for url in spec["candidates"]:
            idx += 1
            url = url.replace("{today}", today).replace("{yesterday}", yesterday)
            rec = fetch(url)
            if rec.get("http_status") and "html" in rec.get("content_type", "").lower():
                for k in (1, 2):
                    time.sleep(QPS)
                    try:
                        s, c, b = _req(url, alt_uas[k % len(alt_uas)], alt_refs[k % len(alt_refs)])
                        rec = {"url": url, "fetched_at": now_utc(), "http_status": s,
                               "content_type": c, "body": b, "attempts": 1, "retried_ua": k}
                        if "html" not in c.lower():
                            break
                    except (urllib.error.URLError, TimeoutError, OSError) as e:
                        rec["error"] = f"{type(e).__name__}: {e}"
            body = rec.get("body", b"")
            head = body[:HEAD_BYTES].decode("utf-8", errors="replace")
            blocked = not rec.get("http_status") or "html" in rec.get("content_type", "").lower()
            ext = ".html" if "html" in rec.get("content_type", "").lower() else ".json"
            raw_name = f"{topic}__{idx:02d}{ext}"
            (raw_dir / raw_name).write_bytes(body)
            results.append({
                "topic": topic, "url": url, "http_status": rec.get("http_status", 0),
                "content_type": rec.get("content_type", ""), "blocked": blocked,
                "head": head, "raw_file": f"raw/{raw_name}",
                "fetched_at": rec.get("fetched_at", ""), "error": rec.get("error", ""),
            })
            print(f"[probe] {topic:14} {rec.get('http_status', 0):>3} "
                  f"{'BLOCKED' if blocked else 'OK':7} {url[:90]}")
    summary = {"generated_at": now_utc(), "collector_host": HOST, "results": results}
    (out_dir / "probe_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    pack = out_dir / "probe_pack.tar.gz"
    with tarfile.open(pack, "w:gz") as tf:
        tf.add(out_dir / "probe_results.json", arcname="probe_results.json")
        for f in sorted(raw_dir.iterdir()):
            tf.add(f, arcname=f"raw/{f.name}")
    print(f"\nprobe 完成：{len(results)} 端点，{sum(1 for r in results if r['blocked'])} BLOCKED")
    print(f"探针包：{pack}（{pack.stat().st_size} 字节）")
    return 0 if not any(r["blocked"] for r in results) else 1


def push() -> int:
    """推送 out/ 到远端 incoming/<host>/，完成后 touch .done。

    本机无 rsync 且远端 incoming 属 league 组（ubuntu 无写权限）：
    scp 到 /tmp → sudo mv + 解包 + chown → sudo touch .done。
    """
    out_dir = ROOT / "out"
    if not out_dir.exists():
        print("[push] out/ 不存在，无内容可推")
        return 1
    pack = ROOT / "out.tar.gz"
    with tarfile.open(pack, "w:gz") as tf:
        for f in sorted(out_dir.rglob("*")):
            if f.is_file():
                tf.add(f, arcname=f.relative_to(out_dir).as_posix())
    r = subprocess.run(["scp", "-o", "BatchMode=yes", str(pack),
                        f"{SSH_ALIAS}:/tmp/out.tar.gz"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"[push] scp 失败 rc={r.returncode}: {r.stderr.strip()}")
        return 1
    done = f"{now_utc().replace(':', '-')}.done"
    remote_cmd = (f"sudo -n mkdir -p {REMOTE_ROOT}/{HOST} && "
                  f"sudo -n mv /tmp/out.tar.gz {REMOTE_ROOT}/{HOST}/ && "
                  f"cd {REMOTE_ROOT}/{HOST} && sudo -n tar xzf out.tar.gz && "
                  f"sudo -n rm out.tar.gz && "
                  f"sudo -n chown -R league:league {REMOTE_ROOT}/{HOST} && "
                  f"sudo -n touch {REMOTE_ROOT}/{HOST}/{done} && "
                  f"sudo -n chown league:league {REMOTE_ROOT}/{HOST}/{done}")
    r2 = subprocess.run(["ssh", "-o", "BatchMode=yes", SSH_ALIAS, remote_cmd],
                        capture_output=True, text=True, timeout=120)
    if r2.returncode != 0:
        print(f"[push] 远端落盘失败 rc={r2.returncode}: {r2.stderr.strip()}")
        return 1
    print(f"[push] 完成：{REMOTE_ROOT}/{HOST}/ + {done}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="国内采集机（契约 v1.1）")
    ap.add_argument("--probe", action="store_true", help="探针模式（复探用）")
    ap.add_argument("--collect", metavar="TOPIC", help="采集指定 topic 落 JSONL")
    ap.add_argument("--collect-all", action="store_true", help="采集全部 7 topic")
    ap.add_argument("--push", action="store_true", help="推送 out/ 到远端 + .done")
    args = ap.parse_args()
    if args.probe:
        return probe()
    if args.collect:
        return collect(args.collect)
    if args.collect_all:
        return collect_all()
    if args.push:
        return push()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())