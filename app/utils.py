# app/utils.py
from __future__ import annotations
from typing import Any, List


def normalize_urls(urls: List[str]) -> List[str]:
    out = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        out.append(u)
    # 중복 제거(순서 유지)
    seen = set()
    uniq = []
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def compact_text(text: str, max_chars: int = 18000) -> str:
    if not text:
        return ""
    t = " ".join(text.split())
    if len(t) > max_chars:
        t = t[:max_chars]
    return t


def segments_to_text(segments: Any, max_chars: int = 18000) -> str:
    """
    transcript segments가 리스트라면
    - {"text": "...", ...} 형태들을 join
    """
    if not segments:
        return ""
    if isinstance(segments, list):
        parts = []
        for s in segments:
            if isinstance(s, dict):
                parts.append(str(s.get("text", "")).strip())
            else:
                parts.append(str(s).strip())
        text = " ".join([p for p in parts if p])
        return compact_text(text, max_chars=max_chars)
    return compact_text(str(segments), max_chars=max_chars)
