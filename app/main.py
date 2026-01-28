from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import os

from app.youtube_data import fetch_videos_metadata
from app.transcript import try_fetch_transcript_segments
from app.stt import stt_from_youtube_url
from app.segment import make_scene_segments
from app.compact import build_compact_view

app = FastAPI(title="YouTube Transcription + Analysis Extractor")

# ====== 환경변수 ======
SCENE_SEC = float(os.getenv("SCENE_SEC", "2.0"))               # 씬 분할 기준(초)
MAX_SCENES_PER_VIDEO = int(os.getenv("MAX_SCENES_PER_VIDEO", "18"))  # compact에서 씬 최대 개수
MAX_CHARS_PER_SCENE = int(os.getenv("MAX_CHARS_PER_SCENE", "160"))   # compact에서 씬 텍스트 컷
MAX_DURATION_SEC_FOR_STT = int(os.getenv("MAX_DURATION_SEC_FOR_STT", "900"))  # STT 허용 최대 길이(초) 기본 15분
ENABLE_STT = os.getenv("ENABLE_STT", "true").lower() == "true"

class AnalyzeReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    include_stats: bool = True
    stt_fallback: bool = True
    # 긴 영상이 섞여 있을 때 안전장치
    skip_stt_if_longer_than_sec: int = Field(default=MAX_DURATION_SEC_FOR_STT)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/analyze")
def analyze(req: AnalyzeReq) -> Dict[str, Any]:
    if not req.urls:
        raise HTTPException(400, "urls is empty")

    meta = fetch_videos_metadata(req.urls, include_stats=req.include_stats)

    per_video: List[Dict[str, Any]] = []
    for item in meta["items"]:
        # URL/ID가 유효하지 않거나, 메타 조회 실패한 항목은 그대로 반환
        if not item.get("ok"):
            per_video.append({
                **item,
                "transcriptSource": "NONE",
                "segments": [],
                "sceneSegments": [],
                "compact": {
                    "hook": [],
                    "body": [],
                    "cta": [],
                    "scenes": [],
                }
            })
            continue

        url = item["url"]
        video_id = item["videoId"]
        duration_sec = int(item.get("durationSec") or 0)

        # 1) transcript 우선 시도
        segs = try_fetch_transcript_segments(video_id, req.languages)
        transcript_source = "YOUTUBE_CAPTION" if segs else "NONE"

        # 2) 없으면 STT 폴백
        stt_info = None
        if (not segs) and req.stt_fallback and ENABLE_STT:
            if duration_sec > req.skip_stt_if_longer_than_sec:
                transcript_source = "NONE"
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
                else:
                    transcript_source = "NONE"

        # 3) 씬 분할
        scene_segments = make_scene_segments(segs, scene_sec=SCENE_SEC)

        # 4) compact 생성(토큰 폭발 방지용)
        compact = build_compact_view(
            item=item,
            scene_segments=scene_segments,
            max_scenes=MAX_SCENES_PER_VIDEO,
            max_chars_per_scene=MAX_CHARS_PER_SCENE,
        )

        per_video.append({
            **item,
            "transcriptSource": transcript_source,
            "segments": segs,                 # 원본 세그먼트(필요 없으면 n8n에서 버려도 됨)
            "sceneSegments": scene_segments,  # 2초 단위 묶음
            "sttInfo": stt_info,              # STT 실패/스킵 이유 추적용
            "compact": compact                # Gemini에 주기 좋은 압축본
        })

    return {
        "ok": True,
        "count": len(per_video),
        "sceneSec": SCENE_SEC,
        "perVideo": per_video
    }
