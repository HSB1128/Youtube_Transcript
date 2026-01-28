from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import os

from app.youtube_data import fetch_videos_metadata
from app.transcript import try_fetch_transcript_segments
from app.stt import stt_from_youtube_url
from app.segment import make_natural_segments  # 변경
from app.compact import build_compact_view

app = FastAPI(title="YouTube Transcription + Analysis Extractor")

# ====== 환경변수 ======
# NOTE: MAX_DURATION_SEC_FOR_STT 이름 오타 나면 적용 안 됨. (DUARATION X)
MAX_DURATION_SEC_FOR_STT = int(os.getenv("MAX_DURATION_SEC_FOR_STT", "900"))
ENABLE_STT = os.getenv("ENABLE_STT", "true").lower() == "true"

MAX_SCENES_PER_VIDEO = int(os.getenv("MAX_SCENES_PER_VIDEO", "12"))
MAX_CHARS_PER_SCENE = int(os.getenv("MAX_CHARS_PER_SCENE", "140"))

# 자연 세그먼트 파라미터
PAUSE_GAP_SEC = float(os.getenv("PAUSE_GAP_SEC", "0.7"))
MAX_SPAN_SEC = float(os.getenv("MAX_SPAN_SEC", "10.0"))
MAX_SEG_CHARS = int(os.getenv("MAX_SEG_CHARS", "240"))

class AnalyzeReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    include_stats: bool = True
    stt_fallback: bool = True

    # STT 안전장치
    skip_stt_if_longer_than_sec: int = Field(default=MAX_DURATION_SEC_FOR_STT)

    # ====== 출력 옵션(기본: compact-only) ======
    include_segments: bool = False
    include_natural_segments: bool = False  # 자연 세그먼트(중간 데이터)도 보고 싶을 때
    include_compact: bool = True
    include_duration_bucket: bool = False   # compact에 durationBucket 포함 여부

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/analyze")
def analyze(req: AnalyzeReq) -> Dict[str, Any]:
    if not req.urls:
        raise HTTPException(400, "urls is empty")

    meta = fetch_videos_metadata(req.urls, include_stats=req.include_stats)

    per_video: List[Dict[str, Any]] = []
    for item in meta.get("items", []):
        # URL/ID가 유효하지 않거나, 메타 조회 실패한 항목은 그대로 반환
        if not item.get("ok"):
            per_video.append({
                **item,
                "transcriptSource": "NONE",
                "sttInfo": None,
                "segments": [] if req.include_segments else None,
                "naturalSegments": [] if req.include_natural_segments else None,
                "compact": {
                    "title": "",
                    "description": "",
                    "hook": [],
                    "cta": [],
                    "scenes": [],
                } if req.include_compact else None
            })
            continue

        url = item["url"]
        video_id = item["videoId"]
        duration_sec = int(item.get("durationSec") or 0)

        # 1) transcript 우선 시도
        segs = try_fetch_transcript_segments(video_id, req.languages)
        transcript_source = "YOUTUBE_CAPTION" if segs else "NONE"

        # 2) 없으면 STT 폴백(조건 만족 시)
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

        # 3) 자연 세그먼트 생성(2초 고정 대신)
        natural_segments = make_natural_segments(
            segs,
            pause_gap_sec=PAUSE_GAP_SEC,
            max_span_sec=MAX_SPAN_SEC,
            max_chars=MAX_SEG_CHARS,
        )

        # 4) compact 생성(토큰 폭발 방지용)
        compact = None
        if req.include_compact:
            compact = build_compact_view(
                item=item,
                natural_segments=natural_segments,
                max_scenes=MAX_SCENES_PER_VIDEO,
                max_chars_per_scene=MAX_CHARS_PER_SCENE,
                include_duration_bucket=req.include_duration_bucket,
            )

        payload: Dict[str, Any] = {
            **item,
            "transcriptSource": transcript_source,
            "sttInfo": stt_info,
        }

        # ====== 큰 데이터는 기본 제외(=n8n 안정) ======
        if req.include_segments:
            payload["segments"] = segs  # 원본 세그먼트(큰 편)
        else:
            payload["segments"] = None

        if req.include_natural_segments:
            payload["naturalSegments"] = natural_segments  # 중간 데이터(디버그용)
        else:
            payload["naturalSegments"] = None

        payload["compact"] = compact  # 기본 포함(작게 유지)

        per_video.append(payload)

    return {
        "ok": True,
        "count": len(per_video),
        "perVideo": per_video,
        "config": {
            "enableSTT": ENABLE_STT,
            "skipSTTLongerThanSec": req.skip_stt_if_longer_than_sec,
            "naturalSeg": {
                "pauseGapSec": PAUSE_GAP_SEC,
                "maxSpanSec": MAX_SPAN_SEC,
                "maxSegChars": MAX_SEG_CHARS,
            },
            "compact": {
                "maxScenesPerVideo": MAX_SCENES_PER_VIDEO,
                "maxCharsPerScene": MAX_CHARS_PER_SCENE,
                "includeDurationBucket": req.include_duration_bucket,
            }
        }
    }
