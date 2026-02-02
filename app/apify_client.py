# app/apify_client.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx


class ApifyError(Exception):
    pass


APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
if not APIFY_TOKEN:
    # Cloud Run에서 env 없으면 바로 죽게 하고 싶다면 여기서 raise 해도 됨
    pass

# 이 actor는 OpenAPI에서 이렇게 정의됨:
# POST /v2/acts/starvibe~youtube-video-transcript/run-sync-get-dataset-items?token=...
APIFY_ACTOR = os.getenv("APIFY_ACTOR", "starvibe~youtube-video-transcript").strip()
APIFY_BASE = "https://api.apify.com/v2"


async def fetch_transcript_and_metadata(
    youtube_url: str,
    language: str = "ko",
    timeout_sec: float = 120.0,
) -> Optional[Dict[str, Any]]:
    if not APIFY_TOKEN:
        raise ApifyError("APIFY_TOKEN is missing")

    # ✅ input schema: youtube_url / language / include_transcript_text ...
    payload = {
        "youtube_url": youtube_url,
        "language": language,
        "include_transcript_text": True,  # transcript_text 받기
        "include_transcript": True,       # timestamps 포함 segments도 받기(혹시 transcript_text 비면 대비)
        "include_video_details": True,    # 메타(조회수/좋아요 등)
    }

    url = f"{APIFY_BASE}/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN}

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(url, params=params, json=payload)
    except Exception as e:
        raise ApifyError(f"Apify request failed: {e}")

    if r.status_code != 200:
        raise ApifyError(f"Apify HTTP {r.status_code}: {r.text}")

    data = r.json()
    # run-sync-get-dataset-items는 "items 배열"이 오는 형태가 일반적
    # actor 구현에 따라 [{...}] 또는 {"items":[...]} 둘 다 방어
    if isinstance(data, dict) and "items" in data:
        items = data.get("items") or []
        if items:
            return _normalize_item(items[0])
        return None

    if isinstance(data, list) and len(data) > 0:
        return _normalize_item(data[0])

    return None


def _normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    actor 결과 필드명이 바뀌어도 main.py에서 쓰기 좋게 normalize
    (네가 이미 meta 잘 뽑히던 형태 유지)
    """
    # transcript_text / transcript(segments)는 actor가 주는 그대로 받아두기
    out = dict(item)

    # 흔한 키들에 대해 alias 처리(없으면 그냥 "")
    out["title"] = out.get("title") or out.get("video_title") or ""
    out["description"] = out.get("description") or out.get("video_description") or ""
    out["channel_name"] = out.get("channel_name") or out.get("channel") or out.get("author") or ""
    out["published_at"] = out.get("published_at") or out.get("upload_date") or ""

    # 숫자 메타
    out["duration_seconds"] = out.get("duration_seconds") or out.get("duration") or None
    out["view_count"] = out.get("view_count") or out.get("views") or None
    out["like_count"] = out.get("like_count") or out.get("likes") or None
    out["comment_count"] = out.get("comment_count") or out.get("comments") or None

    return out
