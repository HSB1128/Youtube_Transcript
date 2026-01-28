from typing import List, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi

def try_fetch_transcript_segments(video_id: str, languages: List[str]) -> List[Dict[str, Any]]:
    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id, languages=languages, preserve_formatting=False)
        raw = fetched.to_raw_data()  # [{text,start,duration},...]
        segs: List[Dict[str, Any]] = []
        for x in raw:
            text = (x.get("text") or "").strip()
            if not text:
                continue
            segs.append({
                "start": float(x.get("start", 0.0)),
                "duration": float(x.get("duration", 0.0)),
                "text": text,
            })
        return segs
    except Exception:
        return []
