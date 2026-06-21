# ai/tts/tts_client.py

import asyncio
import os
import uuid
from monitoring.logger import get_logger

logger = get_logger(__name__)

TTS_OUTPUT_DIR = "/tmp/pillara_tts"


class TTSClient:
    """
    Local Coqui TTS — runs entirely on the server.
    No text is sent to external APIs — HIPAA compliant by design.
    Audio files are stored in /tmp with UUID names and deleted after serving.
    """

    def __init__(self):
        self._tts = None

    def _load_model(self):
        if self._tts is None:
            from TTS.api import TTS
            logger.info("tts_model_loading")
            self._tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")
            logger.info("tts_model_loaded")
        return self._tts

    async def synthesize(self, text: str) -> str:
        """
        Converts text to speech. Returns the path to the generated audio file.
        Caller is responsible for serving and deleting the file.
        """
        os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(TTS_OUTPUT_DIR, f"{uuid.uuid4()}.wav")

        def _sync_synthesize():
            tts = self._load_model()
            tts.tts_to_file(text=text, file_path=output_path)

        await asyncio.to_thread(_sync_synthesize)
        logger.info("tts_synthesis_complete", output_path=output_path)
        return output_path