from typing import List, Dict, Any

def make_scene_segments(segs: List[Dict[str, Any]], scene_sec: float = 2.0) -> List[Dict[str, Any]]:
    if not segs:
        return []

    scenes: List[Dict[str, Any]] = []
    cur = {"start": None, "end": None, "text": ""}

    def flush():
        nonlocal cur
        if cur["start"] is not None and cur["text"].strip():
            scenes.append({
                "start": float(cur["start"]),
                "duration": float(cur["end"] - cur["start"]),
                "text": cur["text"].strip(),
            })
        cur = {"start": None, "end": None, "text": ""}

    for s in segs:
        st = float(s.get("start", 0.0))
        dur = float(s.get("duration", 0.0))
        ed = st + dur
        tx = (s.get("text") or "").strip()
        if not tx:
            continue

        if cur["start"] is None:
            cur["start"] = st
            cur["end"] = ed
            cur["text"] = tx
            continue

        # 다음 텍스트를 합치면 씬 길이가 scene_sec 넘어가면 flush
        if (ed - cur["start"]) >= scene_sec:
            flush()
            cur["start"] = st
            cur["end"] = ed
            cur["text"] = tx
        else:
            cur["end"] = ed
            cur["text"] += " " + tx

    flush()
    return scenes
