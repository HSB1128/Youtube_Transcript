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
너는 유튜브 숏츠/롱폼 제작을 분석하는 기획자다.
아래 영상의 정보를 보고, "기획 요소"를 JSON으로 정리해라.

[요구사항]
- 반드시 JSON만 출력
- 키는 아래 스키마를 정확히 지켜라
- 값은 가능한 한 구체적으로
- 한국어로 작성

[JSON 스키마]
{{
  "ok": true,
  "video_index": {index},
  "hook": {{
    "summary": "초반 훅이 무엇인지 한 문장",
    "techniques": ["훅 기법들(질문/충격/숫자/반전/공포/비교/밈 등)"]
  }},
  "structure": {{
    "beats": ["전개 순서(도입-전개-클라이맥스-정리) 요약"],
    "pacing": "템포/전개 속도 특징"
  }},
  "style_tone": {{
    "narration_style": "말투/서술자 캐릭터",
    "tone_keywords": ["키워드 5개"]
  }},
  "retention": {{
    "pattern": "반복 포맷/고정 코너/시청 지속 유도 장치",
    "cta": "구독/댓글 유도 방식"
  }},
  "content": {{
    "topic": "주제",
    "audience": "타깃 시청자",
    "novelty": "차별점/신선한 포인트"
  }},
  "quotes": {{
    "memorable_lines": ["인상 깊은 문장 3개(가능하면)"]
  }}
}}

[영상]
- index: {index}
- title: {title}
- description: {description}

[transcript]
{transcript_text}
""".strip()


def build_channel_profile_prompt(analyses: List[Dict[str, Any]]) -> str:
    return f"""
너는 유튜브 채널의 고정 포맷을 추출하는 전략가다.
아래는 채널의 여러 영상 분석 결과(JSON) 모음이다.
이걸 기반으로 채널의 "한 문장 컨셉 / 타깃 / 고정 포맷 / 금기사항 / 체크리스트"를 JSON으로 만들어라.

[요구사항]
- 반드시 JSON만 출력
- 한국어로 작성
- 추측은 "추정"으로 표시
- 반복되는 패턴을 최우선으로 뽑아라

[출력 JSON 스키마]
{{
  "ok": true,
  "one_sentence_concept": "한 문장 컨셉",
  "target_audience": "핵심 타깃",
  "fixed_format": {{
    "opening": "오프닝 고정 패턴",
    "body": "본론 전개 패턴",
    "ending": "엔딩/CTA 패턴",
    "recurring_devices": ["반복 장치"]
  }},
  "tone_guide": {{
    "persona": "서술자 캐릭터",
    "tone_keywords": ["키워드"]
  }},
  "dos_donts": {{
    "dos": ["해야 할 것"],
    "donts": ["피해야 할 것(금기/주의)"]
  }},
  "checklist": ["제작 전 체크리스트"]
}}

[영상 분석 모음]
{analyses}
""".strip()
