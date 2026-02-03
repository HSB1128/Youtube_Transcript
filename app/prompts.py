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
너는 유튜브 쇼츠/롱폼의 "형식(포맷) DNA"를 추출하는 기획자다.
아래 영상 정보를 보고, "형식/표현/구조"만 JSON으로 정리해라.
(주제 요약/내용 해설/시사 해석 같은 '내용'은 쓰지 마라.)

[절대 규칙]
- 반드시 JSON만 출력 (설명/머리말/마크다운 금지)
- 아래 스키마의 키를 정확히 지켜라 (추가 키 금지)
- 값은 구체적으로, 그러나 짧게
- 한국어로 작성
- transcript에 근거가 없는 내용은 만들지 마라

[중요: 인용(Quotes) 규칙]
- quotes.items[].text 는 transcript_text 안에 "그대로 존재하는 문장"만 허용
- 없으면 quotes.items 는 빈 배열 []
- 가능하면 evidence로 "approx_start_sec(대략 초)" 또는 "near_keywords(근처 키워드)" 중 하나 이상을 채워라
- 시간 추정이 어렵다면 near_keywords만 채워라

[출력 JSON 스키마]
{{
  "ok": true,
  "video_index": {index},

  "hook": {{
    "summary": "초반 훅을 한 문장으로 요약(형식 중심)",
    "techniques": ["훅 기법(질문/충격/숫자/반전/공포/비교/밈 등)"],
    "frames": [
      "질문형: 'OOO 아세요?'",
      "숫자형: 'OOO의 90%가...'",
      "반전형: '다들 OO인 줄 아는데 사실은...'"
    ]
  }},

  "structure": {{
    "template": "문제→근거2→예시→전환→정리 (가능한 한 이런 형태로)",
    "beats": ["전개 순서를 4~7개 구간으로 요약(형식 중심)"],
    "pacing": "템포/전개 속도 특징(짧게)"
  }},

  "style_tone": {{
    "persona": "서술자 캐릭터/포지션(예: 기자톤/친구톤/권위자/드립캐)",
    "narration_style": "말투 특징(짧게)",
    "tone_keywords": ["키워드 5개"]
  }},

  "retention": {{
    "recurring_devices": ["반복 장치/고정 코너/리듬 장치"],
    "cta": "댓글/구독/다음편 예고 등 CTA 형태(짧게)"
  }},

  "quotes": {{
    "items": [
      {{
        "text": "transcript에 실제로 있는 문장 1개",
        "evidence": {{
          "approx_start_sec": 0,
          "near_keywords": ["근처 키워드1", "근처 키워드2"]
        }}
      }}
    ]
  }}
}}

[영상 메타]
- index: {index}
- title: {title}
- description: {(description or "")[:250]}

[transcript_text]
{transcript_text}
""".strip()


def build_channel_profile_prompt(analyses_json: str) -> str:
    return f"""
너는 유튜브 채널의 "재현 가능한 포맷(playbook)"을 만드는 전략가다.
아래는 같은 채널의 여러 영상에서 추출한 "형식 DNA JSON" 모음이다.

[목표]
- 채널을 카피할 수 있게: 훅 프레임/전개 템플릿/톤 가이드/CTA/반복 장치/금기/체크리스트를 만든다.
- 영상 내용(주제)은 다를 수 있으니, 내용 일반화는 하지 말고 "형식"만 뽑아라.

[집계 규칙(중요)]
- 최소 60% 이상의 영상에서 반복되는 패턴만 fixed_format에 넣어라
- 반복 빈도가 낮으면 fixed_format이 아니라 options(옵션) 또는 "추정"으로 분리해라
- tone_keywords는 상위 5개만
- opening/body/ending은 각 1~2문장 "프레임"으로 작성
- 근거 없는 추측은 금지. 불확실하면 '추정'이라고 명시

[출력 JSON 스키마]
{{
  "ok": true,
  "one_sentence_concept": "형식 관점의 한 문장 컨셉(예: '숫자+반전으로 몰아치는 뉴스 요약 쇼츠')",
  "target_audience": "핵심 타깃(추정 가능)",
  "fixed_format": {{
    "opening": "오프닝 프레임(1~2문장)",
    "body": "본론 전개 프레임(1~2문장)",
    "ending": "엔딩/CTA 프레임(1~2문장)",
    "hook_frames": ["자주 쓰는 훅 프레임 top 3~6"],
    "structure_templates": ["자주 쓰는 전개 템플릿 top 2~4"],
    "recurring_devices": ["반복 장치"]
  }},
  "tone_guide": {{
    "persona": "서술자 캐릭터",
    "tone_keywords": ["키워드 5개"],
    "dos": ["톤/표현에서 해야 할 것"],
    "donts": ["피해야 할 표현/이탈 유발 포인트(금기)"]
  }},
  "options": {{
    "optional_hooks": ["가끔 쓰지만 핵심은 아닌 훅(옵션)"],
    "optional_devices": ["옵션 장치"]
  }},
  "checklist": ["제작 전 체크리스트(10개 내외)"]
}}

[영상 형식 DNA JSON 모음]
{analyses_json}
""".strip()
