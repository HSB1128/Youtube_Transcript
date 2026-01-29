# app/transcript.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    CouldNotRetrieveTranscript,
)
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _looks_like_placeholder_proxy(url: str) -> bool:
    """
    Cloud Run에 흔히 'http://USERNAME:PASSWORD@...' 같은 placeholder가 남아있을 수 있음.
    이게 잡히면 실제 인증이 아니라서 407 유발 가능.
    """
    u = (url or "").upper()
    return ("USERNAME:PASSWORD@" in u) or ("<USERNAME>" in u) or ("<PASSWORD>" in u)


def _build_ytt_api() -> YouTubeTranscriptApi:
    """
    우선순위:
      1) Webshare 프록시 (네가 지금 Cloud Run에 넣은 키)
         - WEBSHARE_PROXY_USERNAME
         - WEBSHARE_PROXY_PASSWORD
         - (옵션) WEBSHARE_FILTER_IP_LOCATIONS=kr,jp,us
      2) Generic 프록시 (표준)
         - PROXY_HTTP_URL / PROXY_HTTPS_URL
         - HTTP_PROXY / HTTPS_PROXY  (Cloud Run에서 자주 쓰는 표준 키)
      3) 프록시 없이
    """

    # -------------------------
    # 1) Webshare (최우선)
    # -------------------------
    ws_user = _env("WEBSHARE_PROXY_USERNAME")
    ws_pass = _env("WEBSHARE_PROXY_PASSWORD")
    ws_locs = _env("WEBSHARE_FILTER_IP_LOCATIONS")

    if ws_user and ws_pass:
        filter_locs = None
        if ws_locs:
            filter_locs = [x.strip() for x in ws_locs.split(",") if x.strip()]

        proxy_cfg = WebshareProxyConfig(
            proxy_username=ws_user,
            proxy_password=ws_pass,
            filter_ip_locations=filter_locs,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_cfg)

    # -------------------------
    # 2) Generic Proxy
    # -------------------------
    # (a) 네가 쓰던 커스텀 키
    http_url = _env("PROXY_HTTP_URL")
    https_url = _env("PROXY_HTTPS_URL")

    # (b) 표준 키 (Cloud Run/requests가 자주 쓰는)
    if not http_url:
        http_url = _env("HTTP_PROXY")
    if not https_url:
        https_url = _env("HTTPS_PROXY")

    # placeholder면 무시 (407 유발 가능)
    if _looks_like_placeholder_proxy(http_url):
        http_url = ""
    if _looks_like_placeholder_proxy(https_url):
        https_url = ""

    if http_url or https_url:
        proxy_cfg = GenericProxyConfig(
            http_url=http_url or None,
            https_url=https_url or None,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_cfg)

    # -------------------------
    # 3) No Proxy
    # -------------------------
    return YouTubeTranscriptApi()


# ✅ 싱글톤
_YTT_API = _build_ytt_api()


def _normalize_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in segments or []:
        if not isinstance(s, dict):
            continue
        out.append(
            {
                "text": s.get("text", "") or "",
                "start": float(s.get("start") or 0.0),
                "duration": float(s.get("duration") or 0.0),
            }
        )
    return out


def _try_get_transcript_via_api(
    api: YouTubeTranscriptApi,
    video_id: str,
    languages: List[str],
) -> Optional[List[Dict[str, Any]]]:
    """
    youtube-transcript-api 버전에 따라:
    - api.get_transcript(...) 가 있거나
    - YouTubeTranscriptApi.get_transcript(...) (클래스 메서드)만 있을 수 있음.
    프록시 설정을 최대한 타게 하려면 "인스턴스 메서드 우선" 시도.
    """
    # 1) 인스턴스 메서드 우선
    if hasattr(api, "get_transcript"):
        return api.get_transcript(video_id, languages=languages)  # type: ignore[attr-defined]

    # 2) 클래스 메서드 폴백
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        return YouTubeTranscriptApi.get_transcript(video_id, languages=languages)

    return None


