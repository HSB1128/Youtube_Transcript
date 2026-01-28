from typing import Dict, Any, List
import re

def _cut(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"

def _duration_bucket(duration_sec: int) -> str:
    # 필요하면 Gemini가 "짧은 영상/긴 영상" 감만 잡게 하는 용도
    if duration_sec <= 60:
        return "short"
    if duration_sec <= 300:
        return "mid"
    return "long"

def build_compact_view(
    item: Dict[str, Any],
    natural_segments: List[Dict[str, Any]],
    max_scenes: int = 12,
    max_chars_per_scene: int = 140,
    include_duration_bucket: bool = False,
) -> Dict[str, Any]:
    """
    Gemini에 바로 던지기 위한 compact:
    - 긴 대본/자막을 "자연 세그먼트" 단위로 받은 뒤, 중요 구간 위주로 샘플링
    - 각 scene은 start/end/dur 숫자 + text(컷)
    """

    title = item.get("title", "")
    desc = item.get("description", "")
    duration_sec = int(item.get("durationSec") or 0)

    scenes = natural_segments[:]  # copy

    # (A) 너무 많으면 앞/중간/뒤에서 균등 샘플링
    if len(scenes) > max_scenes:
        third = max_scenes // 3
        head = scenes[:third]

        mid_start = max(0, (len(scenes) // 2) - (third // 2))
        mid = scenes[mid_start:mid_start + third]

        tail_need = max_scenes - len(head) - len(mid)
        tail = scenes[-tail_need:] if tail_need > 0 else []

        scenes = head + mid + tail

    compact_scenes: List[Dict[str, Any]] = []
    for sc in scenes:
        st = int(float(sc.get("start", 0.0)))
        dur = int(float(sc.get("duration", 0.0)))
        ed = st + max(0, dur)
        text = _cut(sc.get("text", ""), max_chars_per_scene)

        if not text:
            continue

        compact_scenes.append({
            "start": st,
            "end": ed,
            "dur": max(0, dur),
            "text": text,
        })

    # (B) 훅/CTA 후보: 앞 3개, 뒤 2개
    hook = compact_scenes[:3]
    cta = compact_scenes[-2:] if len(compact_scenes) >= 2 else []

    out: Dict[str, Any] = {
        "title": _cut(title, 120),
        "description": _cut(desc, 180),
        "hook": hook,
        "cta": cta,
        "scenes": compact_scenes,
    }

    if include_duration_bucket:
        out["durationBucket"] = _duration_bucket(duration_sec)

    return out
