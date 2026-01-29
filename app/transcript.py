# app/transcript.py
from typing import List, Dict, Any, Optional, Tuple
from youtube_transcript_api import YouTubeTranscriptApi

def _to_segments(fetched) -> List[Dict[str, Any]]:
    """
    youtube-transcript-api의 FetchedTranscript를 raw list로 변환
    """
    raw = fetched.to_raw_data()  # [{text,start,duration},...]
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

def fetch_best_transcript(
    video_id: str,
    languages_priority: List[str],
    translate_targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    youtube-transcript-api==1.2.3 기준으로
    수동/자동/번역 자막을 최대한 확보.

    반환 포맷:
    {
      "ok": bool,
      "sourceType": "MANUAL"|"AUTO"|"TRANSLATED"|"FETCH"|"NONE",
      "language": str|None,
      "languageCode": str|None,
      "isGenerated": bool|None,
      "detail": {...} | None,
      "segments": [...]
    }
    """
    ytt_api = YouTubeTranscriptApi()

    # 1) TranscriptList 기반 (가장 강력)
    #    공식 문서: ytt_api.list(video_id) :contentReference[oaicite:2]{index=2}
    if hasattr(ytt_api, "list"):
        try:
            transcript_list = ytt_api.list(video_id)

            # (A) 수동 자막 우선
            try:
                t = transcript_list.find_manually_created_transcript(languages_priority)
                fetched = t.fetch()
                return {
                    "ok": True,
                    "sourceType": "MANUAL",
                    "language": getattr(fetched, "language", None),
                    "languageCode": getattr(fetched, "language_code", None),
                    "isGenerated": getattr(fetched, "is_generated", None),
                    "detail": None,
                    "segments": _to_segments(fetched),
                }
            except Exception:
                pass

            # (B) 자동 생성 자막
            try:
                t = transcript_list.find_generated_transcript(languages_priority)
                fetched = t.fetch()
                return {
                    "ok": True,
                    "sourceType": "AUTO",
                    "language": getattr(fetched, "language", None),
                    "languageCode": getattr(fetched, "language_code", None),
                    "isGenerated": getattr(fetched, "is_generated", None),
                    "detail": None,
                    "segments": _to_segments(fetched),
                }
            except Exception:
                pass

            # (C) 번역 자막 (원문 자막이 translatable이면 translate() 가능) :contentReference[oaicite:3]{index=3}
            # translate_targets를 안 주면 languages_priority를 대상으로 번역 시도
            targets = translate_targets or languages_priority
            # 원문 후보: TranscriptList에서 아무거나 찾기 (우선순위 언어 먼저)
            base = None
            try:
                base = transcript_list.find_transcript(languages_priority)
            except Exception:
                # 우선순위 언어가 전혀 없으면 transcript_list 순회 중 첫 개로 시도
                try:
                    base = next(iter(transcript_list))
                except Exception:
                    base = None

            if base is not None and getattr(base, "is_translatable", False):
                for tgt in targets:
                    try:
                        translated = base.translate(tgt)  # :contentReference[oaicite:4]{index=4}
                        fetched = translated.fetch()
                        segs = _to_segments(fetched)
                        if segs:
                            return {
                                "ok": True,
                                "sourceType": "TRANSLATED",
                                "language": getattr(fetched, "language", None),
                                "languageCode": getattr(fetched, "language_code", None),
                                "isGenerated": getattr(fetched, "is_generated", None),
                                "detail": {
                                    "baseLanguageCode": getattr(base, "language_code", None),
                                    "targetLanguageCode": tgt,
                                },
                                "segments": segs,
                            }
                    except Exception:
                        continue

            return {
                "ok": False,
                "sourceType": "NONE",
                "language": None,
                "languageCode": None,
                "isGenerated": None,
                "detail": {"error": "NO_TRANSCRIPT_FOUND"},
                "segments": [],
            }

        except Exception as e:
            # list() 자체가 막힘 (IP 차단 등)
            return {
                "ok": False,
                "sourceType": "NONE",
                "language": None,
                "languageCode": None,
                "isGenerated": None,
                "detail": {"error": "LIST_FAILED", "message": str(e)},
                "segments": [],
            }

    # 2) fallback: list()가 없는 옛 API/환경이면 fetch()를 언어 우선순위대로 시도
    # 공식 fetch(video_id, languages=[...]) :contentReference[oaicite:5]{index=5}
    for lang in (languages_priority or []):
        try:
            fetched = ytt_api.fetch(video_id, languages=[lang], preserve_formatting=False)
            segs = _to_segments(fetched)
            if segs:
                return {
                    "ok": True,
                    "sourceType": "FETCH",
                    "language": getattr(fetched, "language", None),
                    "languageCode": getattr(fetched, "language_code", None),
                    "isGenerated": getattr(fetched, "is_generated", None),
                    "detail": {"note": "fallback_fetch_used"},
                    "segments": segs,
                }
        except Exception:
            continue

    # 최종 실패
    return {
        "ok": False,
        "sourceType": "NONE",
        "language": None,
        "languageCode": None,
        "isGenerated": None,
        "detail": {"error": "FETCH_FAILED_ALL_LANGS"},
        "segments": [],
    }
