import os
import asyncio
from typing import List

from .ollama import embed as ollama_embed, OllamaError

_ST_MODEL = None

_MODEL_MAP = {
    # Map simple names to HF model IDs
    "nomic-embed-text": "nomic-ai/nomic-embed-text-v1.5",
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
}


def _get_st_model_id(name: str) -> str:
    return _MODEL_MAP.get(name, name)


async def _embed_with_st(texts: List[str], model_name: str) -> List[List[float]]:
    global _ST_MODEL
    from sentence_transformers import SentenceTransformer  # lazy import

    model_id = _get_st_model_id(model_name)
    if _ST_MODEL is None or getattr(_ST_MODEL, "_model_id", None) != model_id:
        # Some models (e.g., nomic) require trust_remote_code=True
        _ST_MODEL = SentenceTransformer(model_id, trust_remote_code=True)
        setattr(_ST_MODEL, "_model_id", model_id)

    def _run() -> List[List[float]]:
        vecs = _ST_MODEL.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        # Ensure list of lists
        if len(vecs.shape) == 1:
            return [vecs.tolist()]
        return [v.tolist() for v in vecs]

    return await asyncio.to_thread(_run)


async def embed_texts(texts: List[str], model: str | None = None) -> List[List[float]]:
    emodel = model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    # Try Ollama first
    try:
        vecs = await ollama_embed(texts, model=emodel)
        # Fallback if empty or zero-dim vectors
        if not vecs or any((not v or len(v) == 0) for v in vecs):
            raise OllamaError("Empty embeddings from Ollama, falling back")
        return vecs
    except (OllamaError, Exception):
        # Fallback to sentence-transformers
        return await _embed_with_st(texts, emodel)
