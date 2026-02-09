from __future__ import annotations

import os
import json
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.apify_client import fetch_transcript_and_metadata, ApifyError
from app.gemini_rest import analyze_with_gemini
from app.prompts import build_video_analysis_prompt, build_channel_profile_prompt, build_json_repair_prompt
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


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    videoAnalysis.text가 '순수 JSON'일 수도 있고,
    혹시라도 코드펜스가 섞일 수도 있으니 (방어적으로) 둘 다 처리.
    """
    if not text:
        return None
    t = text.strip()

    # 1) ```json ... ``` 우선 추출
    if "```" in t:
        import re
        m = re.search(r"```json\s*([\s\S]*?)```", t, re.IGNORECASE)
        if m:
            t = m.group(1).strip()
        else:
            m2 = re.search(r"```\s*([\s\S]*?)```", t)
            if m2:
                t = m2.group(1).strip()

    # 2) JSON 파싱
    try:
        return json.loads(t)
    except Exception:
        return None


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
            transcript_text = segments_to_text(
                apify_data.get("transcript"),
                max_chars=MAX_TRANSCRIPT_CHARS
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

        # 3) Gemini 영상별 분석 (JSON 보장: 실패하면 1회 복구 시도)
        analysis_text = ""
        try:
            prompt = build_video_analysis_prompt(
                index=idx,
                title=meta.get("title", ""),
                description=(meta.get("description", "") or "")[:300],
                transcript_text=transcript_text,
            )
            first = await asyncio.to_thread(
                analyze_with_gemini,
                prompt,
                max_output_tokens=2048
            )
            analysis_text = (first.get("text") or "").strip()

            # 1차 JSON 파싱 검사
            parsed = _extract_json_from_text(analysis_text)

            # 실패하면 1회 복구 시도
            if parsed is None:
                repair_prompt = build_json_repair_prompt(
                    schema_name="video_analysis",
                    raw_text=analysis_text[:6000],
                )
                second = await asyncio.to_thread(
                    analyze_with_gemini,
                    repair_prompt,
                    max_output_tokens=2048
                )
                analysis_text = (second.get("text") or "").strip()

                # 2차 파싱 재검사
                parsed2 = _extract_json_from_text(analysis_text)
                if parsed2 is None:
                    raise ValueError("Gemini output is not valid JSON even after repair")

            analysis = {"ok": True, "text": analysis_text}

        except Exception as e:
            analysis = {"ok": False, "error": str(e), "text": analysis_text[:1200]}

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

            text = (va.get("text") or "").strip()

            # 1) 영상별 분석 JSON 파싱 시도
            parsed = _extract_json_from_text(text)

            # 2) 필요한 필드만 축약 (채널 프로필에 필요한 '형식 DNA'만)
            if isinstance(parsed, dict) and parsed.get("ok") is True:
                hook = parsed.get("hook") or {}
                structure = parsed.get("structure") or {}
                style_tone = parsed.get("style_tone") or {}
                expression_markers = parsed.get("expression_markers") or {}
                retention = parsed.get("retention") or {}
                quotes = parsed.get("quotes") or {"items": []}

                slim = {
                    "video_index": parsed.get("video_index"),
                    "hook": {
                        "summary": hook.get("summary"),
                        "techniques": hook.get("techniques") or [],
                        "frames": hook.get("frames") or [],
                    },
                    "structure": {
                        "template": structure.get("template"),
                        "beats": structure.get("beats") or [],
                        "pacing": structure.get("pacing"),
                    },
                    "style_tone": {
                        "persona": style_tone.get("persona"),
                        "narration_style": style_tone.get("narration_style"),
                        "tone_keywords": style_tone.get("tone_keywords") or [],
                    },
                    "expression_markers": {
                        "punctuation": expression_markers.get("punctuation") or [],
                        "catchphrases": expression_markers.get("catchphrases") or [],
                        "rhythm": expression_markers.get("rhythm"),
                        "numbers_style": expression_markers.get("numbers_style"),
                    },
                    "retention": {
                        "recurring_devices": retention.get("recurring_devices") or [],
                        "cta": retention.get("cta"),
                    },
                    "quotes": quotes,
                }
            else:
                # 파싱 실패 시 최소정보만 남겨서 넣기(길이 폭발 방지)
                slim = {"raw_text": text[:1200]}

            analyses.append({
                "index": v.get("index"),
                "url": v.get("url") or "",
                "meta": {
                    "title": (v.get("meta") or {}).get("title", ""),
                    "channel": (v.get("meta") or {}).get("channel", ""),
                    "published_at": (v.get("meta") or {}).get("published_at", ""),
                    "language": (v.get("meta") or {}).get("language", ""),
                },
                "dna": slim,
            })

        if analyses:
            try:
                analyses_json = json.dumps(analyses, ensure_ascii=False)
                prompt = build_channel_profile_prompt(analyses_json)
                channel_profile = await asyncio.to_thread(
                    analyze_with_gemini,
                    prompt,
                    max_output_tokens=2048
                )
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
