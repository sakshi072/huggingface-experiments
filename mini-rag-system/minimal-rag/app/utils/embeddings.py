"""
Shared embedding model loader with caching.
"""

import logging
from functools import lru_cache
import asyncio
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_shared_embedder(embedding_model: str) -> SentenceTransformer:
    """
    Load and cache the embedding model (singleton).

    Args:
        embedding_model: Model name/path to load.

    Returns:
        Loaded SentenceTransformer model.
    """
    logger.info(f"Loading embedding model: {embedding_model}")
    return SentenceTransformer(embedding_model)

async def embed_chunks(texts: list[str], model_name: str):
    loop = asyncio.get_running_loop()
    embedder = get_shared_embedder(model_name)

    return await loop.run_in_executor(
        None,
        lambda: embedder.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    )