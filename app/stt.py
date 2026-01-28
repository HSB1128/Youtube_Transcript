import os, subprocess, tempfile
from typing import Dict, Any, List
from faster_whisper import WhisperModel

STT_MODEL = os.getenv("STT_MODEL", "small")

def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)

def stt_from_youtube_url(url: str) -> Dict[str, Any]:
    """
    1) yt-dlp 로 오디오 다운로드
    2) ffmpeg 로 wav(16k mono) 변환
    3) faster-whisper로 세그먼트 생성
    """
    with tempfile.TemporaryDirectory() as td:
        audio_path = os.path.join(td, "audio.m4a")
        wav_path = os.path.join(td, "audio.wav")

        cmd = ["yt-dlp", "-f", "bestaudio", "--no-playlist", "-o", audio_path, url]
        p = _run(cmd)
        if p.returncode != 0:
            return {"ok": False, "error": f"yt-dlp failed", "detail": p.stderr[:2000], "segments": []}

        cmd2 = ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", wav_path]
        p2 = _run(cmd2)
        if p2.returncode != 0:
            return {"ok": False, "error": f"ffmpeg failed", "detail": p2.stderr[:2000], "segments": []}

        try:
            model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")
            segments, info = model.transcribe(wav_path, beam_size=1, vad_filter=True)

            out: List[Dict[str, Any]] = []
            for seg in segments:
                text = (seg.text or "").strip()
                if not text:
                    continue
                start = float(seg.start)
                end = float(seg.end)
                out.append({
                    "start": start,
                    "duration": max(0.0, end - start),
                    "text": text
                })

            return {
                "ok": True,
                "language": getattr(info, "language", None),
                "segments": out
            }
        except Exception as e:
            return {"ok": False, "error": "whisper failed", "detail": str(e), "segments": []}
