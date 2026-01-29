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


def _build_ytt_api() -> YouTubeTranscriptApi:
    """
    Cloud Run/GCP 같은 데이터센터 IP에서 유튜브가 transcript 요청을 막는 케이스가 많아서
    youtube-transcript-api가 proxy_config를 공식 지원함.

    env 우선순위:
      1) Webshare 프록시:
         - WEBSHARE_PROXY_USERNAME
         - WEBSHARE_PROXY_PASSWORD
         - (옵션) WEBSHARE_FILTER_IP_LOCATIONS=kr,us,jp
      2) Generic 프록시:
         - PROXY_HTTP_URL=http://user:pass@host:port
         - PROXY_HTTPS_URL=https://user:pass@host:port
      3) 프록시 없음
    """
    ws_user = os.getenv("WEBSHARE_PROXY_USERNAME", "").strip()
    ws_pass = os.getenv("WEBSHARE_PROXY_PASSWORD", "").strip()
    ws_locs = os.getenv("WEBSHARE_FILTER_IP_LOCATIONS", "").strip()

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

    http_url = os.getenv("PROXY_HTTP_URL", "").strip()
    https_url = os.getenv("PROXY_HTTPS_URL", "").strip()
    if http_url or https_url:
        proxy_cfg = GenericProxyConfig(
            http_url=http_url or None,
            https_url=https_url or None,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_cfg)

    return YouTubeTranscriptApi()


# ✅ 싱글톤(요청마다 새로 만들면 느리고 안정성도 떨어짐)
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


def fetch_best_transcript(
    video_id: str,
    languages_priority: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    목표:
      1) list_transcripts(또는 list) 기반으로 "수동 → 자동 → 번역" 최대한 확보
      2) list 계열 메서드가 없거나 깨지면: get_transcript를 언어 우선순위대로 순차 시도
      3) 전부 실패하면 sourceType=NONE

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

    # -----------------------------------------
    # 1) list_transcripts / list 기반 (가능하면 이게 제일 강력)
    #    - 버전에 따라 API 이름이 다를 수 있어: list_transcripts 또는 list
    # -----------------------------------------
    try:
        transcript_list = None

        if hasattr(_YTT_API, "list_transcripts"):
            transcript_list = _YTT_API.list_transcripts(video_id)
            list_method = "list_transcripts"
        elif hasattr(_YTT_API, "list"):
            transcript_list = _YTT_API.list(video_id)
            list_method = "list"
        else:
            transcript_list = None
            list_method = None

        if transcript_list is not None:
            # 1-1) 수동 자막
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

            # 1-2) 자동 생성 자막
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

            # 1-3) 번역 자막(가능하면)
            #      "선호 언어(보통 ko)"로 번역 가능한 transcript가 있으면 translate() 후 fetch()
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

            # list는 성공했는데 매칭 실패
            return {
                "ok": False,
                "sourceType": "NONE",
                "language": None,
                "languageCode": None,
                "isGenerated": None,
                "segments": [],
                "detail": {"error": "NO_MATCH_IN_LIST", "path": list_method},
            }

    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, CouldNotRetrieveTranscript) as e:
        # ✅ 네가 지금 맞고 있는 "클라우드 IP 차단"도 여기로 떨어지는 경우가 흔함
        return {
            "ok": False,
            "sourceType": "NONE",
            "language": None,
            "languageCode": None,
            "isGenerated": None,
            "segments": [],
            "detail": {"error": "LIST_OR_FETCH_FAILED", "message": str(e)},
        }
    except Exception as e:
        # list 단계 자체가 깨지면 아래 get_transcript 폴백으로
        list_error = str(e)
    else:
        list_error = None

    # -----------------------------------------
    # 2) list 계열 메서드가 없거나/깨졌을 때: get_transcript를 언어별 순차 시도
    #    - 이 경로는 수동/자동 구분이 어려워서 sourceType=FETCH로 표기
    # -----------------------------------------
    try:
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            for lang in langs:
                try:
                    segs_raw = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
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
