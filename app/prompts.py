def build_video_analysis_prompt(
    index: int,
    title: str,
    description: str,
    transcript: str,
) -> str:
    return f"""
너는 유튜브 쇼츠/영상 기획 전문 분석가다.
아래 영상의 **전체 자막을 처음부터 끝까지 모두 읽고 분석**하라.

[영상 번호]
{index}

[제목 - 원문 그대로]
{title}

[설명 - 300자 이내]
{description}

[전체 자막]
{transcript}

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
"""

