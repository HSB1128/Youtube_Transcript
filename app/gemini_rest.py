# app/gemini_rest.py
from __future__ import annotations

import os
import json
import asyncio
from typing import Any, Dict, Optional

from google import genai


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    return v


def _make_client() -> genai.Client:
    """
    1) GEMINI_API_KEY가 있으면 -> AI Studio(API Key) 모드
    2) 없으면 -> Vertex AI(Cloud Run 서비스계정 ADC/OAuth) 모드
    """
    api_key = _get_env("GEMINI_API_KEY")
    model = _get_env("GEMINI_MODEL", "gemini-2.5-pro")  # 참고용

    if api_key:
        # ✅ AI Studio API Key 모드: project 필요 없음
        return genai.Client(api_key=api_key)

    # ✅ Vertex AI 모드: Cloud Run 서비스계정(ADC) 사용
    project = (
        _get_env("GOOGLE_CLOUD_PROJECT")
        or _get_env("GCP_PROJECT")
        or _get_env("PROJECT_ID")
    )
    if not project:
        raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT (or GCP_PROJECT/PROJECT_ID) env var")

    location = _get_env("GCP_LOCATION", "us-central1")
    # Vertex AI로 붙일 때는 vertexai=True + project/location이 필요
    return genai.Client(vertexai=True, project=project, location=location)


# 모듈 로드 시 1회 생성 (요청마다 생성하면 느려짐)
_CLIENT = _make_client()


def _generate_sync(prompt: str, *, max_output_tokens: int = 2048) -> Dict[str, Any]:
    """
    google-genai는 기본적으로 동기 호출이 많아서,
    async 환경(FastAPI)에서 병렬 처리를 위해 to_thread로 감싸서 사용.
    """
    model = _get_env("GEMINI_MODEL", "gemini-2.5-pro")

    # genai 라이브러리 버전에 따라 config 파라미터 이름이 조금씩 달라서
    # 가장 호환 잘 되는 형태로 최소만 넣는다.
    resp = _CLIENT.models.generate_content(
        model=model,
        contents=prompt,
    )

    # resp는 라이브러리 객체일 수 있으니 dict로 안전 변환
    try:
        # 최신 버전에서 응답 객체에 model_dump_json 같은 게 있을 수 있음
        if hasattr(resp, "model_dump"):
            return resp.model_dump()
        if hasattr(resp, "to_dict"):
            return resp.to_dict()
    except Exception:
        pass

    # 최후의 수단: 문자열/객체 그대로 감싸서 반환
    return {"ok": True, "raw": str(resp)}


async def analyze_with_gemini(prompt: str, *, max_output_tokens: int = 2048) -> Dict[str, Any]:
    """
    ✅ main.py에서 `await analyze_with_gemini(...)` 해도 안 터지게 만든 핵심.
    """
    try:
        result = await asyncio.to_thread(_generate_sync, prompt, max_output_tokens=max_output_tokens)
        return result
    except Exception as e:
        return {"ok": False, "error": f"Gemini call failed: {type(e).__name__}: {str(e)}"}
