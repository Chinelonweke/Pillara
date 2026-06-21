# ai/stt/whisper_client.py

import asyncio
import os
from monitoring.logger import get_logger

logger = get_logger(__name__)


class WhisperClient:
    """
    Local Whisper STT — runs entirely on the server.
    No audio data is sent to external APIs — HIPAA compliant by design.
    """

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            import whisper
            logger.info("whisper_model_loading", model_size=self.model_size)
            self._model = whisper.load_model(self.model_size)
            logger.info("whisper_model_loaded")
        return self._model

    async def transcribe(self, audio_path: str, language: str = "en") -> str:
        """
        Transcribes audio file to text.
        Runs in a thread pool — Whisper is synchronous and CPU-intensive.
        """
        def _sync_transcribe():
            model = self._load_model()
            result = model.transcribe(
                audio_path,
                language=language if language != "en" else None,
                # None = auto-detect language (more accurate for non-English)
                fp16=False,
                # fp16=False for CPU — fp16 is GPU only
            )
            return result["text"].strip()

        text = await asyncio.to_thread(_sync_transcribe)
        logger.info("whisper_transcription_complete", chars=len(text))
        return text