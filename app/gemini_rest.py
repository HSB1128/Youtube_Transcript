# app/gemini_rest.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if not GEMINI_API_KEY:
    # main에서 호출 시 ok:false로 리턴해도 되고, 여기서 raise 해도 됨
    pass


async def analyze_with_gemini(
    prompt: str,
    model: str = "gemini-2.5-pro",
    max_output_tokens: int = 2048,
    temperature: float = 0.6,
) -> Dict[str, Any]:
    """
    Google AI Studio API Key 방식:
    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=...
    """
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    params = {"key": GEMINI_API_KEY}

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, params=params, json=payload)
    except Exception as e:
        return {"ok": False, "error": f"Gemini request failed: {e}"}

    if r.status_code != 200:
        return {
            "ok": False,
            "error": f"Gemini HTTP {r.status_code}",
            "detail": r.text,
        }

    data = r.json()

    # 응답 텍스트 추출
    try:
        text = (
            data["candidates"][0]["content"]["parts"][0].get("text")
            if data.get("candidates")
            else None
        )
    except Exception:
        text = None

    if not text:
        return {"ok": False, "error": "Gemini returned empty text", "raw": data}

    # 우리가 prompt에서 JSON만 뽑게 유도했다면 여기서 json.loads 시도
    text_stripped = text.strip()
    if text_stripped.startswith("{") and text_stripped.endswith("}"):
        try:
            return {"ok": True, "json": __import__("json").loads(text_stripped)}
        except Exception:
            # JSON parse 실패해도 raw text는 남김
            return {"ok": True, "text": text_stripped, "warning": "JSON_PARSE_FAILED"}

    return {"ok": True, "text": text_stripped}
