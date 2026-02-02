from __future__ import annotations

from typing import Any, Dict, List, Optional
import re


def normalize_urls(urls: Any) -> List[str]:
    """
    urls가 아래 형태로 올 수 있음:
    - ["https://...","https://..."]
    - "https://...\nhttps://...\n"
    - " https://... , https://... "
    """
    if urls is None:
        return []

    if isinstance(urls, list):
        raw = []
        for u in urls:
            if not u:
                continue
            raw.append(str(u))
        joined = "\n".join(raw)
    else:
        joined = str(urls)

    # 쉼표/공백/개행 혼합 대비
    parts = re.split(r"[\s,\n]+", joined.strip())
    cleaned = []
    for p in parts:
        if not p:
            continue
        p = p.strip()
        if p.startswith("http://") or p.startswith("https://"):
            cleaned.append(p)

    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for u in cleaned:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def pick_language_priority(languages: Optional[List[str]]) -> List[str]:
    if not languages:
        return ["ko", "en"]
    out = []
    for x in languages:
        s = str(x).strip().lower()
        if not s:
            continue
        out.append(s)
    # 중복 제거
    seen = set()
    uniq = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq or ["ko", "en"]


def compact_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    t = str(text)
    # 너무 긴 공백 정리
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    if max_chars and len(t) > max_chars:
        return t[:max_chars]
    return t


def segments_to_text(segments: Any, max_chars: int = 0) -> str:
    """
    transcript segments (list[dict]) -> join
    흔히 Apify가 {"transcript":[{"text":"..."},...]} 형태로 줄 수 있음
    """
    if not segments or not isinstance(segments, list):
        return ""
    texts = []
    for seg in segments:
        if isinstance(seg, dict):
            txt = seg.get("text") or seg.get("caption") or seg.get("value") or ""
            if txt:
                texts.append(str(txt))
        elif isinstance(seg, str):
            texts.append(seg)
    joined = "\n".join(texts).strip()
    if not joined:
        return ""
    return compact_text(joined, max_chars=max_chars if max_chars else len(joined))
