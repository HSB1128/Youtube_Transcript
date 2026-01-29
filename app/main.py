# app/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import os

from app.youtube_data import fetch_videos_metadata
from app.transcript import fetch_best_transcript   # ✅ 여기 변경
from app.stt import stt_from_youtube_url
from app.segment import make_scene_segments
from app.compact import build_compact_view

app = FastAPI(title="YouTube Transcription + Analysis Extractor")

# ====== 환경변수 ======
SCENE_SEC = float(os.getenv("SCENE_SEC", "2.0"))
MAX_SCENES_PER_VIDEO = int(os.getenv("MAX_SCENES_PER_VIDEO", "18"))
MAX_CHARS_PER_SCENE = int(os.getenv("MAX_CHARS_PER_SCENE", "160"))
MAX_DURATION_SEC_FOR_STT = int(os.getenv("MAX_DURATION_SEC_FOR_STT", "900"))
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
    # 네가 말한 기준을 “기본값”으로 반영 (품질 판정은 Gemini가 정리)
    if source_type == "MANUAL":
        return "high"
    if source_type == "AUTO":
        return "medium"
    if source_type == "TRANSLATED":
        # 번역이 잘 뽑히면 high가 될 수도 있지만, 서버단에서 품질판정은 어려워서 기본 medium
        return "medium"
    if source_type == "FETCH":
        # fetch로만 잡힌 경우도 결국 manual/auto 섞여 있을 수 있으니 기본 medium
        return "medium"
    return "low"

@app.post("/analyze")
def analyze(req: AnalyzeReq) -> Dict[str, Any]:
    if not req.urls:
        raise HTTPException(400, "urls is empty")

    meta = fetch_videos_metadata(req.urls, include_stats=req.include_stats)

    per_video: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # 언어 우선순위 확장(ko 변형, en 변형)
    # 네 요구: ko, ko-KR, en, en-US 등 변형도 함께
    lang_variants = []
    for lang in (req.languages or []):
        l = lang.strip()
        if not l:
            continue
        lang_variants.append(l)
        if l == "ko":
            lang_variants += ["ko-KR"]
        if l == "en":
            lang_variants += ["en-US", "en-GB"]
    # 중복 제거(순서 유지)
    seen = set()
    languages_priority = []
    for l in lang_variants:
        if l not in seen:
            seen.add(l)
            languages_priority.append(l)

    for item in meta["items"]:
        if not item.get("ok"):
            out = {
                "ok": False,
                **item,
                "transcriptSource": "NONE",
                "transcriptInfo": {"sourceType": "NONE", "language": None, "detail": {"error": "META_FAILED"}},
                "sttUsed": False,
                "sttInfo": None,
                "confidence": "low",
                "needsTranscript": True,
                "segments": [],
                "sceneSegments": [],
                "compact": {"hook": [], "cta": [], "scenes": [], "title": "", "description": ""},
            }
            per_video.append(out)
            warnings.append({"url": item.get("url"), "reason": "META_FAILED"})
            continue

        url = item["url"]
        video_id = item["videoId"]
        duration_sec = int(item.get("durationSec") or 0)

        # 1) 자막(수동/자동/번역) 최대한 시도
        ti = fetch_best_transcript(video_id, languages_priority=languages_priority)
        segs = ti.get("segments", []) if ti.get("ok") else []
        transcript_source = ti.get("sourceType", "NONE")

        # confidence/needsTranscript
        confidence = _confidence_from_source(transcript_source)
        needs_transcript = (not segs)

        # 2) STT 폴백 (자막이 없을 때만)
        stt_info = None
        stt_used = False
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
                    transcript_source = "STT"
                    confidence = "medium"
                    needs_transcript = False

        # 3) 씬 분할 + compact
        scene_segments = make_scene_segments(segs, scene_sec=SCENE_SEC)
        compact = build_compact_view(
            item=item,
            scene_segments=scene_segments,
            max_scenes=MAX_SCENES_PER_VIDEO,
            max_chars_per_scene=MAX_CHARS_PER_SCENE,
        )

        out = {
            "index": len(per_video) + 1,
            "url": url,
            "videoId": video_id,
            "ok": True,
            "meta": item,  # 필요하면 여기서 meta만 골라서 반환하도록 줄여도 됨
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
            "sceneSegments": scene_segments,
            "compact": compact,
        }

        # 경고 모으기
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

    return {
        "ok": True,
        "count": len(per_video),
        "videos": per_video,
        "warnings": warnings,
    }
