import os
from typing import List, Dict, Any, Tuple

_MODEL_NAME = os.getenv("RERANK_MODEL", "")
_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
_cross_encoder = None


def _load_model():
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder
    if not _MODEL_NAME or not _ENABLED:
        return None
    try:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder(_MODEL_NAME)
    except Exception:
        _cross_encoder = None
    return _cross_encoder


def is_enabled() -> bool:
    return bool(_MODEL_NAME) and _ENABLED and _load_model() is not None


def rerank(query: str, hits: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """Return top_k hits reranked by a cross-encoder if available; otherwise passthrough."""
    model = _load_model()
    if model is None or not hits:
        return hits[:top_k]
    pairs: List[Tuple[str, str]] = []
    for h in hits:
        txt = (h.get("payload") or {}).get("text") or ""
        pairs.append((query, txt))
    try:
        scores = model.predict(pairs)
        # attach and sort
        enriched = []
        for h, s in zip(hits, scores):
            e = dict(h)
            e["rerank_score"] = float(s)
            enriched.append(e)
        enriched.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        return enriched[:top_k]
    except Exception:
        return hits[:top_k]
