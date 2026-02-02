from __future__ import annotations
from typing import Dict, Any, List
import json

def build_video_analysis_prompt(
    index: int,
    title: str,
    description: str,
    transcript_text: str,
) -> str:
    return f"""
너는 유튜브 쇼츠/영상 기획 전문 분석가다.
아래 영상의 **전체 자막을 처음부터 끝까지 모두 읽고 분석**하라.

[영상 번호]
{index}

[제목 - 원문 그대로]
{title}

[설명 - 300자 이내]
{(description or "")[:300]}

[전체 자막]
{transcript_text}

---
다음 정보를 **반드시 JSON 형식으로만** 출력하라.
설명 문장, 주석, 마크다운은 절대 포함하지 마라.

{{
  "hookPattern": {{
    "summary": "...",
    "examples": [
      {{ "start": 0, "end": 0, "text": "..." }}
    ]
  }},
  "structureTemplate": [
    "문제제기",
    "근거",
    "예시",
    "전환",
    "정리"
  ],
  "toneStyle": {{
    "keywords": [],
    "do": [],
    "dont": []
  }},
  "ctaTypes": [],
  "repeatedFrames": []
}}
""".strip()

def build_channel_profile_prompt(analyses: List[Dict[str, Any]]) -> str:
    # analyses: [{"index":..., "url":..., "meta":..., "analysis":...}, ...]
    compact = []
    for a in analyses:
        compact.append({
            "index": a.get("index"),
            "url": a.get("url"),
            "meta": a.get("meta"),
            "analysis": a.get("analysis"),
        })

    payload = json.dumps(compact, ensure_ascii=False)[:60000]  # 너무 길면 잘라서 안전장치

    return f"""
너는 유튜브 채널 기획 컨셉 추출 전문가다.
아래는 같은 채널에서 가져온 여러 영상의 "기획 분석 결과"다.
이를 기반으로 채널의 고정 컨셉과 포맷을 추출하라.

[영상 분석 JSON 배열]
{payload}

---
반드시 JSON 형식으로만 출력하라. 마크다운/주석/설명 문장 금지.

{{
  "oneLineConcept": "...",
  "targetAudience": "...",
  "fixedFormat": {{
    "intro": "...",
    "body": "...",
    "transition": "...",
    "ending": "..."
  }},
  "taboos": [],
  "shortsChecklist": []
}}
""".strip()
