# app/main.py
from __future__ import annotations

import os
import json
import asyncio
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.apify_client import fetch_transcript_and_metadata, ApifyError
from app.gemini_rest import analyze_with_gemini
from app.prompts import build_video_analysis_prompt, build_channel_profile_prompt
from app.utils import normalize_urls, pick_language_priority, compact_text, segments_to_text


app = FastAPI(title="YouTube Transcript + Channel Profile (Apify + Gemini)")

DEFAULT_CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
APIFY_TIMEOUT_SEC = float(os.getenv("APIFY_TIMEOUT_SEC", "120"))
MAX_TRANSCRIPT_CHARS = int(os.getenv("MAX_TRANSCRIPT_CHARS", "18000"))


class AnalyzeReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    concurrency: int = Field(default=DEFAULT_CONCURRENCY, ge=1, le=20)
    make_channel_profile: bool = True


@app.get("/health")
def health():
    return {"ok": True}


def _parse_body_allow_string_json(body: Any) -> Dict[str, Any]:
    """
    n8n Raw에서 JSON.stringify(...) 쓰면 body가 str로 들어오는 경우가 있음.
    """
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
    sem: asyncio.Semaphore,
    lang_priority: List[str],
) -> Dict[str, Any]:
    async with sem:
        apify_data: Optional[Dict[str, Any]] = None
        apify_error: Optional[str] = None
        used_lang: Optional[str] = None

        # 언어 우선순위대로 시도
        for lang in lang_priority:
            try:
                apify_data = await fetch_transcript_and_metadata(
                    youtube_url=url,
                    language=lang,
                    timeout_sec=APIFY_TIMEOUT_SEC,
                    include_transcript_text=True,
                )
                used_lang = lang
                break
            except (ApifyError, Exception) as e:
                apify_error = str(e)

        if not apify_data:
            return {
                "index": idx,
                "url": url,
                "ok": False,
                "stage": "apify",
                "error": apify_error or "Apify failed",
            }

        # transcript_text 우선 사용
        transcript_text = apify_data.get("transcript_text") or ""
        transcript_text = compact_text(transcript_text, max_chars=MAX_TRANSCRIPT_CHARS)

        # 없으면 transcript segments join
        if not transcript_text:
            transcript_text = segments_to_text(
                apify_data.get("transcript"),
                max_chars=MAX_TRANSCRIPT_CHARS,
            )

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
                    "language": apify_data.get("language") or used_lang,
                },
                "error": "NO_TRANSCRIPT_RETURNED_BY_APIFY",
            }

        prompt = build_video_analysis_prompt(
            index=idx,
            title=apify_data.get("title", ""),
            description=(apify_data.get("description", "") or "")[:300],
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
                "language": apify_data.get("language") or used_lang,
            },
            "transcript_chars": len(transcript_text),
            "videoAnalysis": analysis,
        }


def _build_warnings(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    warns: List[Dict[str, Any]] = []
    for v in videos:
        if not v.get("ok"):
            warns.append(
                {
                    "index": v.get("index"),
                    "url": v.get("url"),
                    "stage": v.get("stage"),
                    "error": v.get("error"),
                }
            )
            continue

        va = v.get("videoAnalysis") or {}
        if isinstance(va, dict) and va.get("ok") is False and va.get("error"):
            warns.append(
                {
                    "index": v.get("index"),
                    "url": v.get("url"),
                    "stage": "gemini_video_analysis",
                    "error": va.get("error"),
                }
            )
    return warns


async def _analyze_impl(req: AnalyzeReq) -> Dict[str, Any]:
    urls = normalize_urls(req.urls)
    if not urls:
        raise HTTPException(400, "urls is empty")

    lang_priority = pick_language_priority(req.languages)

    sem = asyncio.Semaphore(req.concurrency)

    tasks = [
        _process_one(i + 1, u, sem, lang_priority)
        for i, u in enumerate(urls)
    ]
    videos = await asyncio.gather(*tasks)

    channel_profile: Optional[Dict[str, Any]] = None
    if req.make_channel_profile:
        analyses: List[Dict[str, Any]] = []
        for v in videos:
            if not v.get("ok"):
                continue
            va = v.get("videoAnalysis")
            if isinstance(va, dict) and va.get("ok") is False:
                continue
            analyses.append(
                {
                    "index": v.get("index"),
                    "url": v.get("url"),
                    "meta": v.get("meta"),
                    "analysis": va,
                }
            )

        if analyses:
            prompt = build_channel_profile_prompt(analyses)
            channel_profile = analyze_with_gemini(prompt, max_output_tokens=2048)
        else:
            channel_profile = {
                "ok": False,
                "error": "No valid per-video analyses to build channel profile",
            }

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

    # n8n 호환: languages_priority -> languages
    if "languages_priority" in body and "languages" not in body:
        body["languages"] = body.get("languages_priority")

    try:
        req = AnalyzeReq(**body)
    except Exception as e:
        raise HTTPException(422, f"Invalid request schema: {str(e)}")

    return await _analyze_impl(req)


# n8n 호환: 예전 노드가 /analyze 로 치는 경우
@app.post("/analyze")
async def analyze(request: Request) -> Dict[str, Any]:
    return await analyze_and_profile(request)
