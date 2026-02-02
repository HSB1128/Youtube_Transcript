from __future__ import annotations
import os
import json
from typing import Any, Dict
import httpx

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-2.5-pro").strip()

# Gemini API (AI Studio) generateContent endpoint
# 문서: generativelanguage.googleapis.com 기반 :contentReference[oaicite:7]{index=7}
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

class GeminiError(Exception):
    pass

def _safe_json_loads(text: str) -> Any:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        return None

async def analyze_with_gemini(prompt: str, max_output_tokens: int = 2048) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    url = f"{BASE_URL}/models/{GEMINI_MODEL}:generateContent"

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
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0)) as client:
        r = await client.post(url, headers=headers, json=body)

    if r.status_code == 401:
        # 너가 지금 보는 그 에러. (대부분 endpoint/인증모드 mismatch 케이스) :contentReference[oaicite:8]{index=8}
        return {"ok": False, "error": "Gemini HTTP 401", "detail": r.text[:2000]}
    if r.status_code >= 400:
        return {"ok": False, "error": f"Gemini HTTP {r.status_code}", "detail": r.text[:2000]}

    data = r.json()

    # 응답 텍스트 꺼내기 (candidate[0].content.parts[0].text)
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return {"ok": False, "error": "Gemini response parse failed", "raw": data}

    # “반드시 JSON만 출력” 프롬프트라서 json.loads 시도
    parsed = _safe_json_loads(text)
    if parsed is None:
        return {"ok": False, "error": "Gemini output not valid JSON", "raw": text[:2000]}
    return parsed
