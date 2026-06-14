import os
import tempfile
import logging
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


async def transcribe_audio(audio_bytes: bytes, content_type: str) -> dict:
    """Transcribe audio to Persian text. Returns {"transcript": str} or {"transcript": "", "error": str}."""

    # Determine file extension from content type
    ext_map = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }
    ext = ext_map.get(content_type, "webm")

    # Strategy 1: OpenAI Whisper
    if OPENAI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": (f"audio.{ext}", audio_bytes, content_type)},
                    data={"model": "whisper-1", "language": "fa"},
                )
                if response.status_code == 200:
                    return {"transcript": response.json().get("text", "")}
                logger.warning("OpenAI Whisper failed: %s %s", response.status_code, response.text)
        except Exception as e:
            logger.warning("OpenAI Whisper exception: %s", e)

    # Fallback: save to disk and return error
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            f.write(audio_bytes)
            logger.info("STT not configured, audio saved to %s", f.name)
    except Exception:
        pass

    return {"transcript": "", "error": "STT not configured"}
