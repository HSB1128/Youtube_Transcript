import os, re, requests
from typing import List, Dict, Any, Optional

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

def extract_video_id(url: str) -> Optional[str]:
    url = (url or "").strip()
    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{6,})",
        r"youtu\.be/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{6,})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def iso8601_to_seconds(d: str) -> int:
    # PT#H#M#S 파싱 (간단)
    h = m = s = 0
    mh = re.search(r"(\d+)H", d or "")
    mm = re.search(r"(\d+)M", d or "")
    ms = re.search(r"(\d+)S", d or "")
    if mh: h = int(mh.group(1))
    if mm: m = int(mm.group(1))
    if ms: s = int(ms.group(1))
    return h * 3600 + m * 60 + s

def fetch_videos_metadata(urls: List[str], include_stats: bool=True) -> Dict[str, Any]:
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing")

    items: List[Dict[str, Any]] = []
    ids: List[str] = []
    url_by_id: Dict[str, str] = {}

    for u in urls:
        vid = extract_video_id(u)
        if not vid:
            items.append({"url": u, "videoId": None, "ok": False, "error": "INVALID_URL"})
            continue
        ids.append(vid)
        url_by_id[vid] = u

    if not ids:
        return {"items": items}

    part = "snippet,contentDetails"
    if include_stats:
        part += ",statistics"

    endpoint = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": YOUTUBE_API_KEY,
        "part": part,
        "id": ",".join(ids),
        "maxResults": 50,
    }
    r = requests.get(endpoint, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()

    got = {it["id"]: it for it in data.get("items", [])}

    for vid in ids:
        if vid not in got:
            items.append({"url": url_by_id[vid], "videoId": vid, "ok": False, "error": "NOT_FOUND"})
            continue

        it = got[vid]
        sn = it.get("snippet", {})
        cd = it.get("contentDetails", {})
        st = it.get("statistics", {}) if include_stats else {}

        items.append({
            "url": url_by_id[vid],
            "videoId": vid,
            "ok": True,
            "title": sn.get("title", ""),
            "description": sn.get("description", ""),
            "publishedAt": sn.get("publishedAt", ""),
            "channelTitle": sn.get("channelTitle", ""),
            "durationSec": iso8601_to_seconds(cd.get("duration", "")),
            "stats": st,
        })

    return {"items": items}
