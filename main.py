from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import re
import asyncio
from youtube_transcript_api import YouTubeTranscriptApi

app = FastAPI(title="YouTube Transcript SRT Service")

class TranscriptReq(BaseModel):
    urls: List[str] = Field(...)
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    preserve_formatting: bool = False
    concurrency: int = 3
    per_video_timeout_sec: int = 20

def extract_video_id(url: str) -> Optional[str]:
    url = url.strip()
    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{6,})",
        r"youtu\.be/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def srt_timestamp(t: float) -> str:
    h = int(t // 3600); t -= 3600 * h
    m = int(t // 60);   t -= 60 * m
    s = int(t);         ms = int(round((t - s) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def snippets_to_srt(raw_snippets: List[Dict[str, Any]]) -> str:
    lines = []
    idx = 1
    for sn in raw_snippets:
        text = (sn.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        start = float(sn.get("start", 0.0))
        dur = float(sn.get("duration", 0.0))
        end = start + dur
        lines.append(str(idx))
        lines.append(f"{srt_timestamp(start)} --> {srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
        idx += 1
    return "\n".join(lines).strip() + "\n"

async def fetch_one(ytt: YouTubeTranscriptApi, url: str, req: TranscriptReq, sem: asyncio.Semaphore):
    vid = extract_video_id(url)
    if not vid:
        return {"url": url, "ok": False, "error": "INVALID_URL"}

    async with sem:
        try:
            fetched = await asyncio.wait_for(
                asyncio.to_thread(
                    ytt.fetch,
                    vid,
                    languages=req.languages,
                    preserve_formatting=req.preserve_formatting,
                ),
                timeout=req.per_video_timeout_sec
            )
            raw = fetched.to_raw_data()
            return {
                "url": url,
                "videoId": vid,
                "ok": True,
                "snippets": raw,
                "srt": snippets_to_srt(raw),
            }
        except asyncio.TimeoutError:
            return {"url": url, "videoId": vid, "ok": False, "error": "TIMEOUT"}
        except Exception as e:
            return {"url": url, "videoId": vid, "ok": False, "error": f"{type(e).__name__}: {str(e)}"}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/transcripts")
async def transcripts(req: TranscriptReq):
    if not req.urls:
        raise HTTPException(status_code=400, detail="urls is empty")

    ytt = YouTubeTranscriptApi()
    sem = asyncio.Semaphore(max(1, min(req.concurrency, 10)))
    tasks = [fetch_one(ytt, u, req, sem) for u in req.urls]
    results = await asyncio.gather(*tasks)
    return {"count": len(req.urls), "results": results}
