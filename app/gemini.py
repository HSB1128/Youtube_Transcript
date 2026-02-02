# app/gemini.py
from __future__ import annotations

import os
import json
from typing import Dict, Any
import httpx

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()  # 우선 flash 추천
GEMINI_TIMEOUT_SEC = float(os.getenv("GEMINI_TIMEOUT_SEC", "60"))

# Gemini API REST endpoint (API Key 방식)
# model 예: gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro 등
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def analyze_with_gemini(prompt: str, max_output_tokens: int = 2048) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    url = f"{BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    payload = {
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
        with httpx.Client(timeout=GEMINI_TIMEOUT_SEC) as client:
            r = client.post(url, json=payload)
            if r.status_code != 200:
                return {
                    "ok": False,
                    "error": f"Gemini HTTP {r.status_code}",
                    "detail": (r.text or "")[:2000],
                }

            data = r.json()

        # 응답 텍스트 꺼내기
        # candidates[0].content.parts[0].text
        text = ""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            return {"ok": False, "error": "Gemini response missing text", "raw": data}

        # JSON 강제 파싱
        try:
            return json.loads(text)
        except Exception:
            return {"ok": False, "error": "Gemini output not valid JSON", "raw": text[:4000]}

    except Exception as e:
        return {"ok": False, "error": f"Gemini call failed: {type(e).__name__}: {str(e)[:300]}"}
