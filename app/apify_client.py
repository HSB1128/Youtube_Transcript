from __future__ import annotations
import os
from typing import Any, Dict, Optional
import httpx

class ApifyError(Exception):
    pass

APIFY_TOKEN = (os.getenv("APIFY_TOKEN") or "").strip()
APIFY_TIMEOUT_SEC = float(os.getenv("APIFY_TIMEOUT_SEC", "120"))

# starvibe/youtube-video-transcript
# run-sync-get-dataset-items는 실행 완료까지 기다렸다가 dataset items를 바로 응답으로 줌.
APIFY_ACTOR_RUN_SYNC_DATASET_ITEMS = (
    "https://api.apify.com/v2/acts/starvibe~youtube-video-transcript/"
    "run-sync-get-dataset-items"
)

async def fetch_transcript_and_metadata(
    youtube_url: str,
    language: str,
    timeout_sec: float = APIFY_TIMEOUT_SEC,
) -> Dict[str, Any]:
    if not APIFY_TOKEN:
        raise ApifyError("APIFY_TOKEN is missing")

    payload = {
        # 입력 스키마는 Apify actor 문서 기준 (youtubeUrl, language, includeTranscriptText 등)
        "youtubeUrl": youtube_url,
        "language": language,
        "includeTranscriptText": True,
    }

    params = {
        "token": APIFY_TOKEN,
        "format": "json",
        # actor에 따라 timeout이 길어질 수 있어서 http client timeout을 넉넉히
    }

    timeout = httpx.Timeout(timeout_sec, connect=20.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(APIFY_ACTOR_RUN_SYNC_DATASET_ITEMS, params=params, json=payload)
        if r.status_code >= 400:
            raise ApifyError(f"Apify HTTP {r.status_code}: {r.text[:1000]}")

        data = r.json()

    # dataset items 형태는 보통 배열. (아이템 1개만 온다고 가정하고 첫번째 사용)
    if isinstance(data, list) and data:
        item = data[0]
    elif isinstance(data, dict):
        item = data
    else:
        item = {}

    # 통일된 키로 정리해서 리턴
    # (actor output 스키마에 따라 필드명 약간 다를 수 있어서 여러 후보를 같이 체크)
    out: Dict[str, Any] = {
        "title": item.get("title") or item.get("videoTitle") or "",
        "description": item.get("description") or item.get("videoDescription") or "",
        "channel_name": item.get("channelName") or item.get("channel") or "",
        "published_at": item.get("publishedAt") or item.get("published_at") or "",
        "duration_seconds": item.get("durationSeconds") or item.get("duration") or None,
        "view_count": item.get("viewCount") or None,
        "like_count": item.get("likeCount") or None,
        "comment_count": item.get("commentCount") or None,
        "language": item.get("language") or language,
        # transcript_text 우선
        "transcript_text": item.get("transcriptText") or item.get("transcript_text") or "",
        # segments 형태도 혹시 있으니 같이 보관
        "transcript": item.get("transcript") or item.get("segments") or None,
        "raw": item,
    }
    return out
