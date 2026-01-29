from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os

from app.youtube_data import fetch_videos_metadata
from app.transcript import fetch_best_transcript   # ★ 교체된 transcript.py 기준
from app.stt import stt_from_youtube_url

app = FastAPI(title="YouTube Transcript Collector (Manual/Auto/Translated) + STT Fallback")

# ====== 환경변수 ======
MAX_DURATION_SEC_FOR_STT = int(os.getenv("MAX_DURATION_SEC_FOR_STT", "900"))
ENABLE_STT = os.getenv("ENABLE_STT", "true").lower() == "true"


# -----------------------------
# Helpers
# -----------------------------
def _cut(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def compute_confidence(
    transcript_source: str,
    transcript_info: Dict[str, Any],
    stt_used: bool,
    stt_ok: bool
) -> str:
    """
    네가 요구한 규칙 그대로:
    - 수동(MANUAL): high
    - 자동(AUTO): medium
    - 번역(TRANSLATED): 잘 나오면 high, 이상하면 medium
        -> 서버에서 완벽 판정은 어렵기 때문에,
           번역 원본이 MANUAL이면 high, AUTO면 medium으로 분기
    - STT 성공: medium
    - 자막 실패 + STT 실패: low
    """
    if transcript_source == "MANUAL":
        return "high"
    if transcript_source == "AUTO":
        return "medium"
    if transcript_source == "TRANSLATED":
        origin = (transcript_info.get("detail", {}) or {}).get("sourceOrigin")
        return "high" if origin == "MANUAL" else "medium"
    if transcript_source == "STT":
        return "medium" if stt_ok else "low"
    return "low"


# -----------------------------
# Request Model
# -----------------------------
class AnalyzeReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    include_stats: bool = True

    # 자막 실패 시 STT 폴백
    stt_fallback: bool = True
    skip_stt_if_longer_than_sec: int = Field(default=MAX_DURATION_SEC_FOR_STT)

    # 응답 크기 제어
    include_segments: bool = True  # Gemini에 통째로 던질 거면 True 권장


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/analyze")
def analyze(req: AnalyzeReq) -> Dict[str, Any]:
    if not req.urls:
        raise HTTPException(400, "urls is empty")

    # 0) 메타데이터 수집
    meta = fetch_videos_metadata(req.urls, include_stats=req.include_stats)

    videos: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for idx, item in enumerate(meta.get("items", []), start=1):
        # base meta output
        base_meta = {
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "channelTitle": item.get("channelTitle", ""),
            "publishedAt": item.get("publishedAt", ""),
            "durationSec": int(item.get("durationSec") or 0),
            "stats": item.get("stats") if req.include_stats else None,
        }

        # 메타 조회 실패/URL invalid
        if not item.get("ok"):
            videos.append({
                "index": idx,
                "url": item.get("url"),
                "videoId": item.get("videoId"),
                "ok": False,
                "error": item.get("error", "META_FAILED"),
                "meta": base_meta,
                "transcriptSource": "NONE",
                "transcriptInfo": None,
                "sttUsed": False,
                "sttInfo": None,
                "confidence": "low",
                "needsTranscript": True,
                "segments": [] if req.include_segments else None,
            })
            warnings.append({
                "index": idx,
                "url": item.get("url"),
                "reason": "META_FAILED",
                "detail": item.get("error")
            })
            continue

        url = item["url"]
        video_id = item["videoId"]
        duration_sec = int(item.get("durationSec") or 0)

        # 1) 자막 최우선: 수동 → 자동 → 번역 (✅)
        tr = fetch_best_transcript(
            video_id=video_id,
            languages=req.languages,
            prefer_translate_targets=req.languages
        )

        segs: List[Dict[str, Any]] = tr.get("segments", []) if tr.get("ok") else []
        transcript_source = tr.get("sourceType", "NONE")  # MANUAL/AUTO/TRANSLATED/NONE

        transcript_info = {
            "sourceType": transcript_source,
            "language": tr.get("language"),
            "detail": tr.get("detail", {})
        }

        # 2) 자막이 없으면 STT 폴백 (옵션)
        stt_used = False
        stt_ok = False
        stt_info: Optional[Dict[str, Any]] = None

        if (not segs) and req.stt_fallback and ENABLE_STT:
            stt_used = True

            if duration_sec > req.skip_stt_if_longer_than_sec:
                stt_info = {
                    "ok": False,
                    "skipped": True,
                    "reason": f"durationSec {duration_sec} > skip_stt_if_longer_than_sec {req.skip_stt_if_longer_than_sec}"
                }
            else:
                stt_info = stt_from_youtube_url(url)
                if stt_info.get("ok") and stt_info.get("segments"):
                    segs = stt_info["segments"]
                    stt_ok = True
                    transcript_source = "STT"
                else:
                    stt_ok = False

        # 3) confidence + needsTranscript 계산
        confidence = compute_confidence(
            transcript_source=transcript_source,
            transcript_info=transcript_info,
            stt_used=stt_used,
            stt_ok=stt_ok
        )
        needs_transcript = (confidence == "low")

        # 4) 최종 결과 구성
        out = {
            "index": idx,
            "url": url,
            "videoId": video_id,
            "ok": True,
            "meta": base_meta,

            "transcriptSource": transcript_source,  # MANUAL/AUTO/TRANSLATED/STT/NONE
            "transcriptInfo": transcript_info,      # 어떤 자막을 잡았는지 상세
            "sttUsed": stt_used,
            "sttInfo": stt_info,

            "confidence": confidence,
            "needsTranscript": needs_transcript,
        }

        if req.include_segments:
            out["segments"] = segs
        else:
            out["segments"] = None

        # 경고 수집(자막/대본 확보 실패)
        if needs_transcript:
            warnings.append({
                "index": idx,
                "url": url,
                "reason": "NO_TRANSCRIPT_AND_STT_FAILED",
                "transcriptSource": transcript_source,
                "transcriptInfo": transcript_info,
                "sttInfo": stt_info
            })

        videos.append(out)

    return {
        "ok": True,
        "count": len(videos),
        "videos": videos,
        "warnings": warnings,
    }
