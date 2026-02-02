from __future__ import annotations
from typing import Any, Dict, Optional
import os
import httpx


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()


def analyze_with_gemini(prompt: str, max_output_tokens: int = 2048) -> Dict[str, Any]:
    """
    Google AI Studio (Gemini API) REST 직호출.
    API Key는 x-goog-api-key 헤더로 전달. :contentReference[oaicite:5]{index=5}
    """
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": max_output_tokens,
        },
    }

    try:
        r = httpx.post(
            url,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        if r.status_code >= 400:
            return {"ok": False, "error": f"Gemini HTTP {r.status_code}", "detail": r.text[:4000]}

        data = r.json()

        # 텍스트만 뽑기 (후처리에서 JSON 파싱)
        text = ""
        candidates = data.get("candidates") or []
        if candidates:
            parts = (((candidates[0].get("content") or {}).get("parts")) or [])
            if parts and isinstance(parts, list):
                text = (parts[0].get("text") or "").strip()

        if not text:
            return {"ok": False, "error": "Gemini returned empty text", "raw": data}

        # "반드시 JSON만" 프롬프트를 줬으니 JSON 파싱 시도
        import json
        try:
            return json.loads(text)
        except Exception:
            return {"ok": False, "error": "Gemini output not valid JSON", "raw": text[:4000]}

    except Exception as e:
        return {"ok": False, "error": f"Gemini call failed: {str(e)}"}
