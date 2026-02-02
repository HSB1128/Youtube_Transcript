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
아래 영상의 자막을 처음부터 끝까지 모두 읽고 분석하라.

[영상 번호]
{index}

[제목 - 원문 그대로]
{title}

[설명 - 300자 이내]
{(description or "")[:300]}

[전체 자막]
{transcript_text}

---
다음 정보를 반드시 JSON 형식으로만 출력하라.
설명 문장, 주석, 마크다운은 절대 포함하지 마라.

{{
  "hookPattern": {{
    "summary": "...",
    "examples": [
      {{ "start": 0, "end": 10, "text": "첫 3~10초 핵심 문장/전개" }}
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


def build_channel_profile_prompt(per_video_results: List[Dict[str, Any]]) -> str:
    """
    per_video_results: [{index,url,meta,analysis}, ...]
    analysis는 영상별 JSON(훅/구조/톤/CTA/반복프레임) 결과.
    """
    payload = json.dumps(per_video_results, ensure_ascii=False)

    return f"""
너는 유튜브 채널 기획 컨설턴트다.
아래는 같은 채널의 여러 영상에 대한 '기획 분석 결과(JSON)' 모음이다.
이 데이터를 종합해서 채널의 고정 기획 컨셉을 뽑아라.

[입력 데이터(JSON 배열)]
{payload}

---
반드시 JSON 형식으로만 출력하라. 마크다운/설명문 금지.

{{
  "oneLineConcept": "...",
  "targetAudience": "...",
  "fixedFormat": {{
    "intro": "...",
    "body": "...",
    "transition": "...",
    "ending": "..."
  }},
  "taboosWarnings": [
    "이탈 유발 포인트",
    "하면 안 되는 톤/표현"
  ],
  "shortsChecklist": [
    "체크리스트 항목들"
  ]
}}
""".strip()
