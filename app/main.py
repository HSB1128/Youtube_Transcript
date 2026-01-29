from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os

from app.youtube_data import fetch_videos_metadata
from app.transcript import fetch_best_transcript   # ★ fetch_best_transcript 구현되어 있어야 함
from app.stt import stt_from_youtube_url

app = FastAPI(title="YouTube Transcript Collector + Profile Analyzer (via Gemini downstream)")

# ====== 환경변수 ======
MAX_DURATION_SEC_FOR_STT = int(os.getenv("MAX_DURATION_SEC_FOR_STT", "900"))
ENABLE_STT = os.getenv("ENABLE_STT", "true").lower() == "true"


# -----------------------------
# Helpers
# -----------------------------
def compute_confidence(
    transcript_source: str,
    transcript_info: Dict[str, Any],
    stt_used: bool,
    stt_ok: bool
) -> str:
    """
    네 규칙:
    - 수동(MANUAL): high
    - 자동(AUTO): medium
    - 번역(TRANSLATED): 원본이 MANUAL이면 high, AUTO면 medium
    - STT 성공: medium
    - 자막/대본 확보 실패: low
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
    include_segments: bool = True  # 1차 분석 결과를 Gemini로 넘길 거면 True 권장


@app.get("/health")
def health():
    return {"ok": True}


# ✅ 기존 analyze도 유지해둘게 (테스트/호환용)
@app.post("/analyze")
def analyze(req: AnalyzeReq) -> Dict[str, Any]:
    return _analyze_core(req)


# ✅ 너가 n8n에서 부르는 엔드포인트
@app.post("/analyze_and_profile")
def analyze_and_profile(req: AnalyzeReq) -> Dict[str, Any]:
    # 지금 단계에서는 "profile"을 서버에서 Gemini로 만들지 말고,
    # 원데이터(자막/메타 + 라벨링 + confidence)를 돌려주는 역할만 수행.
    # 2차 Gemini 노드가 이 출력을 받아 채널 기획안을 만들면 됨.
    return _analyze_core(req)


def _analyze_core(req: AnalyzeReq) -> Dict[str, Any]:
    if not req.urls:
        raise HTTPException(400, "urls is empty")

    meta = fetch_videos_metadata(req.urls, include_stats=req.include_stats)

    videos: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for idx, item in enumerate(meta.get("items", []), start=1):
        base_meta = {
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "channelTitle": item.get("channelTitle", ""),
            "publishedAt": item.get("publishedAt", ""),
            "durationSec": int(item.get("durationSec") or 0),
            "stats": item.get("stats") if req.include_stats else None,
        }

        # 메타 조회 실패
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

        # 1) 자막 최우선: 수동 → 자동 → 번역
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

        # 2) 자막이 없으면 STT 폴백
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

        # 3) confidence + needsTranscript
        confidence = compute_confidence(
            transcript_source=transcript_source,
            transcript_info=transcript_info,
            stt_used=stt_used,
            stt_ok=stt_ok
        )
        needs_transcript = (confidence == "low")

        out = {
            "index": idx,
            "url": url,
            "videoId": video_id,
            "ok": True,
            "meta": base_meta,

            "transcriptSource": transcript_source,  # MANUAL/AUTO/TRANSLATED/STT/NONE
            "transcriptInfo": transcript_info,
            "sttUsed": stt_used,
            "sttInfo": stt_info,

            "confidence": confidence,
            "needsTranscript": needs_transcript,
        }

        if req.include_segments:
            out["segments"] = segs
        else:
            out["segments"] = None

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
