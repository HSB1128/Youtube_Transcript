# app/gemini_rest.py
import os
from google import genai

LOCATION = os.getenv("GEMINI_LOCATION", "us-central1")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("PROJECT_ID")
    if not project:
        raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT (or GCP_PROJECT/PROJECT_ID) env var")

    _client = genai.Client(
        vertexai=True,
        project=project,
        location=LOCATION,
    )
    return _client

def analyze_with_gemini(prompt: str, max_output_tokens: int = 2048) -> dict:
    client = _get_client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )
    return {
        "ok": True,
        "model": MODEL,
        "text": (resp.text or "").strip(),
    }
