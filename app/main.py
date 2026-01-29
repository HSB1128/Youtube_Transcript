from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import json
import time

from app.youtube_data import fetch_videos_metadata
from app.transcript import try_fetch_transcript_segments
from app.stt import stt_from_youtube_url

# ===== Gemini SDK =====
# requirements.txt에 google-genai 추가 필요
from google import genai

app = FastAPI(title="YouTube Transcription + Gemini Profiling (Cloud Run)")

# ====== 환경변수 ======
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")  # youtube_data.py 내부에서도 사용
ENABLE_STT = os.getenv("ENABLE_STT", "true").lower() == "true"
MAX_DURATION_SEC_FOR_STT = int(os.getenv("MAX_DURATION_SEC_FOR_STT", "1200"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

# 출력 토큰 제한(너무 길게 나오는 걸 방지)
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2200"))
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))

# 입력이 너무 커질 때를 대비한 안전장치(필요 없으면 크게 잡아도 됨)
# "전체 자막"을 원칙으로 하되, 진짜 말도 안 되게 길면 서버가 죽는 걸 막기 위함
MAX_TRANSCRIPT_CHARS = int(os.getenv("MAX_TRANSCRIPT_CHARS", "600000"))  # 대략 수십만~수백만도 가능

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


class AnalyzeProfileReq(BaseModel):
    urls: List[str] = Field(..., description="YouTube URLs")
    languages: List[str] = Field(default_factory=lambda: ["ko", "en"])
    include_stats: bool = True

    stt_fallback: bool = True
    skip_stt_if_longer_than_sec: int = Field(default=MAX_DURATION_SEC_FOR_STT)

    # 영상별 분석 결과를 더 짧게/길게 만들고 싶을 때(옵션)
    max_output_tokens: int = Field(default=GEMINI_MAX_OUTPUT_TOKENS)
    temperature: float = Field(default=GEMINI_TEMPERATURE)


@app.get("/health")
def health():
    return {"ok": True}


def _cut(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def _segments_to_timed_text(segs: List[Dict[str, Any]]) -> str:
    """
    전체 자막을 '원문 전체'로 넘기되,
    Gemini가 훅/CTA 위치를 더 잘 잡도록 타임스탬프를 함께 붙임.
    """
    lines = []
    for s in segs:
        st = float(s.get("start", 0.0))
        dur = float(s.get("duration", 0.0))
        ed = st + max(0.0, dur)
        tx = (s.get("text") or "").strip()
        if not tx:
            continue
        # 예: [12.3-15.8] 안녕하세요 ...
        lines.append(f"[{st:.1f}-{ed:.1f}] {tx}")
    return "\n".join(lines)


def _build_prompt(index: int, title: str, description_300: str, transcript_text: str) -> str:
    """
    - 제목: 절대 요약/변형 금지 (원문 그대로 제공)
    - 설명: 300자 컷 (원문 유지)
    - 자막: 전체(타임스탬프 포함)
    - 출력: JSON만
    """
    return f"""
너는 유튜브 영상/쇼츠 기획을 분석하는 전문가다.
아래 영상의 "전체 자막"을 처음부터 끝까지 모두 읽고, 기획/구성/말투/CTA 패턴을 분석하라.

[영상 인덱스]
{index}

[제목 - 원문 그대로 (절대 요약/변형 금지)]
{title}

[설명 - 300자 이내(원문 컷)]
{description_300}

[전체 자막 - 타임스탬프 포함]
{transcript_text}

---
반드시 아래 스키마를 만족하는 "JSON"만 출력하라.
마크다운, 설명 문장, 코드펜스, 주석, 여분 텍스트를 절대 포함하지 마라.

{{
  "hookPattern": {{
    "summary": "첫 3~10초 훅 구조를 한 문장으로",
    "examples": [
      {{ "start": 0.0, "end": 0.0, "text": "훅에 해당하는 원문 자막 일부" }}
    ]
  }},
  "structureTemplate": [
    "전개를 4~7단계로 요약(예: 문제제기→근거→예시→전환→정리)"
  ],
  "toneStyle": {{
    "keywords": ["말투/톤 키워드 5~10개"],
    "do": ["이 채널/스타일에서 효과적인 표현/운영 포인트 3~8개"],
    "dont": ["이탈 유발/금기 포인트 3~8개"]
  }},
  "ctaTypes": ["댓글 유도", "구독 유도", "다음편 예고" 등 실제 관찰된 것만],
  "repeatedFrames": ["반복되는 문장 프레임 3~10개(가능하면 원문 프레이즈 형태)"],
  "keyScenes": [
    {{ "start": 0.0, "end": 0.0, "text": "핵심 장면 자막(원문 일부)" }}
  ]
}}
""".strip()


def _gemini_json(prompt: str, max_output_tokens: int, temperature: float) -> Dict[str, Any]:
    if client is None:
        return {"ok": False, "error": "GEMINI_API_KEY is missing"}

    # 간단 재시도(레이트리밋/일시 오류 대비)
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens,
                },
            )
            text = (resp.text or "").strip()

            # JSON만 받기로 했으니 파싱 시도
            return json.loads(text)
        except Exception as e:
            last_err = str(e)
            # backoff
            time.sleep(0.8 * attempt)

    return {"ok": False, "error": "Gemini failed", "detail": last_err}


