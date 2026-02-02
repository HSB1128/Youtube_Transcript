from __future__ import annotations
from typing import Any, Dict, List, Optional
import re


def normalize_urls(urls: List[str]) -> List[str]:
    out: List[str] = []
    for u in urls or []:
        if not u:
            continue
        s = str(u).strip()
        if not s:
            continue
        out.append(s)
    # dedupe keep order
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def pick_language_priority(langs: List[str]) -> List[str]:
    # 요청이 ["ko","en"] 이런 식이면 그대로
    out: List[str] = []
    for l in (langs or []):
        s = (l or "").strip()
        if s:
            out.append(s)
    if not out:
        out = ["ko", "en"]
    # dedupe
    seen = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def compact_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    t = str(text)
    if len(t) <= max_chars:
        return t
    return t[:max_chars]


def segments_to_text(segments: Any, max_chars: int) -> str:
    """
    Apify가 transcript를 segments(list)로 주는 경우가 있어서 합쳐줌.
    segments 아이템이 {"text": "..."} 형태라고 가정하고 최대 max_chars까지 합침.
    """
    if not segments or not isinstance(segments, list):
        return ""
    acc = []
    total = 0
    for s in segments:
        if not isinstance(s, dict):
            continue
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        # 너무 길면 컷
        if total + len(txt) + 1 > max_chars:
            remain = max_chars - total
            if remain > 0:
                acc.append(txt[:remain])
            break
        acc.append(txt)
        total += len(txt) + 1
    return "\n".join(acc)
