from __future__ import annotations

import os
from typing import Any, Dict, Optional
import httpx


class GeminiError(Exception):
    pass


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()


async def analyze_with_gemini(
    prompt: str,
    *,
    model: Optional[str] = None,
    max_output_tokens: int = 2048,
    temperature: float = 0.2,
    timeout_sec: float = 120.0,
) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is missing")

    use_model = (model or GEMINI_MODEL).strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent"

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    body = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        r = await client.post(url, headers=headers, json=body)

    if r.status_code >= 400:
        # 그대로 반환해서 디버깅 가능하게
        raise GeminiError(f"Gemini HTTP {r.status_code}: {r.text}")

    data = r.json()

    # 텍스트 뽑기 (후처리에서 쓰기 쉽도록 text도 같이 넣어줌)
    text = ""
    try:
        cands = data.get("candidates") or []
        if cands:
            parts = cands[0].get("content", {}).get("parts", [])
            if parts and isinstance(parts[0], dict):
                text = parts[0].get("text", "") or ""
    except Exception:
        text = ""

    return {"ok": True, "model": use_model, "text": text, "raw": data}
