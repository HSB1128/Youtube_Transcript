from typing import List, Dict, Any, Optional, Tuple
from youtube_transcript_api import YouTubeTranscriptApi


def _normalize_segments(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    segs: List[Dict[str, Any]] = []
    for x in raw or []:
        text = (x.get("text") or "").strip()
        if not text:
            continue
        segs.append({
            "start": float(x.get("start", 0.0)),
            "duration": float(x.get("duration", 0.0)),
            "text": text,
        })
    return segs


def _uniq_keep_order(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        k = (x or "").strip().lower()
        if not k:
            continue
        if k not in seen:
            out.append((x or "").strip())
            seen.add(k)
    return out


def _expand_languages(langs: List[str]) -> List[str]:
    """
    ko만/ en만 주더라도 변형을 함께 시도해 자막 매칭 확률을 높임.
    """
    base = _uniq_keep_order(langs or [])
    if not base:
        base = ["ko", "en"]

    expanded: List[str] = []
    for x in base:
        lx = x.lower()
        if lx in ["ko", "ko-kr"]:
            expanded += ["ko", "ko-KR"]
        elif lx in ["en", "en-us"]:
            expanded += ["en", "en-US"]
        else:
            expanded.append(x)

    return _uniq_keep_order(expanded)


def fetch_best_transcript(
    video_id: str,
    languages: List[str],
    prefer_translate_targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    반환:
    {
      "ok": bool,
      "segments": [...],
      "sourceType": "MANUAL" | "AUTO" | "TRANSLATED" | "NONE",
      "language": "ko" 같은 코드,
      "detail": { ... }
    }

    우선순위:
    1) 수동 자막 (MANUAL)
    2) 자동 생성 자막 (AUTO)
    3) 번역 자막 (TRANSLATED)  - 가능한 경우
    """
    prefer_langs = _expand_languages(languages)
    translate_targets = _expand_languages(prefer_translate_targets or ["ko", "en"])

    try:
        tl = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception as e:
        return {
            "ok": False,
            "segments": [],
            "sourceType": "NONE",
            "language": None,
            "detail": {"error": "LIST_TRANSCRIPTS_FAILED", "message": str(e)},
        }

    # --- 1) MANUAL 먼저: prefer_langs 순서대로 찾기 ---
    # youtube_transcript_api는 find_transcript / find_manually_created_transcript 등을 제공
    # (버전에 따라 차이가 있을 수 있어 try/except로 안전하게)
    for lang in prefer_langs:
        try:
            t = tl.find_manually_created_transcript([lang])
            raw = t.fetch()
            segs = _normalize_segments(raw)
            if segs:
                return {
                    "ok": True,
                    "segments": segs,
                    "sourceType": "MANUAL",
                    "language": getattr(t, "language_code", lang),
                    "detail": {
                        "requested": prefer_langs,
                        "picked": lang,
                        "isGenerated": False,
                        "isTranslated": False,
                    },
                }
        except Exception:
            pass

    # --- 2) AUTO(자동 생성) ---
    for lang in prefer_langs:
        try:
            t = tl.find_generated_transcript([lang])
            raw = t.fetch()
            segs = _normalize_segments(raw)
            if segs:
                return {
                    "ok": True,
                    "segments": segs,
                    "sourceType": "AUTO",
                    "language": getattr(t, "language_code", lang),
                    "detail": {
                        "requested": prefer_langs,
                        "picked": lang,
                        "isGenerated": True,
                        "isTranslated": False,
                    },
                }
        except Exception:
            pass

    # --- 3) TRANSLATED (번역 자막) ---
    # 전략: (a) 어떤 자막이든 하나 잡아서 (b) translate_targets 우선순위로 translate 시도
    # 번역은 원본이 manual인지 auto인지에 따라 신뢰도를 다르게 줄 수 있게 sourceOrigin 기록
    source_origin = None
    base_t = None

    # 3-1) base transcript를 먼저 확보: manual 우선, 없으면 auto
    try:
        # manual 아무거나 하나
        for t in tl:
            if not getattr(t, "is_generated", False):
                base_t = t
                source_origin = "MANUAL"
                break
        if base_t is None:
            for t in tl:
                if getattr(t, "is_generated", False):
                    base_t = t
                    source_origin = "AUTO"
                    break
    except Exception:
        base_t = None

    if base_t is not None and getattr(base_t, "is_translatable", False):
        for tgt in translate_targets:
            try:
                tt = base_t.translate(tgt)
                raw = tt.fetch()
                segs = _normalize_segments(raw)
                if segs:
                    return {
                        "ok": True,
                        "segments": segs,
                        "sourceType": "TRANSLATED",
                        "language": tgt,
                        "detail": {
                            "translatedTo": tgt,
                            "sourceOrigin": source_origin,   # MANUAL or AUTO
                            "isGenerated": (source_origin == "AUTO"),
                            "isTranslated": True,
                        },
                    }
            except Exception:
                pass

    # 전부 실패
    return {
        "ok": False,
        "segments": [],
        "sourceType": "NONE",
        "language": None,
        "detail": {
            "requested": prefer_langs,
            "translateTargets": translate_targets,
            "error": "NO_TRANSCRIPT_FOUND",
        },
    }
