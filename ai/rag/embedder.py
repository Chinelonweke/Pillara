# ai/rag/embedder.py
#
# Local embeddings via fastembed — no API calls, no PHI sent externally, free forever.
# Used both at ingestion time (embedding drug chunks for ChromaDB)
# and implicitly by ChromaDB's query() — but we expose this directly
# for cases where we need raw embeddings (e.g. precomputing for ingestion).

import asyncio
from typing import Optional

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


class Embedder:
    """
    Wraps fastembed for generating local embeddings.

    WHY fastembed (not OpenAI embeddings API):
    1. No PHI ever leaves our server — critical for HIPAA compliance
    2. Free forever — no per-embedding API cost
    3. Fast — optimised ONNX runtime, 2-3x faster than sentence-transformers
    4. Good enough quality for drug information retrieval at our scale

    SINGLETON PATTERN:
    The embedding model is loaded once and reused.
    Loading takes ~2 seconds — we don't want that cost on every request.
    """

    _instance: Optional["Embedder"] = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            logger.info("embedding_model_loading", model=settings.EMBEDDING_MODEL)
            self._model = TextEmbedding(model_name=settings.EMBEDDING_MODEL)
            logger.info("embedding_model_loaded")
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a list of texts. Returns a list of embedding vectors.
        Runs in a thread pool since fastembed is synchronous.
        """
        def _sync_embed():
            model = self._load_model()
            embeddings = list(model.embed(texts))
            return [emb.tolist() for emb in embeddings]

        return await asyncio.to_thread(_sync_embed)

    async def embed_single(self, text: str) -> list[float]:
        """Embeds a single text string."""
        results = await self.embed_texts([text])
        return results[0]