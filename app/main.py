# app/main.py
from __future__ import annotations

import os, asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import httpx

from app.apify_client import fetch_transcript_and_metadata, ApifyError
from app.gemini import analyze_with_gemini
from app.prompts import build_video_analysis_prompt, build_channel_profile_prompt
from app.utils import normalize_urls, pick_language_priority, compact_text, segments_to_text

app = FastAPI(title="YouTube Transcript + Channel Profile (Apify + Gemini)")

DEFAULT_CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
APIFY_TIMEOUT_SEC = float(os.getenv("APIFY_TIMEOUT_SEC", "120"))  # 영상 1개당 Apify 대기 시간
MAX_TRANSCRIPT_CHARS = int(os.getenv("MAX_TRANSCRIPT_CHARS", "18000"))  # Gemini 입력 보호

class AnalyzeReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    concurrency: int = Field(default=DEFAULT_CONCURRENCY, ge=1, le=20)
    make_channel_profile: bool = True

@app.get("/health")
def health():
    return {"ok": True}

async def _process_one(
    idx: int,
    url: str,
    lang_priority: List[str],
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
) -> Dict[str, Any]:
    """
    영상 1개 처리:
    - Apify로 메타+자막
    - transcript_text 만들어서 Gemini로 영상별 분석 JSON
    """
    async with sem:
        # 1) Apify 호출 (언어 우선순위 순서대로 한 번씩만 시도)
        apify_data: Optional[Dict[str, Any]] = None
        apify_error: Optional[str] = None

        for lang in lang_priority:
            try:
                apify_data = await fetch_transcript_and_metadata(
                    client=client,
                    youtube_url=url,
                    language=lang,
                    timeout_sec=APIFY_TIMEOUT_SEC,
                )
                apify_error = None
                break
            except ApifyError as e:
                apify_error = str(e)
                continue

        if not apify_data:
            return {
                "index": idx,
                "url": url,
                "ok": False,
                "stage": "apify",
                "error": apify_error or "Apify failed",
            }

        # 2) transcript_text 우선, 없으면 transcript segments join
        transcript_text = apify_data.get("transcript_text") or ""
        transcript_text = compact_text(transcript_text, max_chars=MAX_TRANSCRIPT_CHARS)

        if not transcript_text:
            transcript_text = segments_to_text(apify_data.get("transcript"), max_chars=MAX_TRANSCRIPT_CHARS)

        if not transcript_text:
            return {
                "index": idx,
                "url": url,
                "ok": False,
                "stage": "transcript",
                "meta": {
                    "title": apify_data.get("title", ""),
                    "channel": apify_data.get("channel_name", ""),
                    "published_at": apify_data.get("published_at", ""),
                },
                "error": "NO_TRANSCRIPT_RETURNED_BY_APIFY",
            }

        # 3) Gemini 영상별 분석
        prompt = build_video_analysis_prompt(
            index=idx,
            title=apify_data.get("title", ""),
            description=apify_data.get("description", "")[:300],
            transcript_text=transcript_text,
        )
        analysis = analyze_with_gemini(prompt, max_output_tokens=2048)

        return {
            "index": idx,
            "url": url,
            "ok": True,
            "meta": {
                "title": apify_data.get("title", ""),
                "description": apify_data.get("description", ""),
                "channel": apify_data.get("channel_name", ""),
                "published_at": apify_data.get("published_at", ""),
                "duration_seconds": apify_data.get("duration_seconds"),
                "view_count": apify_data.get("view_count"),
                "like_count": apify_data.get("like_count"),
                "comment_count": apify_data.get("comment_count"),
                "language": apify_data.get("language"),
            },
            "transcript_chars": len(transcript_text),
            "videoAnalysis": analysis,
        }

def _build_warnings(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    warns = []
    for v in videos:
        if not v.get("ok"):
            warns.append({
                "index": v.get("index"),
                "url": v.get("url"),
                "stage": v.get("stage"),
                "error": v.get("error"),
            })
        else:
            # Gemini JSON 실패도 경고로 올려두면 운영이 편함
            va = v.get("videoAnalysis") or {}
            if isinstance(va, dict) and va.get("ok") is False and va.get("error"):
                warns.append({
                    "index": v.get("index"),
                    "url": v.get("url"),
                    "stage": "gemini_video_analysis",
                    "error": va.get("error"),
                })
    return warns

@app.post("/analyze_and_profile")
async def analyze_and_profile(req: AnalyzeReq) -> Dict[str, Any]:
    urls = normalize_urls(req.urls)
    if not urls:
        raise HTTPException(400, "urls is empty")

    lang_priority = pick_language_priority(req.languages)
    sem = asyncio.Semaphore(req.concurrency)

    async with httpx.AsyncClient() as client:
        tasks = [
            _process_one(i + 1, url, lang_priority, sem, client)
            for i, url in enumerate(urls)
        ]
        videos = await asyncio.gather(*tasks)

    # 1) 채널 프로필 생성(성공+Gemini JSON 정상인 것 위주로)
    channel_profile: Optional[Dict[str, Any]] = None
    if req.make_channel_profile:
        # 영상 분석이 JSON으로 성공한 것만 모으기
        analyses: List[Dict[str, Any]] = []
        for v in videos:
            if not v.get("ok"):
                continue
            va = v.get("videoAnalysis")
            if isinstance(va, dict) and va.get("ok") is False:
                continue
            analyses.append({
                "index": v.get("index"),
                "url": v.get("url"),
                "meta": v.get("meta"),
                "analysis": va,
            })

        if analyses:
            prompt = build_channel_profile_prompt(analyses)
            channel_profile = analyze_with_gemini(prompt, max_output_tokens=2048)
        else:
            channel_profile = {
                "ok": False,
                "error": "No valid per-video analyses to build channel profile"
            }

    warnings = _build_warnings(videos)

    return {
        "ok": True,
        "count": len(videos),
        "videos": videos,
        "channelProfile": channel_profile,
        "warnings": warnings,
    }

# 과거 n8n이 /analyze를 치던 호환용
@app.post("/analyze")
async def analyze(req: AnalyzeReq) -> Dict[str, Any]:
    return await analyze_and_profile(req)
