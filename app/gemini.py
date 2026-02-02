# app/gemini.py
from __future__ import annotations

import os, json
from typing import Dict, Any
from google import genai

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if not GEMINI_API_KEY:
    # import 시점에 바로 죽이면 Cloud Run health도 죽어서,
    # 런타임에서 체크하게 두고 싶으면 여기서 raise하지 말고 client=None로 두는 방법도 있음.
    pass

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def analyze_with_gemini(prompt: str, max_output_tokens: int = 2048) -> Dict[str, Any]:
    if client is None:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        generation_config={
            "temperature": 0.3,
            "max_output_tokens": max_output_tokens,
        },
    )

    text = (response.text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        return {
            "ok": False,
            "error": "Gemini output not valid JSON",
            "raw": text[:5000],
        }
