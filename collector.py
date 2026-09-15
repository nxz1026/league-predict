#!/usr/bin/env python3
"""国内采集机：取官方 JSON → 落 JSONL → 推远端（league-predict 实施文档 v1）。

定位：独立小工具，只做取数/落盘/推送。不连 DB、不解析 HTML、不装重型依赖。
仅 stdlib（urllib/json/hashlib/pathlib/subprocess/tarfile/argparse）。

实施顺序（文档 §3 强制）：先 probe → 探针包回传 → 契约冻结 → 再写解析。
本文件 probe 模式完整可用；collect 解析部分待契约冻结后填充。

用法：
  python collector.py --probe            # 逐个 GET 候选端点，产出 probe_pack.tar.gz
  python collector.py --collect <topic>  # 拉取并落 JSONL（契约冻结后启用）
  python collector.py --push             # rsync 推送 out/ 到远端 + .done
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


def now_utc() -> str:
    """UTC ISO8601 带 Z（文件名/时间戳统一口径）。"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fname_ts() -> str:
    """文件名用 UTC 时间戳（冒号换 -，Windows 兼容）：2026-09-15T13-30Z。"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%MZ")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _req(url: str, ua: str, referer: str, timeout: int = 20) -> tuple[int, str, bytes]:
    """GET 单次；返回 (http_status, content_type, body)。网络错误抛 urllib.error。"""
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
            time.sleep(QPS)  # QPS ≤ 1
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


def is_html(rec: dict) -> bool:
    ctype = rec.get("content_type", "").lower()
    body = rec.get("body", b"")
    return "html" in ctype or body[:1] == b"<"


def probe() -> int:
    """逐个 GET 候选端点；反爬 HTML 换 UA/Referer 重试 2 次；BLOCKED 标记。产出 probe_pack.tar.gz。"""
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
    yesterday = (datetime.now(CN_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    for topic, spec in CONFIG["topics"].items():
        for url in spec["candidates"]:
            idx += 1
            url = url.replace("{yesterday}", yesterday)
            rec = fetch(url)
            status = rec.get("http_status", 0)
            # 反爬 HTML：换 UA/Referer 重试 2 次
            if status and is_html(rec):
                for k in (1, 2):
                    time.sleep(QPS)
                    try:
                        s, c, b = _req(url, alt_uas[k % len(alt_uas)], alt_refs[k % len(alt_refs)])
                        rec = {"url": url, "fetched_at": now_utc(), "http_status": s,
                               "content_type": c, "body": b, "attempts": 1, "retried_ua": k}
                        if not is_html(rec):
                            break
                    except (urllib.error.URLError, TimeoutError, OSError) as e:
                        rec["error"] = f"{type(e).__name__}: {e}"
            body = rec.get("body", b"")
            head = body[:HEAD_BYTES].decode("utf-8", errors="replace")
            blocked = not rec.get("http_status") or is_html(rec)
            # 完整响应体落盘（JSON 存 .json；HTML 存 .html 供人工判断）
            ext = ".html" if is_html(rec) else ".json"
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
    # 摘要 + 打包
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


def collect(topic: str) -> int:
    """拉取 topic → 落 out/<topic>/<utc>__<batch>.jsonl。解析待契约冻结后填充。"""
    print(f"[collect] {topic}：契约未冻结，解析未实现（先跑 --probe 回传等冻结）")
    return 1


def push() -> int:
    """推送 out/ 到远端 incoming/<host>/，完成后 touch .done。

    本机无 rsync 且远端 incoming 属 league 组（ubuntu 无写权限）：
    scp 到 /tmp → sudo mv + 解包 + chown → sudo touch .done。
    """
    import tarfile
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
                  f"sudo -n touch {REMOTE_ROOT}/{HOST}/{done}")
    r2 = subprocess.run(["ssh", "-o", "BatchMode=yes", SSH_ALIAS, remote_cmd],
                        capture_output=True, text=True, timeout=120)
    if r2.returncode != 0:
        print(f"[push] 远端落盘失败 rc={r2.returncode}: {r2.stderr.strip()}")
        return 1
    print(f"[push] 完成：{REMOTE_ROOT}/{HOST}/ + {done}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="国内采集机（league-predict 实施文档 v1）")
    ap.add_argument("--probe", action="store_true", help="探针模式：逐个 GET 候选端点，产出 probe_pack.tar.gz")
    ap.add_argument("--collect", metavar="TOPIC", help="采集指定 topic 落 JSONL（契约冻结后启用）")
    ap.add_argument("--push", action="store_true", help="rsync 推送 out/ 到远端 + .done")
    args = ap.parse_args()
    if args.probe:
        return probe()
    if args.collect:
        return collect(args.collect)
    if args.push:
        return push()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())