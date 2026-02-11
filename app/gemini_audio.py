from __future__ import annotations

import os
from google import genai
from google.genai import types

LOCATION = os.getenv("GEMINI_LOCATION", "us-central1")
MODEL_AUDIO = os.getenv("GEMINI_MODEL_AUDIO", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("PROJECT_ID")
    if not project:
        raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT (or GCP_PROJECT/PROJECT_ID) env var")

    _client = genai.Client(
        vertexai=True,
        project=project,
        location=LOCATION,
    )
    return _client


def transcribe_audio_bytes(*, audio_bytes: bytes, mime_type: str, language_hint: str = "ko") -> dict:
    instruction = (
        "다음 오디오를 가능한 한 정확히 받아쓰기(전사) 하라. "
        "요약/해석/재구성 금지. "
        "말버릇/추임새/반복 표현도 가능한 유지. "
        f"언어 힌트: {language_hint}. "
        "출력은 전사 텍스트만. 마크다운/코드펜스/설명 금지."
    )

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(text=instruction),
                types.Part(
                    inline_data=types.Blob(
                        data=audio_bytes,
                        mime_type=mime_type,
                    )
                ),
            ],
        )
    ]

    client = _get_client()
    resp = client.models.generate_content(model=MODEL_AUDIO, contents=contents)

    return {"ok": True, "model": MODEL_AUDIO, "text": (resp.text or "").strip()}
