from __future__ import annotations
from typing import Any, Dict, List, Optional
import re

def normalize_urls(urls: List[str]) -> List[str]:
    out: List[str] = []
    for u in urls or []:
        u = (u or "").strip()
        if not u:
            continue
        out.append(u)
    # dedupe keep order
    seen = set()
    deduped = []
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped

def pick_language_priority(langs: List[str]) -> List[str]:
    # 요청이 ["ko","en"] 이런 식이면 그대로 우선순위로 사용
    out: List[str] = []
    for l in (langs or []):
        l = (l or "").strip()
        if not l:
            continue
        out.append(l)
    if not out:
        out = ["ko", "en"]
    # dedupe
    seen = set()
    deduped = []
    for l in out:
        if l not in seen:
            seen.add(l)
            deduped.append(l)
    return deduped

def compact_text(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    # 공백 정리(과한 줄바꿈/공백 압축)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    if max_chars > 0 and len(t) > max_chars:
        t = t[:max_chars]
    return t

def segments_to_text(segments: Any, max_chars: int) -> str:
    """
    Apify가 segments를 주는 경우를 대비:
      [{"start":..., "duration":..., "text":...}, ...]
    또는 [{"text":...}, ...]
    """
    if not segments or not isinstance(segments, list):
        return ""
    parts: List[str] = []
    for s in segments:
        if not isinstance(s, dict):
            continue
        txt = (s.get("text") or "").strip()
        if txt:
            parts.append(txt)
        if max_chars > 0 and sum(len(p) for p in parts) > max_chars:
            break
    joined = " ".join(parts)
    return compact_text(joined, max_chars=max_chars)
