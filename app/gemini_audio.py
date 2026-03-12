from __future__ import annotations

import os
from google import genai
from google.genai import types

MODEL_AUDIO = os.getenv("GEMINI_MODEL_AUDIO", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY env var")

    _client = genai.Client(api_key=api_key)
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
