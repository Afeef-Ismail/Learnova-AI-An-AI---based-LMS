import os
import asyncio
from typing import Any, Dict
from .celery_app import celery_app
from app.summaries.summarize import ingest_youtube_url, summarize_course_async


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(name="workers.ingest_youtube", bind=True)
def ingest_youtube_task(self, url: str, course_id: str, model: str | None = None, summarize: bool = False) -> Dict[str, Any]:
    ing = _run(ingest_youtube_url(url=url, course_id=course_id))
    out: Dict[str, Any] = {"task": "ingest_youtube", "course_id": course_id, "ingestion": ing}
    if summarize:
        use_model = model or os.getenv("LLM_MODEL", "llama3:8b")
        summ = _run(summarize_course_async(course_id=course_id, model=use_model))
        out["summary"] = summ
    return out


@celery_app.task(name="workers.summarize_course", bind=True)
def summarize_course_task(self, course_id: str, model: str | None = None) -> Dict[str, Any]:
    use_model = model or os.getenv("LLM_MODEL", "llama3:8b")
    summ = _run(summarize_course_async(course_id=course_id, model=use_model))
    return {"task": "summarize_course", "course_id": course_id, "summary": summ}
