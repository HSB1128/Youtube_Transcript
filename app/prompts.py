# app/prompts.py
from __future__ import annotations
from typing import Dict, List


def build_video_analysis_prompt(
    *,
    index: int,
    title: str,
    description: str,
    transcript_text: str,
) -> str:
    return f"""
너는 유튜브 영상의 "기획 시스템(재현 가능한 형식 DNA)"만 추출하는 분석가다.
영상의 '내용 요약'은 금지하고, 훅/전개/톤/리텐션/CTA/반복 프레임만 JSON으로 뽑아라.

[출력 규칙]
- 반드시 순수 JSON만 출력 (설명/마크다운/코드펜스 금지)
- 아래 스키마의 키를 정확히 지켜라 (추가 키 금지)
- 한국어로 작성
- transcript_text에 근거가 없는 내용은 만들지 마라

[인용(Quotes) 규칙]
- quotes.items[].text는 transcript_text 안에 "그대로 존재하는 연속 구절"만 허용
- quotes.items[].text는 너무 길면 잘라서 넣어도 되나, 최대 20단어(또는 120자) 이내로 제한
- 해당 문장을 찾을 수 없으면 quotes.items = []
- evidence.approx_start_sec는 '대략'이면 되고, 자신 없으면 0으로 두고 near_keywords라도 채워라

[표현 특징(Expression Markers) 규칙]
- expression_markers는 transcript_text에서 반복되는 "표현 방식/기호/말버릇"만 기록
- 내용(주제) 자체를 요약하거나 추가로 해석하지 마라

[JSON 스키마]
{{
  "ok": true,
  "video_index": {index},

  "hook": {{
    "summary": "초반 훅을 형식 중심으로 한 문장 요약",
    "techniques": ["질문/충격/숫자/반전/공포/비교/밈 등"],
    "frames": [
      "질문형: 'OOO 아세요?'",
      "숫자형: 'OOO의 90%가...'",
      "반전형: '다들 OO인 줄 아는데 사실은...'"
    ]
  }},

  "structure": {{
    "template": "문제→근거2→예시→전환→정리",
    "beats": ["전개 구간을 4~7개로(형식 중심)"],
    "pacing": "템포 특징(짧게)"
  }},

  "style_tone": {{
    "persona": "서술자 캐릭터/포지션(예: 기자톤/친구톤/권위자/드립캐)",
    "narration_style": "말투/리듬 특징(짧게)",
    "tone_keywords": ["키워드 5개"]
  }},

  "expression_markers": {{
    "punctuation": ["자주 쓰는 문장부호/표현기호 최대 6개"],
    "catchphrases": ["반복되는 말버릇/고정 문구 최대 6개"],
    "rhythm": "문장 호흡 특징(짧게)",
    "numbers_style": "숫자/단위/비교 제시 방식(짧게)"
  }},

  "retention": {{
    "recurring_devices": ["반복 장치/고정 코너/리듬 장치"],
    "cta": ["CTA 유형/문장 프레임(최대 3개)"]
  }},

  "quotes": {{
    "items": [
      {{
        "text": "transcript에 실제로 있는 연속 구절(20단어/120자 이내)",
        "evidence": {{
          "approx_start_sec": 0,
          "near_keywords": ["근처 키워드1", "근처 키워드2"]
        }}
      }}
    ]
  }}
}}

[메타]
- index: {index}
- title: {title}
- description: {(description or "")[:250]}

[transcript_text]
{transcript_text}
""".strip()


def build_channel_profile_prompt(analyses_json: str) -> str:
    return f"""
너는 유튜브 채널의 "재현 가능한 플레이북"만을 추출하는 전략가다.
아래는 동일 채널의 여러 영상에서 추출된 형식 DNA JSON 모음이다.

[출력 규칙]
- 반드시 순수 JSON만 출력 (마크다운/코드펜스/설명 금지)
- 한국어로 작성
- 근거 없는 추정 금지. 불확실하면 '추정'으로만 표시

[집계 규칙(중요)]
- 최소 60% 이상의 영상에서 반복되면 core로 채택
- 반복 빈도가 낮으면 options로 분리
- tone_keywords는 상위 5개만
- opening/body/ending은 각 1~2문장 프레임
- 내용(주제) 일반화 금지, 형식만 추출

[출력 JSON 스키마]
{{
  "ok": true,
  "one_sentence_concept": "형식 관점의 한 문장 컨셉",
  "target_audience": "핵심 타깃(추정 가능)",
  "fixed_format": {{
    "opening": "오프닝 프레임(1~2문장)",
    "body": "본론 프레임(1~2문장)",
    "ending": "엔딩/CTA 프레임(1~2문장)",
    "hook_frames": ["자주 쓰는 훅 프레임 top 3~6"],
    "structure_templates": ["자주 쓰는 전개 템플릿 top 2~4"],
    "recurring_devices": ["반복 장치"]
  }},
  "tone_guide": {{
    "persona": "서술자 캐릭터",
    "tone_keywords": ["키워드 5개"],
    "dos": ["해야 할 것"],
    "donts": ["피해야 할 것"]
  }},
  "cta_system": {{
    "types": ["CTA 타입들(댓글/구독/다음편 예고 등)"],
    "templates": ["CTA 문장 프레임 top 3~6"],
    "timing_rules": ["CTA 배치 규칙"]
  }},
  "options": {{
    "optional_hooks": ["옵션 훅 프레임"],
    "optional_devices": ["옵션 장치"],
    "optional_structures": ["옵션 전개 템플릿"]
  }},
  "checklist": ["제작 전 체크리스트(10개 내외)"]
}}

[형식 DNA 모음(JSON)]
{analyses_json}
""".strip()


def build_json_repair_prompt(schema_name: str, raw_text: str) -> str:
    return f"""
너는 JSON 포맷 복구기다.
아래 텍스트는 모델의 출력인데, 순수 JSON이 아니거나 스키마를 어겼다.

[규칙]
- 반드시 순수 JSON만 출력
- 마크다운/코드펜스/설명/추가 텍스트 절대 금지
- 새로운 정보 생성 금지: 원문 텍스트에 없는 내용은 넣지 마라
- 값이 불확실하면 빈 값/빈 배열/0으로 둬라
- 키는 스키마에 있는 것만 허용(추가 키 금지)

[schema_name]
{schema_name}

[raw_output]
{raw_text}
""".strip()
