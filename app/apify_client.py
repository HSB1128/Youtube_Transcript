# app/apify_client.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx


class ApifyError(Exception):
    pass


APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
APIFY_TIMEOUT_SEC = float(os.getenv("APIFY_TIMEOUT_SEC", "120"))

# starvibe/youtube-video-transcript
# run-sync-get-dataset-items : actor 실행 완료까지 기다리고 dataset items 반환
APIFY_RUN_SYNC_GET_DATASET_ITEMS_URL = (
    "https://api.apify.com/v2/acts/starvibe~youtube-video-transcript/run-sync-get-dataset-items"
)


async def fetch_transcript_and_metadata(
    youtube_url: str,
    language: str,
    *,
    timeout_sec: float = APIFY_TIMEOUT_SEC,
    include_transcript_text: bool = True,
) -> Dict[str, Any]:
    """
    Apify Actor 호출.
    - 입력 스키마: youtube_url, language, include_transcript_text (include_transcript 없음!)
    - 응답: dataset items (list). single video면 보통 list 길이 1
    """
    if not APIFY_TOKEN:
        raise ApifyError("APIFY_TOKEN is missing")

    payload = {
        "youtube_url": youtube_url,
        "language": language,
        "include_transcript_text": bool(include_transcript_text),
    }

    params = {"token": APIFY_TOKEN}  # query param 방식

    timeout = httpx.Timeout(timeout_sec, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            APIFY_RUN_SYNC_GET_DATASET_ITEMS_URL,
            params=params,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    if r.status_code >= 400:
        raise ApifyError(f"Apify HTTP {r.status_code}: {r.text}")

    # run-sync-get-dataset-items는 "dataset items"를 반환
    data = r.json()

    # 보통 list (items)로 오는데, 혹시 dict로 감싸져도 안전하게 처리
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        items = data["items"]
    else:
        raise ApifyError(f"Unexpected Apify response type: {type(data)}")

    if not items:
        raise ApifyError("Apify returned empty dataset items")

    # single video면 첫 아이템
    item = items[0]
    if not isinstance(item, dict):
        raise ApifyError("Apify dataset item is not an object")

    return item
