"""P0-COLLECT2o 自 jc_load 拆出：批↔文件归属与读行工具；.done 清单优先（行数对账），0 字节 marker 走时间戳窗口兜底。"""
import json
import re
from datetime import datetime
from pathlib import Path

from core.log import logger


def _stamp(name: str) -> datetime:
    m = re.search(r"(\d{4})-(\d\d)-(\d\d)T(\d\d)-(\d\d)(?:-(\d\d))?", name)
    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    int(m.group(4)), int(m.group(5)), int(m.group(6) or "0"))


def iter_markers(root: Path, only: str | None = None) -> list[Path]:
    ms = sorted(root.glob("*.done"))
    key = only + ".done" if only and not only.endswith(".done") else only
    return [m for m in ms if m.name == key] if key else ms


def _count_lines(path: Path) -> int:
    return sum(1 for s in open(path, encoding="utf-8") if s.strip())


def _manifest(root: Path, marker: Path) -> dict[str, list[tuple[str, int]]]:
    """.done 文本清单 → {topic: [(相对路径, 声明行数)]}；无前缀行挂 ""；0 字节 marker ⇒ {} 走窗口。"""
    out: dict[str, list[tuple[str, int]]] = {}
    for line in marker.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        rel = parts[0].strip()
        try: decl = int(parts[1].strip())
        except (IndexError, ValueError): decl = -1
        key = rel.split("/", 1)[0] if "/" in rel else ""
        out.setdefault(key, []).append((rel, decl))
    return out


def _check_entry(topic: str, p: Path, decl: int) -> tuple[Path, str]:
    if not p.exists():
        logger.warning("manifest-file-missing topic=%s 文件=%s", topic, p)
        return (p, "rejected")
    actual = _count_lines(p)
    if actual != decl:
        logger.warning("manifest-mismatch topic=%s 声明=%d 实际=%d 文件=%s",
                       topic, decl, actual, p)
        return (p, "rejected")
    return (p, p.suffix.lstrip("."))


def _resolve(root: Path, topics: tuple[str, ...], rel: str, decl: int):
    """清单丢了目录前缀时消歧：唯一"存在且行数吻合"的 topic 才算命中，否则 None（不许猜）。"""
    hits = [(t, root / t / rel) for t in topics
            if (root / t / rel).is_file() and _count_lines(root / t / rel) == decl]
    if len(hits) != 1:
        logger.warning("manifest-无法消歧 rel=%s 声明=%d 命中=%d", rel, decl, len(hits))
        return None
    logger.warning("manifest-无目录前缀 topic=%s 文件=%s（按目录消歧）", hits[0][0], rel)
    return hits[0]


def _from_manifest(root: Path, man: dict[str, list[tuple[str, int]]],
                   topics: tuple[str, ...]) -> dict[str, list[tuple[Path, str]]]:
    out: dict[str, list[tuple[Path, str]]] = {}
    resolved: dict[str, list[tuple[str, int]]] = {}
    for rel, decl in man.get("", []):
        if hit := _resolve(root, topics, rel, decl):
            resolved.setdefault(hit[0], []).append((f"{hit[0]}/{rel}", decl))
    for topic in topics:
        entries = man.get(topic, []) + resolved.get(topic, [])
        out[topic] = [(None, "missing")] if not entries else [
            _check_entry(topic, root / rel, decl) for rel, decl in entries]
    return out


def _window(root: Path, marker: Path,
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


def files_for_batch(root: Path, marker: Path,
                    topics: tuple[str, ...]) -> dict[str, list[tuple[Path, str]]]:
    man = _manifest(root, marker)
    return _from_manifest(root, man, topics) if man else _window(root, marker, topics)


def read_lines(path: Path) -> list[dict]:
    return [json.loads(s) for s in open(path, encoding="utf-8") if s.strip()]
