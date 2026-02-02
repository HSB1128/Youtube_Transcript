from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple
import httpx


class ApifyError(Exception):
    pass


def _actor_endpoint(actor_id: str) -> str:
    """
    actor_id 예:
    - "starvibe~youtube-video-transcript"
    - "starvibe/youtube-video-transcript"  -> "~"로 변환
    """
    if "/" in actor_id:
        actor_id = actor_id.replace("/", "~")
    return f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"


async def fetch_transcript_and_metadata(
    *,
    youtube_url: str,
    language: str,
    timeout_sec: float,
    token: str,
    actor_id: str = "starvibe~youtube-video-transcript",
) -> Dict[str, Any]:
    """
    Apify actor 실행 후 dataset items 반환(JSON array)에서 첫 아이템 뽑아서 표준화 리턴.
    """
    if not token:
        raise ApifyError("APIFY_TOKEN is missing")

    endpoint = _actor_endpoint(actor_id)
    params = {
        "token": token,
        # format을 json으로 명시(안 써도 되지만 명확히)
        "format": "json",
    }

    # ✅ actor input schema 기준 (include_transcript는 없음)
    # youtube_url / language / include_transcript_text 만 보냄
    payload = {
        "youtube_url": youtube_url,
        "language": language,
        "include_transcript_text": True,
    }

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        r = await client.post(endpoint, params=params, json=payload)

    if r.status_code >= 400:
        raise ApifyError(f"Apify HTTP {r.status_code}: {r.text}")

    data = r.json()

    # run-sync-get-dataset-items는 dataset items(보통 list) 리턴
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        item = data[0]
    elif isinstance(data, dict):
        # 혹시나 다른 형태면 그대로
        item = data
    else:
        raise ApifyError(f"Apify returned unexpected payload: {type(data)}")

    # 예상되는 키들을 최대한 흡수해서 표준화
    transcript = item.get("transcript") or item.get("captions") or item.get("segments")
    transcript_text = item.get("transcript_text") or item.get("transcriptText") or item.get("text") or ""

    out = {
        "title": item.get("title") or "",
        "description": item.get("description") or "",
        "channel_name": item.get("channel_name") or item.get("channelName") or item.get("channel") or "",
        "published_at": item.get("published_at") or item.get("publishedAt") or "",
        "duration_seconds": item.get("duration_seconds") or item.get("duration") or None,
        "view_count": item.get("view_count") or item.get("views") or None,
        "like_count": item.get("like_count") or item.get("likes") or None,
        "comment_count": item.get("comment_count") or item.get("commentsCount") or None,
        "language": item.get("language") or language,
        "transcript": transcript if transcript else [],
        "transcript_text": transcript_text if isinstance(transcript_text, str) else "",
        "raw": item,  # 디버깅용
    }
    return out
