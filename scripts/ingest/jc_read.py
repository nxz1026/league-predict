"""P0-COLLECT2i 自 jc_load 拆出：批↔文件时间戳窗口归属与读行工具；_stamp/iter_markers/read_lines 逐字搬移，files_for_batch 按 C 条改返回文件列表。"""
import json
import re
from datetime import datetime
from pathlib import Path


def _stamp(name: str) -> datetime:
    m = re.search(r"(\d{4})-(\d\d)-(\d\d)T(\d\d)-(\d\d)(?:-(\d\d))?", name)
    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    int(m.group(4)), int(m.group(5)), int(m.group(6) or "0"))


def iter_markers(root: Path, only: str | None = None) -> list[Path]:
    ms = sorted(root.glob("*.done"))
    key = only + ".done" if only and not only.endswith(".done") else only
    return [m for m in ms if m.name == key] if key else ms


def files_for_batch(root: Path, marker: Path,
                    topics: tuple[str, ...]) -> dict[str, list[tuple[Path, str]]]:
    ms = iter_markers(root)
    i = ms.index(marker)
    lo, hi = (_stamp(ms[i - 1].name) if i else datetime.min), _stamp(marker.name)
    out = {}
    for topic in topics:
        cands = [p for pat in ("*.jsonl", "*.empty")
                 for p in (root / topic).glob(pat) if lo < _stamp(p.name) <= hi]
        cands.sort(key=lambda p: p.name)
        out[topic] = [(p, p.suffix.lstrip(".")) for p in cands]
    return out


def read_lines(path: Path) -> list[dict]:
    return [json.loads(s) for s in open(path, encoding="utf-8") if s.strip()]