@app.post("/analyze_and_profile")
def analyze_and_profile(req: AnalyzeProfileReq) -> Dict[str, Any]:
    if not req.urls:
        raise HTTPException(400, "urls is empty")

    if not YOUTUBE_API_KEY:
        # youtube_data.py에서도 쓰지만, 여기서 먼저 명확히 에러 안내
        raise HTTPException(500, "YOUTUBE_API_KEY is missing")

    meta = fetch_videos_metadata(req.urls, include_stats=req.include_stats)

    results: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    idx = 1
    for item in meta.get("items", []):
        # 메타 실패는 그대로 기록
        if not item.get("ok"):
            results.append({
                "index": idx,
                "url": item.get("url"),
                "videoId": item.get("videoId"),
                "ok": False,
                "error": item.get("error", "META_FETCH_FAILED"),
            })
            idx += 1
            continue

        url = item["url"]
        video_id = item["videoId"]
        duration_sec = int(item.get("durationSec") or 0)

        # 1) transcript 우선
        segs = try_fetch_transcript_segments(video_id, req.languages)
        transcript_source = "YOUTUBE_CAPTION" if segs else "NONE"

        # 2) 없으면 STT 폴백(조건/설정 충족 시)
        stt_info: Optional[Dict[str, Any]] = None
        if (not segs) and req.stt_fallback and ENABLE_STT:
            if duration_sec > req.skip_stt_if_longer_than_sec:
                stt_info = {
                    "ok": False,
                    "skipped": True,
                    "reason": f"durationSec {duration_sec} > skip_stt_if_longer_than_sec {req.skip_stt_if_longer_than_sec}"
                }
            else:
                stt_info = stt_from_youtube_url(url)
                if stt_info.get("ok") and stt_info.get("segments"):
                    segs = stt_info["segments"]
                    transcript_source = "STT"
                else:
                    transcript_source = "NONE"

        # 3) 전체 자막 텍스트(타임스탬프 포함) 구성
        transcript_text = _segments_to_timed_text(segs)

        if not transcript_text:
            warnings.append({
                "index": idx,
                "url": url,
                "reason": "NO_TRANSCRIPT",
                "transcriptSource": transcript_source,
                "sttInfo": stt_info
            })
            # 자막이 없으면 분석은 빈 값으로 반환(또는 스킵)
            results.append({
                "index": idx,
                "url": url,
                "videoId": video_id,
                "meta": {
                    "title": item.get("title", ""),
                    "description": _cut(item.get("description", ""), 300),
                    "channelTitle": item.get("channelTitle", ""),
                    "publishedAt": item.get("publishedAt", ""),
                    "durationSec": duration_sec,
                    "stats": item.get("stats") if req.include_stats else None
                },
                "transcriptSource": transcript_source,
                "sttInfo": stt_info,
                "analysis": {"ok": False, "error": "NO_TRANSCRIPT"}
            })
            idx += 1
            continue

        # 안전장치: 너무 길면 자르되, 원칙은 전체
        if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
            transcript_text = transcript_text[:MAX_TRANSCRIPT_CHARS] + "\n[TRUNCATED]"
            warnings.append({
                "index": idx,
                "url": url,
                "reason": f"TRANSCRIPT_TRUNCATED chars>{MAX_TRANSCRIPT_CHARS}"
            })

        title_raw = item.get("title", "")
        desc_300 = _cut(item.get("description", ""), 300)

        prompt = _build_prompt(
            index=idx,
            title=title_raw,           # 제목은 원문 그대로
            description_300=desc_300,  # 설명은 300자 컷
            transcript_text=transcript_text
        )

        analysis = _gemini_json(
            prompt=prompt,
            max_output_tokens=req.max_output_tokens,
            temperature=req.temperature,
        )

        results.append({
            "index": idx,
            "url": url,
            "videoId": video_id,
            "meta": {
                "title": title_raw,
                "description": desc_300,
                "channelTitle": item.get("channelTitle", ""),
                "publishedAt": item.get("publishedAt", ""),
                "durationSec": duration_sec,
                "stats": item.get("stats") if req.include_stats else None
            },
            "transcriptSource": transcript_source,
            "sttInfo": stt_info,
            "analysis": analysis
        })

        idx += 1

    return {
        "ok": True,
        "count": len(results),
        "videos": results,
        "warnings": warnings
    }
