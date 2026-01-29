# app/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os

from app.youtube_data import fetch_videos_metadata
from app.transcript import fetch_best_transcript
from app.stt import stt_from_youtube_url

app = FastAPI(title="YouTube Transcription (captions first)")

# ====== 환경변수 ======
MAX_DURATION_SEC_FOR_STT = int(os.getenv("MAX_DURATION_SEC_FOR_STT", "1200"))
ENABLE_STT = os.getenv("ENABLE_STT", "true").lower() == "true"


class AnalyzeReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    include_stats: bool = True
    stt_fallback: bool = True
    skip_stt_if_longer_than_sec: int = Field(default=MAX_DURATION_SEC_FOR_STT)


@app.get("/health")
def health():
    return {"ok": True}


def _confidence_from_source(source_type: str) -> str:
    if source_type == "MANUAL":
        return "high"
    if source_type in ("AUTO", "TRANSLATED", "FETCH", "STT"):
        # AUTO/TRANSLATED는 품질 편차가 있으니 기본 medium (정교 평가는 Gemini가)
        return "medium"
    return "low"


def _expand_language_variants(langs: List[str]) -> List[str]:
    # ko -> ko-KR, en -> en-US/en-GB 변형 추가 (요구사항 반영)
    variants: List[str] = []
    for lang in (langs or []):
        l = (lang or "").strip()
        if not l:
            continue
        variants.append(l)
        if l == "ko":
            variants += ["ko-KR"]
        elif l == "en":
            variants += ["en-US", "en-GB"]

    # dedupe keeping order
    seen = set()
    out = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _run(req: AnalyzeReq) -> Dict[str, Any]:
    if not req.urls:
        raise HTTPException(400, "urls is empty")

    meta = fetch_videos_metadata(req.urls, include_stats=req.include_stats)

    per_video: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    languages_priority = _expand_language_variants(req.languages)

    for item in meta.get("items", []):
        # meta fetch 실패
        if not item.get("ok"):
            out = {
                "index": len(per_video) + 1,
                "url": item.get("url"),
                "videoId": item.get("videoId"),
                "ok": False,
                "meta": item,
                "transcriptSource": "NONE",
                "transcriptInfo": {"sourceType": "NONE", "language": None, "languageCode": None, "isGenerated": None, "detail": {"error": "META_FAILED"}},
                "sttUsed": False,
                "sttInfo": None,
                "confidence": "low",
                "needsTranscript": True,
                "segments": [],
            }
            per_video.append(out)
            warnings.append({"index": out["index"], "url": out["url"], "reason": "META_FAILED"})
            continue

        url = item["url"]
        video_id = item["videoId"]
        duration_sec = int(item.get("durationSec") or 0)

        # 1) 자막(수동/자동/번역) 최대한 시도
        ti = fetch_best_transcript(video_id, languages_priority=languages_priority)
        segs = ti.get("segments", []) if ti.get("ok") else []
        transcript_source = ti.get("sourceType", "NONE")

        confidence = _confidence_from_source(transcript_source)
        needs_transcript = (len(segs) == 0)

        # 2) STT 폴백 (자막이 없을 때만)
        stt_info: Optional[Dict[str, Any]] = None
        stt_used = False
        if needs_transcript and req.stt_fallback and ENABLE_STT:
            stt_used = True
            if duration_sec > req.skip_stt_if_longer_than_sec:
                stt_info = {
                    "ok": False,
                    "skipped": True,
                    "reason": f"durationSec {duration_sec} > skip_stt_if_longer_than_sec {req.skip_stt_if_longer_than_sec}",
                }
            else:
                stt_info = stt_from_youtube_url(url)
                if stt_info.get("ok") and stt_info.get("segments"):
                    segs = stt_info["segments"]
                    transcript_source = "STT"
                    confidence = _confidence_from_source("STT")
                    needs_transcript = False

        out = {
            "index": len(per_video) + 1,
            "url": url,
            "videoId": video_id,
            "ok": True,
            "meta": item,
            "transcriptSource": transcript_source,
            "transcriptInfo": {
                "sourceType": ti.get("sourceType", "NONE"),
                "language": ti.get("language"),
                "languageCode": ti.get("languageCode"),
                "isGenerated": ti.get("isGenerated"),
                "detail": ti.get("detail"),
            },
            "sttUsed": stt_used,
            "sttInfo": stt_info,
            "confidence": confidence,
            "needsTranscript": needs_transcript,
            "segments": segs,
        }

        if needs_transcript:
            warnings.append({
                "index": out["index"],
                "url": url,
                "reason": "NO_TRANSCRIPT_AND_STT_FAILED" if stt_used else "NO_TRANSCRIPT",
                "transcriptSource": transcript_source,
                "transcriptInfo": out["transcriptInfo"],
                "sttInfo": stt_info,
            })

        per_video.append(out)

    return {"ok": True, "count": len(per_video), "videos": per_video, "warnings": warnings}


@app.post("/analyze_and_profile")
def analyze_and_profile(req: AnalyzeReq) -> Dict[str, Any]:
    return _run(req)


# (옵션) 과거 n8n 설정이 /analyze를 치는 경우 404 안 나게 호환
@app.post("/analyze")
def analyze(req: AnalyzeReq) -> Dict[str, Any]:
    return _run(req)
