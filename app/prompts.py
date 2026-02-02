# app/prompts.py
from __future__ import annotations

from typing import Any, Dict, List


def build_video_analysis_prompt(
    *,
    index: int,
    title: str,
    description: str,
    transcript_text: str,
) -> str:
    return f"""
너는 유튜브 숏츠/영상 기획 분석가다.
아래 영상 정보를 바탕으로 "기획 요소"를 JSON으로만 출력하라.

[영상 인덱스] {index}
[제목] {title}
[설명(앞부분)] {description}

[대본/자막]
{transcript_text}

출력 JSON 스키마(반드시 이 구조를 지켜라):
{{
  "ok": true,
  "hook": "초반 훅 요약(1~2문장)",
  "structure": ["전개1", "전개2", "전개3"],
  "tone": ["문체/톤 키워드들"],
  "key_points": ["핵심 포인트 5~10개"],
  "cta": "콜투액션/마무리 패턴",
  "repeatable_format": "반복 가능한 포맷이 있으면 한 문장으로",
  "banned_or_caution": ["금기/주의점"],
  "keywords": ["검색/태그 후보 10~20개"]
}}
""".strip()


def build_channel_profile_prompt(per_video_analyses: List[Dict[str, Any]]) -> str:
    return f"""
너는 채널 기획 컨셉 분석가다.
아래는 같은 채널(또는 유사 채널) 영상들의 기획 분석 결과 모음이다.
이걸 통합해서 채널 고정 포맷/타깃/한줄 컨셉을 JSON으로만 출력하라.

입력 데이터:
{per_video_analyses}

출력 JSON 스키마:
{{
  "ok": true,
  "one_line_concept": "한 문장 컨셉",
  "target_audience": ["타깃1","타깃2"],
  "fixed_format": ["고정 포맷 규칙 5~10개"],
  "tone_and_style": ["톤/문체 5~10개"],
  "do_not": ["금기/주의 5~10개"],
  "checklist": ["기획 체크리스트 10개 내외"]
}}
""".strip()
