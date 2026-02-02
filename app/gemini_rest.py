# app/gemini_rest.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
import google.auth
from google.auth.transport.requests import Request


class GeminiError(Exception):
    pass


def _get_access_token() -> str:
    """
    Cloud Run에 붙은 서비스 계정(ADC)으로 OAuth2 access token 발급.
    """
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    if not creds.token:
        raise GeminiError("Failed to obtain access token via ADC")
    return creds.token


def analyze_with_gemini(
    prompt: str,
    *,
    model: Optional[str] = None,
    location: Optional[str] = None,
    max_output_tokens: int = 2048,
    temperature: float = 0.6,
) -> Dict[str, Any]:
    """
    Vertex AI Gemini REST 호출:
    POST https://{location}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{location}/publishers/google/models/{model}:generateContent
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("PROJECT_ID")
    if not project_id:
        raise GeminiError("Missing GOOGLE_CLOUD_PROJECT (or GCP_PROJECT/PROJECT_ID) env var")

    location = location or os.getenv("VERTEX_LOCATION", "us-central1")
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

    token = _get_access_token()
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project_id}/locations/{location}/publishers/google/models/{model}:generateContent"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": int(max_output_tokens),
            "temperature": float(temperature),
        },
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=120) as client:
            r = client.post(url, json=payload, headers=headers)
    except Exception as e:
        raise GeminiError(f"Gemini request failed: {e}")

    if r.status_code >= 400:
        raise GeminiError(f"Gemini HTTP {r.status_code}: {r.text}")

    data = r.json()

    # Vertex 응답 파싱(가장 흔한 candidates[0].content.parts[0].text)
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"ok": True, "text": text, "raw": data}
    except Exception:
        # 모델이 JSON만 주거나, 다른 포맷이면 raw를 그대로 넘겨서 main에서 처리하게
        return {"ok": True, "text": None, "raw": data}
