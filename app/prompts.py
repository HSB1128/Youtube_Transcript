# app/prompts.py
from __future__ import annotations

import json
from typing import Any, Dict, List


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
  "repeatedFrames": [],
  "channelInsight": {{
    "oneLineConcept": "...",
    "targetAudience": "...",
    "formatTemplate": {{
      "intro": "...",
      "body": "...",
      "transition": "...",
      "ending": "..."
    }},
    "warnings": [],
    "shortsChecklist": []
  }}
}}
""".strip()


def build_channel_profile_prompt(
    analyses: List[Dict[str, Any]],
) -> str:
    """
    analyses: [
      {
        "index": 1,
        "url": "...",
        "meta": {...},
        "analysis": {...}  # 영상별 JSON 분석 결과
      },
      ...
    ]
    """
    # 너무 길어지는 걸 막기 위해 입력을 JSON으로 축약
    compact_items: List[Dict[str, Any]] = []
    for it in analyses:
        meta = it.get("meta") or {}
        a = it.get("analysis") or {}
        compact_items.append({
            "index": it.get("index"),
            "url": it.get("url"),
            "title": meta.get("title"),
            "channel": meta.get("channel"),
            "published_at": meta.get("published_at"),
            "videoAnalysis": {
                "hookPattern": (a.get("hookPattern") if isinstance(a, dict) else None),
                "structureTemplate": (a.get("structureTemplate") if isinstance(a, dict) else None),
                "toneStyle": (a.get("toneStyle") if isinstance(a, dict) else None),
                "ctaTypes": (a.get("ctaTypes") if isinstance(a, dict) else None),
                "repeatedFrames": (a.get("repeatedFrames") if isinstance(a, dict) else None),
                "channelInsight": (a.get("channelInsight") if isinstance(a, dict) else None),
            }
        })

    bundle = json.dumps(compact_items, ensure_ascii=False)

    return f"""
너는 유튜브 쇼츠 채널의 '기획 컨셉'을 역공학하는 전문가다.
아래는 같은 채널(또는 유사 채널)에서 가져온 여러 영상의 분석 결과다.
이 결과들을 종합해서 채널의 고정 포맷과 전략을 추출하라.

[입력: 영상별 분석 묶음(JSON)]
{bundle}

---
다음 정보를 **반드시 JSON 형식으로만** 출력하라.
설명 문장, 주석, 마크다운은 절대 포함하지 마라.

{{
  "oneLineConcept": "...",
  "targetAudience": {{
    "core": "...",
    "whyTheyWatch": ["..."],
    "painPoints": ["..."]
  }},
  "fixedFormat": {{
    "introTemplate": "...",
    "hookTemplate": "...",
    "bodyTemplate": "...",
    "transitionTemplate": "...",
    "endingTemplate": "...",
    "ctaTemplate": "..."
  }},
  "toneAndStyleRules": {{
    "keywords": ["..."],
    "dos": ["..."],
    "donts": ["..."]
  }},
  "reusableFrames": [
    "자주 쓰는 문장 프레임 1",
    "자주 쓰는 문장 프레임 2"
  ],
  "taboosAndRisks": [
    "이탈 유발 포인트 / 금기"
  ],
  "shortsProductionChecklist": [
    "체크리스트 항목 1",
    "체크리스트 항목 2"
  ]
}}
""".strip()
