from __future__ import annotations

import os
import mimetypes
import httpx


class AudioDownloadError(Exception):
    pass


# 너무 큰 파일 방지(바이트). 필요하면 env로 조절.
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(60 * 1024 * 1024)))  # 기본 60MB
AUDIO_TIMEOUT_SEC = float(os.getenv("AUDIO_TIMEOUT_SEC", "240"))


def _guess_mime(url: str) -> str:
    path = url.split("?")[0]
    mime = mimetypes.guess_type(path)[0]
    return mime or "audio/mpeg"


async def download_audio_bytes(*, audio_url: str) -> dict:
    if not audio_url:
        raise AudioDownloadError("audio_url is empty")

    mime_type = _guess_mime(audio_url)

    async with httpx.AsyncClient(timeout=AUDIO_TIMEOUT_SEC, follow_redirects=True) as client:
        r = await client.get(audio_url)
        if r.status_code >= 400:
            raise AudioDownloadError(f"Audio download failed {r.status_code}: {r.text[:200]}")
        data = r.content

    if MAX_AUDIO_BYTES and len(data) > MAX_AUDIO_BYTES:
        raise AudioDownloadError(
            f"Audio too large: {len(data)} bytes > MAX_AUDIO_BYTES={MAX_AUDIO_BYTES}"
        )

    return {"bytes": data, "mime_type": mime_type, "size": len(data)}
