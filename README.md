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
