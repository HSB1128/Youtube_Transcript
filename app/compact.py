from typing import Dict, Any, List

def _cut(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"

def build_compact_view(
    item: Dict[str, Any],
    scene_segments: List[Dict[str, Any]],
    max_scenes: int = 18,
    max_chars_per_scene: int = 160,
) -> Dict[str, Any]:
    """
    긴 영상/대량 영상에서 토큰 폭발을 막기 위해:
    - 씬을 전부 주지 않고 중요한 구간 위주로 샘플링
    - 텍스트는 max_chars_per_scene로 컷
    """
    title = item.get("title", "")
    desc = item.get("description", "")

    # 1) 씬이 너무 많으면: 앞/중간/뒤 골고루 뽑기
    scenes = scene_segments[:]  # copy
    if len(scenes) > max_scenes:
        # 앞 1/3, 중간 1/3, 뒤 1/3로 균등 샘플
        third = max_scenes // 3
        head = scenes[:third]
        mid_start = max(0, (len(scenes) // 2) - (third // 2))
        mid = scenes[mid_start:mid_start + third]
        tail = scenes[-(max_scenes - len(head) - len(mid)):]
        scenes = head + mid + tail

    compact_scenes = []
    for sc in scenes:
        st = sc.get("start", 0.0)
        dur = sc.get("duration", 0.0)
        text = _cut(sc.get("text", ""), max_chars_per_scene)
        compact_scenes.append({
            "t": f"{int(st)}-{int(st+dur)}",
            "text": text
        })

    # 2) 훅/CTA 후보: 앞 3개, 뒤 2개 정도
    hook = [x["text"] for x in compact_scenes[:3]]
    cta = [x["text"] for x in compact_scenes[-2:]] if len(compact_scenes) >= 2 else []

    return {
        "title": _cut(title, 120),
        "description": _cut(desc, 300),
        "hook": hook,
        "cta": cta,
        "scenes": compact_scenes
    }
