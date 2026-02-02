from __future__ import annotations

import os
import json
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.apify_client import fetch_transcript_and_metadata, ApifyError
from app.gemini_rest import analyze_with_gemini, GeminiError
from app.prompts import build_video_analysis_prompt, build_channel_profile_prompt
from app.utils import normalize_urls, pick_language_priority, compact_text, segments_to_text

app = FastAPI(title="YouTube Transcript + Channel Profile (Apify + Gemini)")

DEFAULT_CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
APIFY_TIMEOUT_SEC = float(os.getenv("APIFY_TIMEOUT_SEC", "120"))
MAX_TRANSCRIPT_CHARS = int(os.getenv("MAX_TRANSCRIPT_CHARS", "18000"))
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()


class AnalyzeReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    concurrency: int = Field(default=DEFAULT_CONCURRENCY, ge=1, le=20)
    make_channel_profile: bool = True


@app.get("/health")
def health():
    return {"ok": True}


def _parse_body_allow_string_json(body: Any) -> Dict[str, Any]:
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            raise HTTPException(400, "Body was a string but not valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    return body


async def _process_one(
    idx: int,
    url: str,
    lang_priority: List[str],
    sem: asyncio.Semaphore,
) -> Dict[str, Any]:
    async with sem:
        # 1) Apify (언어 우선순위대로 시도)
        apify_data: Optional[Dict[str, Any]] = None
        apify_error: Optional[str] = None

        for lang in lang_priority:
            try:
                apify_data = await fetch_transcript_and_metadata(
                    youtube_url=url,
                    language=lang,
                    timeout_sec=APIFY_TIMEOUT_SEC,
                    token=APIFY_TOKEN,
                    actor_id="starvibe~youtube-video-transcript",
                )
                apify_error = None
                break
            except Exception as e:
                apify_error = str(e)
                apify_data = None

        if not apify_data:
            return {
                "index": idx,
                "url": url,
                "ok": False,
                "stage": "apify",
                "error": apify_error or "Apify failed",
            }

        # 2) transcript_text 우선, 없으면 segments join
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
                    "language": apify_data.get("language"),
                },
                "error": "NO_TRANSCRIPT_RETURNED_BY_APIFY",
            }

        meta = {
            "title": apify_data.get("title", ""),
            "description": apify_data.get("description", ""),
            "channel": apify_data.get("channel_name", ""),
            "published_at": apify_data.get("published_at", ""),
            "duration_seconds": apify_data.get("duration_seconds"),
            "view_count": apify_data.get("view_count"),
            "like_count": apify_data.get("like_count"),
            "comment_count": apify_data.get("comment_count"),
            "language": apify_data.get("language"),
        }

        # 3) Gemini 영상별 분석
        try:
            prompt = build_video_analysis_prompt(
                index=idx,
                title=meta.get("title", ""),
                description=(meta.get("description", "") or "")[:300],
                transcript_text=transcript_text,
            )
            analysis = await analyze_with_gemini(prompt, max_output_tokens=2048)
        except Exception as e:
            analysis = {"ok": False, "error": str(e)}

        return {
            "index": idx,
            "url": url,
            "ok": True,  # Apify/transcript는 성공했으니 True 유지
            "meta": meta,
            "transcript_chars": len(transcript_text),
            "videoAnalysis": analysis,
        }


def _build_warnings(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    warns: List[Dict[str, Any]] = []
    for v in videos:
        if not v.get("ok"):
            warns.append({
                "index": v.get("index"),
                "url": v.get("url"),
                "stage": v.get("stage"),
                "error": v.get("error"),
            })
            continue

        va = v.get("videoAnalysis") or {}
        if isinstance(va, dict) and va.get("ok") is False:
            warns.append({
                "index": v.get("index"),
                "url": v.get("url"),
                "stage": "gemini_video_analysis",
                "error": va.get("error"),
            })
    return warns


async def _analyze_impl(req: AnalyzeReq) -> Dict[str, Any]:
    urls = normalize_urls(req.urls)
    if not urls:
        raise HTTPException(400, "urls is empty")

    lang_priority = pick_language_priority(req.languages)
    sem = asyncio.Semaphore(req.concurrency)

    tasks = [
        _process_one(i + 1, u, lang_priority, sem)
        for i, u in enumerate(urls)
    ]
    videos = await asyncio.gather(*tasks)

    # 채널 프로필 (Gemini 영상 분석이 ok=true인 것만 모아서)
    channel_profile: Optional[Dict[str, Any]] = None
    if req.make_channel_profile:
        analyses: List[Dict[str, Any]] = []
        for v in videos:
            if not v.get("ok"):
                continue
            va = v.get("videoAnalysis")
            if not isinstance(va, dict) or va.get("ok") is False:
                continue
            analyses.append({
                "index": v.get("index"),
                "url": v.get("url"),
                "meta": v.get("meta"),
                "analysis": va.get("text") or va,
            })

        if analyses:
            try:
                prompt = build_channel_profile_prompt(analyses)
                channel_profile = await analyze_with_gemini(prompt, max_output_tokens=2048)
            except Exception as e:
                channel_profile = {"ok": False, "error": str(e)}
        else:
            channel_profile = {"ok": False, "error": "No valid per-video analyses to build channel profile"}

    warnings = _build_warnings(videos)

    return {
        "ok": True,
        "count": len(videos),
        "videos": videos,
        "channelProfile": channel_profile,
        "warnings": warnings,
    }


@app.post("/analyze_and_profile")
async def analyze_and_profile(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    body = _parse_body_allow_string_json(body)

    # 호환: urls가 문자열로 오면 split을 normalize_urls가 처리함
    # 호환: languages_priority -> languages
    if "languages_priority" in body and "languages" not in body:
        body["languages"] = body.get("languages_priority")

    try:
        req = AnalyzeReq(**body)
    except Exception as e:
        raise HTTPException(422, f"Invalid request schema: {str(e)}")

    return await _analyze_impl(req)


# n8n 호환: /analyze 로 보내도 동일 처리
@app.post("/analyze")
async def analyze(request: Request) -> Dict[str, Any]:
    return await analyze_and_profile(request)
