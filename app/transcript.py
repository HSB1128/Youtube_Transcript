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
    RequestBlocked,
    IpBlocked,
)
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig


def _build_ytt_api() -> YouTubeTranscriptApi:
    """
    youtube-transcript-api (PyPI 1.2.3) 기준:
      - ytt_api.list(video_id)
      - ytt_api.fetch(video_id, languages=[...])
    프록시는 proxy_config로 주입.
    """

    # 0) (중요) Cloud Run 전역 프록시가 있으면 라이브러리 동작을 망칠 수 있음
    #    -> 여기서는 "참고용 경고"만 detail로 남기고, 강제로 unset 하진 않음.
    #    (운영 환경 변수는 Cloud Run 설정에서 제거하는 게 정답)

    ws_user = os.getenv("WEBSHARE_PROXY_USERNAME", "").strip()
    ws_pass = os.getenv("WEBSHARE_PROXY_PASSWORD", "").strip()
    ws_locs = os.getenv("WEBSHARE_FILTER_IP_LOCATIONS", "").strip()

    if ws_user and ws_pass:
        filter_locs = None
        if ws_locs:
            filter_locs = [x.strip() for x in ws_locs.split(",") if x.strip()]
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=ws_user,
                proxy_password=ws_pass,
                filter_ip_locations=filter_locs,
            )
        )

    # (옵션) 네가 “다른 프록시”를 쓰고 싶을 때만 사용
    http_url = os.getenv("PROXY_HTTP_URL", "").strip()
    https_url = os.getenv("PROXY_HTTPS_URL", "").strip()
    if http_url or https_url:
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(
                http_url=http_url or None,
                https_url=https_url or None,
            )
        )

    return YouTubeTranscriptApi()


_YTT_API = _build_ytt_api()


def _normalize_segments(raw: Any) -> List[Dict[str, Any]]:
    """
    FetchedTranscript.to_raw_data() 형태:
      [{'text':..., 'start':..., 'duration':...}, ...]
    """
    out: List[Dict[str, Any]] = []
    if not raw:
        return out
    if isinstance(raw, list):
        for s in raw:
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
    우선순위:
      1) list() -> 수동(manual) 우선
      2) list() -> 자동(auto)
      3) list() -> 번역(translate)
      4) fetch(languages=[...]) 폴백
    """

    langs = [l.strip() for l in (languages_priority or []) if isinstance(l, str) and l.strip()]
    if not langs:
        langs = ["ko", "ko-KR", "en", "en-US", "en-GB"]

    env_proxy_hint = {
        "HTTP_PROXY": os.getenv("HTTP_PROXY"),
        "HTTPS_PROXY": os.getenv("HTTPS_PROXY"),
    }

    # ----------------------------
    # 1) list() 기반 (가장 강력)
    # ----------------------------
    list_error = None
    try:
        transcript_list = _YTT_API.list(video_id)

        # 1-1) 수동
        try:
            t = transcript_list.find_manually_created_transcript(langs)
            fetched = t.fetch()
            segs = _normalize_segments(fetched.to_raw_data())
            if segs:
                return {
                    "ok": True,
                    "sourceType": "MANUAL",
                    "language": fetched.language,
                    "languageCode": fetched.language_code,
                    "isGenerated": fetched.is_generated,
                    "segments": segs,
                    "detail": {"path": "list->manual", "env_proxy_hint": env_proxy_hint},
                }
        except Exception:
            pass

        # 1-2) 자동
        try:
            t = transcript_list.find_generated_transcript(langs)
            fetched = t.fetch()
            segs = _normalize_segments(fetched.to_raw_data())
            if segs:
                return {
                    "ok": True,
                    "sourceType": "AUTO",
                    "language": fetched.language,
                    "languageCode": fetched.language_code,
                    "isGenerated": fetched.is_generated,
                    "segments": segs,
                    "detail": {"path": "list->auto", "env_proxy_hint": env_proxy_hint},
                }
        except Exception:
            pass

        # 1-3) 번역
        try:
            target = langs[0]  # 보통 ko
            for base in transcript_list:
                try:
                    if not getattr(base, "is_translatable", False):
                        continue
                    translated = base.translate(target)
                    fetched = translated.fetch()
                    segs = _normalize_segments(fetched.to_raw_data())
                    if segs:
                        return {
                            "ok": True,
                            "sourceType": "TRANSLATED",
                            "language": fetched.language,
                            "languageCode": fetched.language_code,
                            "isGenerated": fetched.is_generated,
                            "segments": segs,
                            "detail": {
                                "path": "list->translate",
                                "target": target,
                                "baseLanguageCode": getattr(base, "language_code", None),
                                "env_proxy_hint": env_proxy_hint,
                            },
                        }
                except Exception:
                    continue
        except Exception:
            pass

        # list 성공했는데 매칭이 안 된 경우
        return {
            "ok": False,
            "sourceType": "NONE",
            "language": None,
            "languageCode": None,
            "isGenerated": None,
            "segments": [],
            "detail": {"error": "NO_MATCH_IN_LIST", "path": "list", "env_proxy_hint": env_proxy_hint},
        }

    except (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
        CouldNotRetrieveTranscript,
        RequestBlocked,
        IpBlocked,
    ) as e:
        list_error = str(e)
    except Exception as e:
        list_error = str(e)

    # ----------------------------
    # 2) fetch() 폴백
    # ----------------------------
    try:
        fetched = _YTT_API.fetch(video_id, languages=langs)
        segs = _normalize_segments(fetched.to_raw_data())
        if segs:
            # fetch는 manual/auto 구분을 100% 확정하기 애매하지만 is_generated로 어느 정도 판단 가능
            source = "AUTO" if getattr(fetched, "is_generated", False) else "MANUAL"
            return {
                "ok": True,
                "sourceType": "FETCH",
                "language": fetched.language,
                "languageCode": fetched.language_code,
                "isGenerated": fetched.is_generated,
                "segments": segs,
                "detail": {"path": "fetch", "tried": langs, "list_error": list_error, "env_proxy_hint": env_proxy_hint},
            }
    except Exception as e:
        return {
            "ok": False,
            "sourceType": "NONE",
            "language": None,
            "languageCode": None,
            "isGenerated": None,
            "segments": [],
            "detail": {"error": "FETCH_FAILED", "message": str(e), "list_error": list_error, "env_proxy_hint": env_proxy_hint},
        }

    # ----------------------------
    # 3) 완전 실패
    # ----------------------------
    return {
        "ok": False,
        "sourceType": "NONE",
        "language": None,
        "languageCode": None,
        "isGenerated": None,
        "segments": [],
        "detail": {"error": "NO_TRANSCRIPT", "message": "No transcript available or blocked.", "list_error": list_error, "env_proxy_hint": env_proxy_hint},
    }
