import os
import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from .embeddings import embed_texts

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "learnova_chunks")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBED_DIM_FALLBACK = int(os.getenv("EMBEDDING_DIM", "768"))

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _client


async def _ensure_collection_for_model(collection: str, model: str) -> int:
    client = get_client()
    dim = EMBED_DIM_FALLBACK
    try:
        probe_vecs = await embed_texts(["dimension probe"], model=model)
        if probe_vecs and probe_vecs[0]:
            dim = len(probe_vecs[0])
    except Exception:
        pass

    try:
        client.get_collection(collection)
        return dim
    except Exception:
        pass

    client.recreate_collection(
        collection_name=collection,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )
    return dim


async def upsert_texts(course_id: str, texts: List[str], metadata: Dict[str, Any] | None = None,
                       model: str | None = None) -> Dict[str, Any]:
    collection = QDRANT_COLLECTION
    emodel = model or EMBED_MODEL
    await _ensure_collection_for_model(collection, emodel)

    vecs = await embed_texts(texts, model=emodel)
    points: List[qmodels.PointStruct] = []
    for text, vector in zip(texts, vecs):
        pid = str(uuid.uuid4())
        payload = {"course_id": course_id, "text": text}
        if metadata:
            payload.update(metadata)
        points.append(qmodels.PointStruct(id=pid, vector=vector, payload=payload))

    client = get_client()
    client.upsert(collection_name=collection, points=points)
    return {"upserted": len(points), "collection": collection}


def fetch_course_summary(course_id: str) -> Dict[str, Any] | None:
    """Return the first summary payload (if any) for the course."""
    client = get_client()
    flt = qmodels.Filter(must=[
        qmodels.FieldCondition(key="course_id", match=qmodels.MatchValue(value=course_id)),
        qmodels.FieldCondition(key="type", match=qmodels.MatchValue(value="summary")),
    ])
    scroll_res, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=flt,
        with_payload=True,
        limit=1,
    )
    if scroll_res:
        pt = scroll_res[0]
        return pt.payload
    return None


async def search(query: str, top_k: int = 5, model: str | None = None, course_id: str | None = None) -> Dict[str, Any]:
    collection = QDRANT_COLLECTION
    emodel = model or EMBED_MODEL
    await _ensure_collection_for_model(collection, emodel)

    qvec = (await embed_texts([query], model=emodel))[0]
    client = get_client()

    qfilter = None
    if course_id:
        qfilter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="course_id", match=qmodels.MatchValue(value=course_id)
                )
            ]
        )

    results = client.search(
        collection_name=collection,
        query_vector=qvec,
        query_filter=qfilter,
        limit=top_k,
        with_payload=True,
        score_threshold=None,
    )
    hits = [
        {
            "id": str(hit.id),
            "score": hit.score,
            "payload": hit.payload,
        }
        for hit in results
        if not (hit.payload or {}).get("type") == "summary"  # exclude summary from normal retrieval
    ]
    return {"count": len(hits), "results": hits}


def fetch_texts_by_course(course_id: str, limit: int = 500) -> List[str]:
    """Return raw text payloads for a course (no embeddings). Uses scroll API."""
    client = get_client()
    collected: List[str] = []
    next_offset = None
    collection = QDRANT_COLLECTION
    flt = qmodels.Filter(must=[qmodels.FieldCondition(key="course_id", match=qmodels.MatchValue(value=course_id))])
    while len(collected) < limit:
        scroll_res, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=flt,
            with_payload=True,
            limit=min(64, limit - len(collected)),
            offset=next_offset,
        )
        if not scroll_res:
            break
        for pt in scroll_res:
            txt = (pt.payload or {}).get("text")
            if txt:
                collected.append(txt)
        if next_offset is None:
            break
    return collected[:limit]


def delete_by_course(course_id: str) -> dict:
    """Delete all points for a given course_id. Returns Qdrant operation result."""
    client = get_client()
    flt = qmodels.Filter(must=[qmodels.FieldCondition(key="course_id", match=qmodels.MatchValue(value=course_id))])
    res = client.delete(collection_name=QDRANT_COLLECTION, points_selector=flt)  # type: ignore[arg-type]
    return {"status": "ok", "result": str(res)}


def delete_by_course_and_source(course_id: str, source: str) -> dict:
    """Delete all points for a given course_id with payload.source == source."""
    client = get_client()
    flt = qmodels.Filter(must=[
        qmodels.FieldCondition(key="course_id", match=qmodels.MatchValue(value=course_id)),
        qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=source)),
    ])
    res = client.delete(collection_name=QDRANT_COLLECTION, points_selector=flt)  # type: ignore[arg-type]
    return {"status": "ok", "result": str(res)}
