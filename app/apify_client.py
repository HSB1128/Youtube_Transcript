# app/apify_client.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional
import httpx

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "starvibe~youtube-video-transcript").strip()

# Apify run-sync-get-dataset-items endpoint
APIFY_BASE = "https://api.apify.com"

class ApifyError(RuntimeError):
    pass

async def fetch_transcript_and_metadata(
    client: httpx.AsyncClient,
    youtube_url: str,
    language: Optional[str] = None,
    timeout_sec: float = 120.0,
) -> Dict[str, Any]:
    """
    Apify Actor 실행(동기) -> dataset items 받기.
    반환은 actor output item 1개(보통 1개) 기준으로 정리해서 리턴.

    참고: run-sync-get-dataset-items는 Actor 실행이 끝나야 응답이 오며,
    오래 걸리면 HTTP가 timeout 될 수 있음. (run은 계속 돌 수 있음)
    """
    if not APIFY_TOKEN:
        raise ApifyError("APIFY_TOKEN is missing")

    url = f"{APIFY_BASE}/v2/acts/{APIFY_ACTOR_ID}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN}

    # Actor input schema에 맞춰 최소 필드만 구성
    payload: Dict[str, Any] = {
        "youtube_url": youtube_url,
        "include_transcript_text": True,  # Gemini에 넣기 좋은 transcript_text 우선
    }
    if language:
        payload["language"] = language

    try:
        r = await client.post(url, params=params, json=payload, timeout=timeout_sec)
        r.raise_for_status()
        items = r.json()
    except httpx.HTTPStatusError as e:
        raise ApifyError(f"Apify HTTP error: {e.response.status_code} {e.response.text[:500]}")
    except Exception as e:
        raise ApifyError(f"Apify request failed: {str(e)}")

    if not isinstance(items, list) or len(items) == 0:
        # actor가 dataset에 아무것도 안 쌓았거나 형식이 다를 때
        raise ApifyError("Apify returned empty dataset items")

    # 보통 1개 아이템이 온다고 가정
    it = items[0]
    if not isinstance(it, dict):
        raise ApifyError("Apify item is not an object")

    # Apify output-schema의 키들은 actor 버전에 따라 조금씩 다를 수 있으니
    # 원본을 그대로 meta로 남기고, 우리가 쓰는 필드만 추출해서 붙임.
    out: Dict[str, Any] = {
        "ok": True,
        "url": youtube_url,
        "apify_raw": it,
        "title": it.get("title") or "",
        "description": it.get("description") or "",
        "channel_name": it.get("channel_name") or it.get("channelTitle") or "",
        "published_at": it.get("published_at") or it.get("publishedAt") or "",
        "duration_seconds": it.get("duration_seconds") or it.get("durationSec") or None,
        "view_count": it.get("view_count") or None,
        "like_count": it.get("like_count") or None,
        "comment_count": it.get("comment_count") or None,
        "transcript_text": it.get("transcript_text") or "",
        "transcript": it.get("transcript") or [],
        "language": it.get("language") or language,
    }
    return out
