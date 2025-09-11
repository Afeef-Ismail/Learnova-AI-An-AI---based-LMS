import os
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy import select, func
import difflib
import re
from ..core.database import get_session
from ..models.db_models import Course, Flashcard
from ..services.ollama import generate as ollama_generate
from ..services.qdrant import fetch_texts_by_course

DEFAULT_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")

GEN_PROMPT = (
    "You are to generate flashcards for spaced repetition. Return ONLY strict JSON array where each item has keys: "
    "question (string), answer (string). 6 to 12 concise cards. No markdown, no commentary, just JSON.\n\n"
    "Context:\n{context}\n\nJSON:"
)


async def _ensure_course(session, course_key: str) -> Course:
    res = await session.execute(select(Course).where(Course.course_key == course_key))
    course = res.scalar_one_or_none()
    if course:
        return course
    course = Course(course_key=course_key, title=course_key)
    session.add(course)
    await session.flush()
    return course


def _leitner_next_due(box: int) -> datetime:
    # Simple schedule: box 1 -> 1 day, 2 -> 2 days, 3 -> 4 days, 4 -> 7 days, 5 -> 14 days
    days = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}.get(box, 1)
    return datetime.utcnow() + timedelta(days=days)


async def generate_flashcards(course_id: str, model: str | None = None, max_context: int = 20) -> Dict[str, Any]:
    mdl = model or DEFAULT_MODEL
    texts = fetch_texts_by_course(course_id, limit=max_context)
    if not texts:
        return {"ok": False, "status": "no-context"}
    random.shuffle(texts)
    ctx = "\n---\n".join(texts[:max_context])
    prompt = GEN_PROMPT.format(context=ctx)
    raw = await ollama_generate(prompt, model=mdl, temperature=0.15)
    # Expect a JSON array
    import json
    try:
        # Greedy extraction: find first '[' and last ']'
        s = raw.find('[')
        e = raw.rfind(']')
        if s != -1 and e != -1 and e > s:
            raw = raw[s:e+1]
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("not a list")
    except Exception as e:
        return {"ok": False, "status": "parse-error", "error": str(e), "raw": raw[:300]}

    def _normalize(s: str) -> str:
        s2 = s.lower()
        s2 = re.sub(r"[^a-z0-9\s]", " ", s2)
        s2 = re.sub(r"\s+", " ", s2).strip()
        return s2

    def _similar(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()

    created = 0
    skipped = 0
    async for session in get_session():
        course = await _ensure_course(session, course_id)
        # Load existing questions for dedupe
        existing_qs_res = await session.execute(select(Flashcard.question).where(Flashcard.course_id == course.id))
        existing_qs = [row[0] for row in existing_qs_res.all()]
        existing_norms = {_normalize(q) for q in existing_qs}

        batch_norms: set[str] = set()
        for item in data:
            q = (item or {}).get("question", "").strip()
            a = (item or {}).get("answer", "").strip()
            if not q or not a:
                continue
            nq = _normalize(q)
            # Exact/near duplicate checks
            if nq in existing_norms or any(_similar(q, eq) > 0.9 for eq in existing_qs) or any(_similar(q, bq) > 0.95 for bq in batch_norms):
                skipped += 1
                continue
            fc = Flashcard(course_id=course.id, question=q, answer=a, box=1, next_due_at=datetime.utcnow())
            session.add(fc)
            created += 1
            batch_norms.add(q)  # store original; similarity uses normalize inside
        await session.commit()
    return {"ok": True, "created": created, "skipped": skipped}


async def next_flashcard(course_id: str, reveal: bool = False, exclude_id: int | None = None) -> Dict[str, Any]:
    async for session in get_session():
        res = await session.execute(select(Course).where(Course.course_key == course_id))
        course = res.scalar_one_or_none()
        if not course:
            return {"status": "no-course"}
        # find due card: next_due_at <= now, lowest box first, oldest first
        q = select(Flashcard).where(Flashcard.course_id == course.id, Flashcard.next_due_at <= datetime.utcnow())
        if exclude_id is not None:
            q = q.where(Flashcard.id != exclude_id)
        res2 = await session.execute(q.order_by(Flashcard.box.asc(), Flashcard.next_due_at.asc()).limit(1))
        fc = res2.scalar_one_or_none()
        if not fc:
            # fallback: any card (oldest)
            q2 = select(Flashcard).where(Flashcard.course_id == course.id)
            if exclude_id is not None:
                q2 = q2.where(Flashcard.id != exclude_id)
            res3 = await session.execute(q2.order_by(Flashcard.next_due_at.asc()).limit(1))
            fc = res3.scalar_one_or_none()
            if not fc:
                return {"status": "empty"}
        result = {
            "status": "ok",
            "id": fc.id,
            "question": fc.question,
            "box": fc.box,
            "due_at": fc.next_due_at.isoformat(),
        }
        if reveal:
            result["answer"] = fc.answer
        return result


async def grade_flashcard(course_id: str, flashcard_id: int, correct: bool) -> Dict[str, Any]:
    async for session in get_session():
        res = await session.execute(select(Course).where(Course.course_key == course_id))
        course = res.scalar_one_or_none()
        if not course:
            return {"status": "no-course"}
        r2 = await session.execute(select(Flashcard).where(Flashcard.id == flashcard_id, Flashcard.course_id == course.id))
        fc = r2.scalar_one_or_none()
        if not fc:
            return {"status": "not-found"}
        if correct:
            fc.box = min(fc.box + 1, 5)
        else:
            fc.box = 1
        fc.next_due_at = _leitner_next_due(fc.box)
        await session.commit()
        return {"status": "ok", "box": fc.box, "next_due_at": fc.next_due_at.isoformat()}


async def flashcard_stats(course_id: str) -> Dict[str, Any]:
    async for session in get_session():
        res = await session.execute(select(Course).where(Course.course_key == course_id))
        course = res.scalar_one_or_none()
        if not course:
            return {"status": "no-course"}
        # counts per box and due count
        counts = {i: 0 for i in range(1, 6)}
        due = 0
        all_res = await session.execute(select(Flashcard).where(Flashcard.course_id == course.id))
        for fc in all_res.scalars().all():
            counts[fc.box] = counts.get(fc.box, 0) + 1
            if fc.next_due_at <= datetime.utcnow():
                due += 1
        return {"status": "ok", "counts": counts, "due": due}


async def get_flashcard(course_id: str, flashcard_id: int) -> Dict[str, Any]:
    async for session in get_session():
        res = await session.execute(select(Course).where(Course.course_key == course_id))
        course = res.scalar_one_or_none()
        if not course:
            return {"status": "no-course"}
        r2 = await session.execute(select(Flashcard).where(Flashcard.id == flashcard_id, Flashcard.course_id == course.id))
        fc = r2.scalar_one_or_none()
        if not fc:
            return {"status": "not-found"}
        return {
            "status": "ok",
            "id": fc.id,
            "question": fc.question,
            "answer": fc.answer,
            "box": fc.box,
            "due_at": fc.next_due_at.isoformat(),
        }


async def list_flashcards(course_id: str, limit: int = 200, offset: int = 0, box: int | None = None) -> Dict[str, Any]:
    async for session in get_session():
        res = await session.execute(select(Course).where(Course.course_key == course_id))
        course = res.scalar_one_or_none()
        if not course:
            return {"status": "no-course", "items": [], "total": 0}
        base_where = (Flashcard.course_id == course.id)
        if box is not None:
            base_where = base_where & (Flashcard.box == box)
        total_res = await session.execute(select(func.count()).select_from(Flashcard).where(base_where))
        total = int(total_res.scalar() or 0)
        q = select(Flashcard).where(base_where).order_by(Flashcard.id.desc()).limit(limit).offset(offset)
        rows = (await session.execute(q)).scalars().all()
        items = [
            {
                "id": fc.id,
                "question": fc.question,
                "answer": fc.answer,
                "box": fc.box,
                "due_at": fc.next_due_at.isoformat(),
            }
            for fc in rows
        ]
        return {"status": "ok", "items": items, "total": total}
