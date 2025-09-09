from typing import Dict, Any, List
import os
from ..services.qdrant import search as qdrant_search, fetch_course_summary
from ..services.ollama import generate as ollama_generate
from ..services.reranker import rerank as rr_rerank, is_enabled as rr_enabled

DEFAULT_MODEL = os.getenv("LLM_MODEL", "llama3:8b")


def _build_prompt(question: str, contexts: List[Dict[str, Any]], summary: str | None = None) -> str:
    parts = [
        "You are an educational assistant. Answer the question using ONLY the provided context.",
        "Cite sources as [1], [2], etc., matching the context items; if uncertain, say you don't know.",
    ]
    if summary:
        parts.append("\nCourse Summary:\n" + summary)
    parts.append("\nContext:")
    for i, ctx in enumerate(contexts, start=1):
        text = ctx.get("payload", {}).get("text", "")
        parts.append(f"[{i}] {text}")
    parts.append("\nQuestion: " + question)
    parts.append("Answer:")
    return "\n".join(parts)


async def rag_answer(question: str, course_id: str | None = None, model: str | None = None, include_summary: bool = True, use_reranker: bool | None = None) -> Dict[str, Any]:
    """RAG with optional course summary prepended (not part of retrieval scoring)."""
    summary_block: str | None = None
    if include_summary and course_id:
        summary_payload = fetch_course_summary(course_id)
        if summary_payload and summary_payload.get("text"):
            summary_block = summary_payload["text"]

    results = await qdrant_search(question, top_k=8, model=None, course_id=course_id)
    contexts = results.get("results", [])
    if (use_reranker if use_reranker is not None else rr_enabled()) and contexts:
        contexts = rr_rerank(question, contexts, top_k=5)
    prompt = _build_prompt(question, contexts, summary_block)
    mdl = model or DEFAULT_MODEL
    response = await ollama_generate(prompt, model=mdl, temperature=0.2)

    sources = []
    for i, hit in enumerate(contexts, start=1):
        payload = hit.get("payload", {})
        sources.append({"idx": i, "score": hit.get("score"), "text": payload.get("text", "")})

    return {"answer": response, "model": mdl, "sources": sources, "used_summary": bool(summary_block), "reranked": (use_reranker if use_reranker is not None else rr_enabled())}
