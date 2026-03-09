from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote
import httpx


class ApifyError(Exception):
    pass


APIFY_API_BASE = "https://api.apify.com/v2"


def _actor_dataset_sync_endpoint(actor_id: str) -> str:
    """
    actor_id 예:
    - "starvibe~youtube-video-transcript"
    - "starvibe/youtube-video-transcript" -> "~"로 변환
    """
    if "/" in actor_id:
        actor_id = actor_id.replace("/", "~")
    return f"{APIFY_API_BASE}/acts/{actor_id}/run-sync-get-dataset-items"


def _actor_runs_endpoint(actor_id: str) -> str:
    if "/" in actor_id:
        actor_id = actor_id.replace("/", "~")
    return f"{APIFY_API_BASE}/acts/{actor_id}/runs"


def _actor_run_endpoint(run_id: str) -> str:
    return f"{APIFY_API_BASE}/actor-runs/{run_id}"


def _kvs_record_endpoint(store_id: str, record_key: str) -> str:
    return f"{APIFY_API_BASE}/key-value-stores/{store_id}/records/{quote(record_key, safe='')}"


async def fetch_transcript_and_metadata(
    *,
    youtube_url: str,
    language: str,
    timeout_sec: float,
    token: str,
    actor_id: str = "starvibe~youtube-video-transcript",
) -> Dict[str, Any]:
    """
    Apify transcript actor 실행 후 dataset items 반환(JSON array)에서 첫 아이템 뽑아서 표준화 리턴.
    transcript 쪽은 기존 구조 유지.
    """
    if not token:
        raise ApifyError("APIFY_TOKEN is missing")

    endpoint = _actor_dataset_sync_endpoint(actor_id)
    params = {
        "token": token,
        "format": "json",
    }

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

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        item = data[0]
    elif isinstance(data, dict):
        item = data
    else:
        raise ApifyError(f"Apify returned unexpected payload: {type(data)}")

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
        "raw": item,
    }
    return out


async def fetch_audio_bytes_from_converter(
    *,
    youtube_url: str,
    timeout_sec: float,
    token: str,
    actor_id: str = "tazy~youtube-converter",
    cookies_text: str = "",
) -> Dict[str, Any]:
    """
    tazy/youtube-converter actor 문서 기준:
    - 입력: videoUrl, format, quality, cookiesText 등
    - 결과 파일: default key-value store의 OUTPUT_FILE
    """
    if not token:
        raise ApifyError("APIFY_TOKEN is missing")

    runs_endpoint = _actor_runs_endpoint(actor_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "videoUrl": youtube_url,
        "format": "mp3",
        "healthCheck": False,
    }

    if cookies_text.strip():
        payload["cookiesText"] = cookies_text.strip()

    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        # 1) actor run 시작
        run_resp = await client.post(
            runs_endpoint,
            params={"waitForFinish": 60},
            headers=headers,
            json=payload,
        )

        if run_resp.status_code >= 400:
            raise ApifyError(f"Converter run HTTP {run_resp.status_code}: {run_resp.text}")

        run_data = run_resp.json().get("data") or {}
        run_id = run_data.get("id")
        status = run_data.get("status")
        kvs_id = run_data.get("defaultKeyValueStoreId")

        if not run_id:
            raise ApifyError("Converter run response missing run id")

        # 2) 아직 완료 안 됐으면 polling
        poll_count = 0
        while status not in {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}:
            poll_count += 1
            if poll_count > 20:
                raise ApifyError("Converter run polling exceeded limit")

            poll_resp = await client.get(
                _actor_run_endpoint(run_id),
                params={"waitForFinish": 15},
                headers=headers,
            )
            if poll_resp.status_code >= 400:
                raise ApifyError(f"Converter poll HTTP {poll_resp.status_code}: {poll_resp.text}")

            run_data = poll_resp.json().get("data") or {}
            status = run_data.get("status")
            kvs_id = run_data.get("defaultKeyValueStoreId") or kvs_id

        if status != "SUCCEEDED":
            raise ApifyError(f"Converter run did not succeed: status={status}")

        if not kvs_id:
            raise ApifyError("Converter run missing defaultKeyValueStoreId")

        # 3) OUTPUT_FILE 다운로드
        file_resp = await client.get(
            _kvs_record_endpoint(kvs_id, "OUTPUT_FILE"),
            headers={"Authorization": f"Bearer {token}"},
        )

        if file_resp.status_code >= 400:
            raise ApifyError(f"Failed to fetch OUTPUT_FILE {file_resp.status_code}: {file_resp.text[:300]}")

        content_type = (file_resp.headers.get("content-type") or "").split(";")[0].strip()
        data = file_resp.content

    if not data:
        raise ApifyError("OUTPUT_FILE is empty")

    return {
        "bytes": data,
        "mime_type": content_type or "audio/mpeg",
        "size": len(data),
        "run_id": run_id,
        "default_key_value_store_id": kvs_id,
    }
