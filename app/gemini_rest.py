# app/gemini_rest.py
from __future__ import annotations

import os
import json
from typing import Any, Dict, Optional

import httpx


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()

# AI Studio / Generative Language API endpoint (API Key 방식)
# v1beta가 보편적. (키 기반)
GEN_LANG_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiError(Exception):
    pass


def _extract_text(resp_json: Dict[str, Any]) -> str:
    """
    Gemini 응답에서 텍스트를 최대한 안전하게 뽑음.
    """
    # candidates[0].content.parts[0].text 형태가 일반적
    candidates = resp_json.get("candidates") or []
    if not candidates:
        return ""

    c0 = candidates[0]
    content = c0.get("content") or {}
    parts = content.get("parts") or []
    texts = []
    for p in parts:
        t = p.get("text")
        if t:
            texts.append(t)
    return "\n".join(texts).strip()


def analyze_with_gemini(
    prompt: str,
    *,
    max_output_tokens: int = 2048,
    temperature: float = 0.4,
    timeout_sec: float = 120.0,
) -> Dict[str, Any]:
    """
    prompt를 Gemini에 보내고, "JSON으로 출력"되길 기대.
    - 성공하면: dict(JSON)
    - 실패하면: {"ok": False, "error": "...", "raw": "..."} 형태로 반환
    """
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    url = f"{GEN_LANG_BASE}/models/{GEMINI_MODEL}:generateContent"
    params = {"key": GEMINI_API_KEY}

    body = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
    }

    try:
        r = httpx.post(
            url,
            params=params,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=timeout_sec,
        )
    except Exception as e:
        return {"ok": False, "error": f"Gemini request failed: {repr(e)}"}

    if r.status_code >= 400:
        return {"ok": False, "error": f"Gemini HTTP {r.status_code}", "detail": r.text}

    resp_json = r.json()
    text = _extract_text(resp_json)

    if not text:
        return {"ok": False, "error": "Gemini returned empty text", "raw": resp_json}

    # JSON 파싱 시도
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed.setdefault("ok", True)
            return parsed
        return {"ok": True, "data": parsed}
    except Exception:
        # JSON이 깨졌으면 raw 텍스트를 같이 남김
        return {"ok": False, "error": "Gemini output is not valid JSON", "raw_text": text}
