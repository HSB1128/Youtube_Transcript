# app/gemini_rest.py
import os
from google import genai

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY env var")

    _client = genai.Client(api_key=api_key)
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
