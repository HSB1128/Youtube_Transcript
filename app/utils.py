# app/utils.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

def normalize_urls(urls: List[str]) -> List[str]:
    out = []
    for u in (urls or []):
        s = (u or "").strip()
        if s:
            out.append(s)
    # dedupe keeping order
    seen = set()
    deduped = []
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped

def compact_text(s: str, max_chars: Optional[int] = None) -> str:
    t = (s or "").replace("\r", "\n")
    # 줄바꿈/공백 정리
    lines = [x.strip() for x in t.split("\n")]
    lines = [x for x in lines if x]
    t2 = "\n".join(lines)
    # 연속 공백 축소
    while "  " in t2:
        t2 = t2.replace("  ", " ")
    if max_chars is not None and len(t2) > max_chars:
        t2 = t2[:max_chars]
    return t2

def segments_to_text(segments: Any, max_chars: Optional[int] = None) -> str:
    """
    Apify output transcript가 리스트(세그먼트)로 올 수 있음.
    각 원소에 text가 있다고 가정하고 join.
    """
    texts: List[str] = []
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                txt = (seg.get("text") or "").strip()
                if txt:
                    texts.append(txt)
            elif isinstance(seg, str):
                if seg.strip():
                    texts.append(seg.strip())
    joined = "\n".join(texts)
    return compact_text(joined, max_chars=max_chars)

def pick_language_priority(langs: List[str]) -> List[str]:
    """
    ko -> ko, ko-KR
    en -> en, en-US, en-GB
    """
    variants: List[str] = []
    for lang in (langs or []):
        l = (lang or "").strip()
        if not l:
            continue
        variants.append(l)
        if l == "ko":
            variants.append("ko-KR")
        elif l == "en":
            variants.extend(["en-US", "en-GB"])

    # dedupe keeping order
    seen = set()
    out = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out or ["ko", "ko-KR", "en", "en-US", "en-GB"]
