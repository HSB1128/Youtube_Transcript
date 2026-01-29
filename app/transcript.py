from typing import List, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi

def _expand_languages(langs: List[str]) -> List[str]:
    """
    요청 언어를 '우선순위가 있는 확장 리스트'로 바꿔서
    자막이 걸릴 확률을 올린다.
    """
    base = [x.strip() for x in (langs or []) if (x or "").strip()]
    if not base:
        base = ["ko", "en"]

    # 우선순위: ko → ko-KR → en → en-US → ja → ... (필요시 더 추가)
    preferred = []
    for x in base:
        if x.lower() in ["ko", "ko-kr"]:
            preferred += ["ko", "ko-KR"]
        elif x.lower() in ["en", "en-us"]:
            preferred += ["en", "en-US"]
        else:
            preferred.append(x)

    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for x in preferred:
        k = x.lower()
        if k not in seen:
            out.append(x)
            seen.add(k)
    return out

def try_fetch_transcript_segments(video_id: str, languages: List[str]) -> List[Dict[str, Any]]:
    """
    유튜브 공개 자막/자동 생성 자막/번역 자막 중
    '공식적으로 노출되는' 자막이 있으면 최대한 가져온다.
    (단, 이 함수는 우회가 아니라 공개 자막 접근 시도 강화)
    """
    languages = _expand_languages(languages)

    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id, languages=languages, preserve_formatting=False)
        raw = fetched.to_raw_data()
        segs: List[Dict[str, Any]] = []
        for x in raw:
            text = (x.get("text") or "").strip()
            if not text:
                continue
            segs.append({
                "start": float(x.get("start", 0.0)),
                "duration": float(x.get("duration", 0.0)),
                "text": text,
            })
        return segs
    except Exception:
        return []