def fetch_best_transcript(
    video_id: str,
    languages_priority: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    네 요구사항 반영:

    1) hasattr(YouTubeTranscriptApi, "list_transcripts") 로 메서드 존재 확인
       - 있으면 기존 방식(수동→자동→번역) 사용
    2) 메서드가 없을 경우(or list단이 실패한 경우)
       - get_transcript(video_id, languages=[lang]) 를 langs 순서대로 시도
    3) 둘 다 실패하면 sourceType=NONE

    반환:
    {
      ok, sourceType(MANUAL/AUTO/TRANSLATED/FETCH/NONE),
      language, languageCode, isGenerated,
      segments, detail
    }
    """
    langs = [l.strip() for l in (languages_priority or []) if isinstance(l, str) and l.strip()]
    if not langs:
        langs = ["ko", "ko-KR", "en", "en-US", "en-GB"]

    list_error: Optional[str] = None

    # -----------------------------------------
    # 1) list_transcripts 기반: 수동 → 자동 → 번역
    # -----------------------------------------
    try:
        # ✅ 네가 원한 체크 방식 (클래스 기준)
        has_list = hasattr(YouTubeTranscriptApi, "list_transcripts")

        if has_list and hasattr(_YTT_API, "list_transcripts"):
            transcript_list = _YTT_API.list_transcripts(video_id)
            list_method = "list_transcripts"

            # 1-1) 수동
            try:
                t = transcript_list.find_manually_created_transcript(langs)
                segs = _normalize_segments(t.fetch())
                if segs:
                    return {
                        "ok": True,
                        "sourceType": "MANUAL",
                        "language": getattr(t, "language", None),
                        "languageCode": getattr(t, "language_code", None),
                        "isGenerated": getattr(t, "is_generated", None),
                        "segments": segs,
                        "detail": {"path": f"{list_method}->manual"},
                    }
            except Exception:
                pass

            # 1-2) 자동
            try:
                t = transcript_list.find_generated_transcript(langs)
                segs = _normalize_segments(t.fetch())
                if segs:
                    return {
                        "ok": True,
                        "sourceType": "AUTO",
                        "language": getattr(t, "language", None),
                        "languageCode": getattr(t, "language_code", None),
                        "isGenerated": getattr(t, "is_generated", None),
                        "segments": segs,
                        "detail": {"path": f"{list_method}->auto"},
                    }
            except Exception:
                pass

            # 1-3) 번역
            try:
                target = langs[0]  # 예: ko
                for base in transcript_list:
                    try:
                        translated = base.translate(target)
                        segs = _normalize_segments(translated.fetch())
                        if segs:
                            return {
                                "ok": True,
                                "sourceType": "TRANSLATED",
                                "language": getattr(translated, "language", None),
                                "languageCode": getattr(translated, "language_code", None),
                                "isGenerated": getattr(translated, "is_generated", None),
                                "segments": segs,
                                "detail": {
                                    "path": f"{list_method}->translate",
                                    "target": target,
                                    "baseLanguageCode": getattr(base, "language_code", None),
                                },
                            }
                    except Exception:
                        continue
            except Exception:
                pass

            # list는 됐는데 매칭 실패
            list_error = "NO_MATCH_IN_LIST"
        else:
            list_error = "LIST_TRANSCRIPTS_NOT_AVAILABLE"

    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, CouldNotRetrieveTranscript) as e:
        # list 단계에서 막히면 get_transcript 폴백
        list_error = str(e)
    except Exception as e:
        list_error = str(e)

    # -----------------------------------------
    # 2) get_transcript 폴백: 언어 우선순위대로 하나씩 시도
    #    - 수동/자동 구분 어려워 sourceType=FETCH
    # -----------------------------------------
    try:
        for lang in langs:
            try:
                segs_raw = _try_get_transcript_via_api(_YTT_API, video_id, [lang])
                if not segs_raw:
                    continue
                segs = _normalize_segments(segs_raw)
                if segs:
                    return {
                        "ok": True,
                        "sourceType": "FETCH",
                        "language": lang,
                        "languageCode": lang,
                        "isGenerated": None,
                        "segments": segs,
                        "detail": {"path": "get_transcript", "tried": langs, "list_error": list_error},
                    }
            except Exception:
                continue
    except Exception as e:
        return {
            "ok": False,
            "sourceType": "NONE",
            "language": None,
            "languageCode": None,
            "isGenerated": None,
            "segments": [],
            "detail": {"error": "GET_TRANSCRIPT_FAILED", "message": str(e), "list_error": list_error},
        }

    # -----------------------------------------
    # 3) 완전 실패
    # -----------------------------------------
    return {
        "ok": False,
        "sourceType": "NONE",
        "language": None,
        "languageCode": None,
        "isGenerated": None,
        "segments": [],
        "detail": {"error": "NO_TRANSCRIPT", "message": "No transcript available or blocked.", "list_error": list_error},
    }
