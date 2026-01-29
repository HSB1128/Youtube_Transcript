import os
from typing import Dict, Any
from google import genai

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

def analyze_video_with_gemini(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload:
      - title (원문)
      - description (300자 컷)
      - transcript (전체 자막)
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            {
                "role": "user",
                "parts": [
                    {
                        "text": payload["prompt"]
                    }
                ]
            }
        ],
        generation_config={
            "temperature": 0.3,
            "max_output_tokens": 2048
        }
    )

    # JSON 강제 (실패 대비)
    text = response.text.strip()
    try:
        return json.loads(text)
    except Exception:
        return {
            "ok": False,
            "error": "Gemini output not valid JSON",
            "raw": text[:2000]
        }
