from __future__ import annotations
from typing import Any, Dict, Optional
import os
import httpx


class ApifyError(Exception):
    pass


APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
APIFY_TIMEOUT_SEC = float(os.getenv("APIFY_TIMEOUT_SEC", "120"))
APIFY_ACTOR = os.getenv("APIFY_ACTOR", "starvibe/youtube-video-transcript").strip()


def _must_token():
    if not APIFY_TOKEN:
        raise ApifyError("APIFY_TOKEN is missing")


async def fetch_transcript_and_metadata(
    youtube_url: str,
    language: str = "ko",
    timeout_sec: float = APIFY_TIMEOUT_SEC,
) -> Dict[str, Any]:
    """
    Apify Actor를 동기 실행하고 dataset items를 바로 받는다.
    - 입력 key는 youtube_url (snake_case) 여야 함. :contentReference[oaicite:4]{index=4}
    """
    _must_token()

    url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
    params = {
        "token": APIFY_TOKEN,
        "timeout": int(timeout_sec),
        # 필요하면 dataset items 포맷도 조절 가능:
        # "format": "json"
    }

    payload = {
        "youtube_url": youtube_url,
        "language": language,
    }

    async with httpx.AsyncClient(timeout=timeout_sec + 30) as client:
        r = await client.post(url, params=params, json=payload)
        if r.status_code >= 400:
            raise ApifyError(f"Apify HTTP {r.status_code}: {r.text}")

        items = r.json()
        # Actor마다 items 구조가 다를 수 있는데, 보통 list[dict]
        if not isinstance(items, list) or not items:
            return {
                "ok": False,
                "error": "EMPTY_DATASET_ITEMS",
                "raw": items,
            }

        it = items[0] if isinstance(items[0], dict) else {}
        # 최대한 유연하게 매핑 (필드명이 약간 달라도 대비)
        transcript_text = it.get("transcript_text") or it.get("transcript") or ""
        # transcript가 list segments일 수도 있음
        transcript_segments = it.get("transcript") if isinstance(it.get("transcript"), list) else None

        return {
            "ok": True,
            "title": it.get("title") or it.get("video_title") or "",
            "description": it.get("description") or "",
            "channel_name": it.get("channel") or it.get("channel_name") or "",
            "published_at": it.get("published_at") or it.get("publishedAt") or "",
            "duration_seconds": it.get("duration_seconds") or it.get("duration") or 0,
            "view_count": it.get("view_count") or 0,
            "like_count": it.get("like_count") or 0,
            "comment_count": it.get("comment_count") or 0,
            "language": it.get("language") or language,
            "transcript_text": transcript_text if isinstance(transcript_text, str) else "",
            "transcript": transcript_segments,
            "raw": it,
        }
