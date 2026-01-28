# YouTube Transcription + Analysis Extractor (Cloud Run)

## Endpoints
- GET /health
- POST /analyze

## Environment Variables
- YOUTUBE_API_KEY (required)
- SCENE_SEC (default: 2.0)
- ENABLE_STT (default: true)
- STT_MODEL (default: small)
- MAX_DURATION_SEC_FOR_STT (default: 900)
- MAX_SCENES_PER_VIDEO (default: 18)
- MAX_CHARS_PER_SCENE (default: 160)

## Request Example
POST /analyze
```json
{
  "urls": ["https://www.youtube.com/watch?v=xxxx", "..."],
  "languages": ["ko","en"],
  "include_stats": true,
  "stt_fallback": true
}



---

# 12) Cloud Run 배포 시 설정(꼭)
Cloud Run 서비스 설정에서 최소:
- **CPU / Memory**: STT 때문에 최소 2CPU / 2~4GB 권장(가능하면)
- **Timeout**: 길게(최소 5~10분)
- **환경변수**:
  - `YOUTUBE_API_KEY=...`
  - (선택) `ENABLE_STT=true`
  - (선택) `MAX_DURATION_SEC_FOR_STT=900` (15분)  
    → 너가 더 짧게 하고 싶으면 300(5분) 같은 식으로 제한해도 됨

---

# 13) n8n에서 바로 호출하기 위한 입력 예시(참고)
POST `/analyze` body:
```json
{
  "urls": {{ $json["Reference URL"].split(/\r?\n/).map(s => s.trim()).filter(Boolean) }},
  "languages": ["ko","en"],
  "stt_fallback": true
}
