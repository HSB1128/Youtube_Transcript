# app/transcript.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from youtube_transcript_api import YouTubeTranscriptApi


def _to_segments(obj: Any) -> List[Dict[str, Any]]:
    """
    youtube-transcript-api 1.2.3:
      - fetch() returns FetchedTranscript (iterable) with .to_raw_data()
    legacy:
      - get_transcript() returns List[dict]
    """
    if obj is None:
        return []
    # 1) 1.2.3 FetchedTranscript
    if hasattr(obj, "to_raw_data"):
        try:
            raw = obj.to_raw_data()
            # normalize key names just in case
            out = []
            for s in raw:
                out.append({
                    "text": s.get("text", ""),
                    "start": float(s.get("start", 0.0)),
                    "duration": float(s.get("duration", 0.0)),
                })
            return out
        except Exception:
            pass

    # 2) legacy list[dict]
    if isinstance(obj, list):
        out = []
        for s in obj:
            if isinstance(s, dict):
                out.append({
                    "text": s.get("text", ""),
                    "start": float(s.get("start", 0.0)),
                    "duration": float(s.get("duration", 0.0)),
                })
        return out

    return []


def fetch_best_transcript(
    video_id: str,
    languages_priority: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Returns:
      {
        ok: bool,
        sourceType: "MANUAL" | "AUTO" | "TRANSLATED" | "FETCH" | "NONE",
        language: str|None,
        languageCode: str|None,
        isGenerated: bool|None,
        segments: [ {text,start,duration}, ... ],
        detail: { ... optional debug info ... }
      }
    """
    languages_priority = languages_priority or ["ko", "ko-KR", "en", "en-US", "en-GB"]

    # --- 0) legacy API path (only if exists) ---
    # Some older versions had classmethods list_transcripts/get_transcript.
    try:
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            # Legacy transcript list approach
            tl = YouTubeTranscriptApi.list_transcripts(video_id)

            # MANUAL → AUTO → TRANSLATED
            # (Legacy TranscriptList API may differ by version; keep try/except tight.)
            for kind in ("MANUAL", "AUTO"):
                try:
                    if kind == "MANUAL":
                        tr = tl.find_manually_created_transcript(languages_priority)
                    else:
                        tr = tl.find_generated_transcript(languages_priority)
                    fetched = tr.fetch()
                    segs = _to_segments(fetched)
                    if segs:
                        return {
                            "ok": True,
                            "sourceType": "MANUAL" if kind == "MANUAL" else "AUTO",
                            "language": getattr(tr, "language", None),
                            "languageCode": getattr(tr, "language_code", None),
                            "isGenerated": getattr(tr, "is_generated", None),
                            "segments": segs,
                            "detail": {"path": "legacy_list_transcripts"},
                        }
                except Exception:
                    pass

            # TRANSLATED: pick any translatable transcript, translate to first target language that works
            try:
                base = None
                for t in tl:
                    if getattr(t, "is_translatable", False):
                        base = t
                        break
                if base is not None:
                    for target in languages_priority:
                        try:
                            translated = base.translate(target)
                            fetched = translated.fetch()
                            segs = _to_segments(fetched)
                            if segs:
                                return {
                                    "ok": True,
                                    "sourceType": "TRANSLATED",
                                    "language": getattr(translated, "language", None),
                                    "languageCode": getattr(translated, "language_code", None),
                                    "isGenerated": getattr(base, "is_generated", None),
                                    "segments": segs,
                                    "detail": {
                                        "path": "legacy_translate",
                                        "baseLanguageCode": getattr(base, "language_code", None),
                                        "target": target,
                                    },
                                }
                        except Exception:
                            continue
            except Exception:
                pass

            return {
                "ok": False,
                "sourceType": "NONE",
                "language": None,
                "languageCode": None,
                "isGenerated": None,
                "segments": [],
                "detail": {"error": "LEGACY_LIST_TRANSCRIPTS_FOUND_BUT_NO_MATCH"},
            }
    except Exception as e:
        # fall through to 1.2.3 path
        legacy_err = str(e)
    else:
        legacy_err = None

    # --- 1) youtube-transcript-api 1.2.3 (official) ---
    # Use ytt_api.list(video_id) and find_* methods, then fetch().
    try:
        ytt_api = YouTubeTranscriptApi()

        # 1) list available transcripts
        if not hasattr(ytt_api, "list"):
            # ultra-fallback: try legacy get_transcript if available
            if hasattr(YouTubeTranscriptApi, "get_transcript"):
                for lang in languages_priority:
                    try:
                        raw = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
                        segs = _to_segments(raw)
                        if segs:
                            return {
                                "ok": True,
                                "sourceType": "FETCH",
                                "language": None,
                                "languageCode": lang,
                                "isGenerated": None,
                                "segments": segs,
                                "detail": {"path": "fallback_get_transcript", "lang": lang},
                            }
                    except Exception:
                        continue
            return {
                "ok": False,
                "sourceType": "NONE",
                "language": None,
                "languageCode": None,
                "isGenerated": None,
                "segments": [],
                "detail": {"error": "NO_LIST_METHOD_ON_YTT_API"},
            }

        transcript_list = ytt_api.list(video_id)

        # 2) MANUAL first
        try:
            t = transcript_list.find_manually_created_transcript(languages_priority)
            fetched = t.fetch()
            segs = _to_segments(fetched)
            if segs:
                return {
                    "ok": True,
                    "sourceType": "MANUAL",
                    "language": getattr(t, "language", None),
                    "languageCode": getattr(t, "language_code", None),
                    "isGenerated": getattr(t, "is_generated", None),  # should be False
                    "segments": segs,
                    "detail": {"path": "v1.2.3_manual"},
                }
        except Exception:
            pass

        # 3) AUTO (generated) next
        try:
            t = transcript_list.find_generated_transcript(languages_priority)
            fetched = t.fetch()
            segs = _to_segments(fetched)
            if segs:
                return {
                    "ok": True,
                    "sourceType": "AUTO",
                    "language": getattr(t, "language", None),
                    "languageCode": getattr(t, "language_code", None),
                    "isGenerated": getattr(t, "is_generated", None),  # should be True
                    "segments": segs,
                    "detail": {"path": "v1.2.3_auto"},
                }
        except Exception:
            pass

        # 4) TRANSLATED (YouTube auto-translate)
        # pick a base transcript that is_translatable, translate to preferred target language
        base = None
        for t in transcript_list:
            if getattr(t, "is_translatable", False):
                base = t
                break

        if base is not None:
            for target in languages_priority:
                try:
                    translated = base.translate(target)
                    fetched = translated.fetch()
                    segs = _to_segments(fetched)
                    if segs:
                        return {
                            "ok": True,
                            "sourceType": "TRANSLATED",
                            "language": getattr(translated, "language", None),
                            "languageCode": getattr(translated, "language_code", None),
                            "isGenerated": getattr(base, "is_generated", None),
                            "segments": segs,
                            "detail": {
                                "path": "v1.2.3_translated",
                                "baseLanguageCode": getattr(base, "language_code", None),
                                "target": target,
                            },
                        }
                except Exception:
                    continue

        # 5) last resort: direct fetch() with languages_priority (module default prefers manual)
        try:
            fetched = ytt_api.fetch(video_id, languages=languages_priority)
            segs = _to_segments(fetched)
            if segs:
                return {
                    "ok": True,
                    "sourceType": "FETCH",
                    "language": getattr(fetched, "language", None),
                    "languageCode": getattr(fetched, "language_code", None),
                    "isGenerated": getattr(fetched, "is_generated", None),
                    "segments": segs,
                    "detail": {"path": "v1.2.3_fetch"},
                }
        except Exception as e:
            fetch_err = str(e)
        else:
            fetch_err = None

        return {
            "ok": False,
            "sourceType": "NONE",
            "language": None,
            "languageCode": None,
            "isGenerated": None,
            "segments": [],
            "detail": {
                "error": "NO_TRANSCRIPT",
                "legacy_error": legacy_err,
                "fetch_error": fetch_err,
            },
        }

    except Exception as e:
        return {
            "ok": False,
            "sourceType": "NONE",
            "language": None,
            "languageCode": None,
            "isGenerated": None,
            "segments": [],
            "detail": {
                "error": "LIST_OR_FETCH_FAILED",
                "message": str(e),
                "legacy_error": legacy_err,
            },
        }
