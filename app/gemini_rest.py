# app/gemini_rest.py
import os
from google import genai

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("PROJECT_ID")
LOCATION = os.getenv("GEMINI_LOCATION", "us-central1")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not PROJECT:
    raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT (or GCP_PROJECT/PROJECT_ID) env var")

_client = genai.Client(
    vertexai=True,
    project=PROJECT,
    location=LOCATION,
)

def analyze_with_gemini(prompt: str, max_output_tokens: int = 2048) -> dict:
    resp = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        # generation_config는 버전에 따라 형태가 달라져서
        # 최소 구현에서는 빼는 게 안전함.
    )
    return {
        "ok": True,
        "model": MODEL,
        "text": (resp.text or "").strip(),
    }
