# app/prompts.py
from __future__ import annotations
from typing import Any, Dict, List


def build_video_analysis_prompt(index: int, title: str, description: str, transcript_text: str) -> str:
    # "결과는 JSON만" 강제(파싱 안정성)
    return f"""
너는 유튜브 채널 분석가다.
아래 영상의 메타정보와 대본을 기반으로 "영상 기획 요소"를 JSON으로만 출력해라.
설명/말/코드블록 금지. JSON만.

[영상 Index] {index}
[제목] {title}
[설명(일부)] {description}

[대본]
{transcript_text}

반드시 아래 스키마를 지켜라:
{{
  "hook": "첫 3초 훅 요약",
  "structure": ["전개1", "전개2", "전개3"],
  "tone": ["톤/문체 키워드"],
  "cta": "구독/좋아요/댓글 유도 방식",
  "repeatable_format": ["반복되는 포맷/코너"],
  "highlights": ["시청자 반응 유도 포인트 3~7개"],
  "keywords": ["핵심 키워드 10개 내외"]
}}
""".strip()


def build_channel_profile_prompt(analyses: List[Dict[str, Any]]) -> str:
    return f"""
너는 유튜브 채널 전략가다.
아래는 동일 채널의 여러 영상 분석 결과다.
이걸 종합해서 채널의 "고정 포맷/금기/체크리스트"를 JSON으로만 출력해라.
설명 금지, JSON만.

[입력 데이터]
{analyses}

반드시 아래 스키마를 지켜라:
{{
  "one_line_concept": "채널 컨셉 한 문장",
  "target_audience": ["타깃 시청자"],
  "fixed_format": ["반복 포맷/규칙"],
  "tone_rules": ["문체/톤 규칙"],
  "cta_rules": ["CTA 규칙"],
  "taboo": ["하면 안 되는 것"],
  "production_checklist": ["기획/대본/편집 체크리스트"]
}}
""".strip()
