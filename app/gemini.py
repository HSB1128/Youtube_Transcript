# app/gemini.py
from __future__ import annotations

import os
import json
from typing import Dict, Any

from google import genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

client = genai.Client(api_key=GEMINI_API_KEY)


def analyze_with_gemini(prompt: str, max_output_tokens: int = 2048) -> Dict[str, Any]:
    """
    google-genai 버전 차이로 generation_config 인자가 없을 수 있음.
    => 가장 호환성 높은 방식: 최소 인자만으로 호출하고,
       JSON 파싱 실패 시 ok:false로 반환.
    """
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    try:
        # ✅ 여기서 generation_config를 넘기지 않는다 (버전 호환)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = (getattr(resp, "text", None) or "").strip()

        if not text:
            return {"ok": False, "error": "Empty Gemini response"}

        # JSON 강제 파싱
        try:
            return json.loads(text)
        except Exception:
            # JSON이 아닐 때 운영을 위해 raw를 남김
            return {
                "ok": False,
                "error": "Gemini output not valid JSON",
                "raw": text[:4000],
            }

    except Exception as e:
        return {"ok": False, "error": f"Gemini call failed: {type(e).__name__}: {str(e)[:300]}"}
