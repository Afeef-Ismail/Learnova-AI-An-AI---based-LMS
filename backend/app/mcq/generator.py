import os
import random
import json
import re
from typing import List, Dict, Any
from ..services.ollama import generate as ollama_generate
from ..services.qdrant import search as aq_search, fetch_texts_by_course
from ..core.database import get_session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..models.db_models import Course, MCQQuestion, MCQAttempt
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")

# In-memory session store (per course) for answered correct question IDs to avoid repetition
_ANSWERED_CORRECT: Dict[str, set] = {}
# Cache of generated questions not yet answered (per course)
_PENDING: Dict[str, List[Dict[str, Any]]] = {}

PROMPT_TEMPLATE = (
    "You are to generate ONE high-quality multiple choice question from the provided study context.\n"
    "Return ONLY strict JSON with keys: id (string), question (string), options (array of 4 strings), answer_index (0-3 int), explanation (string).\n"
    "Rules: options plausible & distinct; exactly 4; explanation concise; NO markdown, no extra text before or after JSON.\n"
    "Context:\n{context}\n\nJSON:"  # Model should output a single JSON object
)

ASYNC_CONTEXT_SEEDS = ["concept", "definition", "topic", "overview", "key", "important", "principle"]


async def _retrieve_context(course_id: str) -> List[str]:
    random.shuffle(ASYNC_CONTEXT_SEEDS)
    collected: List[str] = []
    # Issue a few semantic queries to diversify
    for s in ASYNC_CONTEXT_SEEDS[:3]:
        r = await aq_search(s, top_k=5, course_id=course_id)
        for hit in r.get("results", []):
            txt = (hit.get("payload", {}) or {}).get("text")
            if txt:
                collected.append(txt.strip())
    # Deduplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for t in collected:
        if t not in seen:
            uniq.append(t)
            seen.add(t)
    # Limit context snippets to prevent over-long prompt
    if uniq:
        return uniq[:6]
    # Fallback: pull raw texts from Qdrant for this course
    raw = fetch_texts_by_course(course_id, limit=20)
    return raw[:6]


def _extract_first_json(raw: str) -> Dict[str, Any]:
    # Fast path: try direct parse if model behaved
    raw_stripped = raw.strip()
    if raw_stripped.startswith('{') and raw_stripped.endswith('}'):  # simple case
        try:
            return json.loads(raw_stripped)
        except Exception:
            pass
    # Greedy search: find first '{' and last '}'
    start = raw.find('{')
    end = raw.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Model did not return JSON: {raw[:200]}")
    candidate = raw[start:end+1]
    # Reduce common trailing artifacts (``` etc.)
    candidate = candidate.replace('```json', '').replace('```', '').strip()
    # Fallback: tighten to smallest balanced braces using regex (non-greedy)
    try:
        # This may still over-capture if nested braces inside strings; acceptable heuristic
        match = re.search(r'\{.*\}', candidate, re.DOTALL)
        if match:
            candidate = match.group(0)
    except Exception:
        pass
    try:
        return json.loads(candidate)
    except Exception as e:
        raise RuntimeError(f"JSON parse error: {e}: {candidate[:200]}")


def _validate_mcq(obj: Dict[str, Any]):
    required = ["id", "question", "options", "answer_index", "explanation"]
    for k in required:
        if k not in obj:
            raise RuntimeError(f"Missing key {k} in MCQ JSON")
    if not isinstance(obj["options"], list) or len(obj["options"]) != 4:
        raise RuntimeError("options must be list of 4")
    if not all(isinstance(o, str) and o.strip() for o in obj["options"]):
        raise RuntimeError("each option must be a non-empty string")
    if len({o.strip() for o in obj["options"]}) < 4:
        raise RuntimeError("options must be distinct")
    if not isinstance(obj["answer_index"], int) or not (0 <= obj["answer_index"] < 4):
        raise RuntimeError("answer_index out of range")
    if not isinstance(obj["question"], str) or len(obj["question"].strip()) < 5:
        raise RuntimeError("question too short")
    if not isinstance(obj["explanation"], str) or len(obj["explanation"].strip()) < 5:
        raise RuntimeError("explanation too short")


async def _generate_question(course_id: str, model: str) -> Dict[str, Any]:
    ctx_list = await _retrieve_context(course_id)
    if not ctx_list:
        raise RuntimeError("No context available for MCQ generation")
    ctx_block = "\n---\n".join(ctx_list)
    prompt = PROMPT_TEMPLATE.format(context=ctx_block)
    raw = await ollama_generate(prompt, model=model, temperature=0.15)
    obj = _extract_first_json(raw)
    if not isinstance(obj, dict):
        raise RuntimeError("Parsed object not a dict")
    _validate_mcq(obj)
    # Stabilize id uniqueness
    obj["id"] = f"{obj['id']}::{random.randint(1000,9999)}"
    obj["course_id"] = course_id
    # Remove accidental markdown artifacts
    obj["question"] = obj["question"].strip().strip('#').strip()
    obj["options"] = [o.strip() for o in obj["options"]]
    obj["explanation"] = obj["explanation"].strip()
    return obj


async def _ensure_course(session: AsyncSession, course_key: str) -> Course:
    result = await session.execute(select(Course).where(Course.course_key == course_key))
    course = result.scalar_one_or_none()
    if course:
        return course
    course = Course(course_key=course_key, title=course_key)
    session.add(course)
    await session.flush()
    return course


async def _persist_question(session: AsyncSession, course: Course, obj: Dict[str, Any]) -> MCQQuestion | None:
    q = MCQQuestion(
        course_id=course.id,
        external_id=obj['id'],
        question=obj['question'],
        option_a=obj['options'][0],
        option_b=obj['options'][1],
        option_c=obj['options'][2],
        option_d=obj['options'][3],
        answer_index=obj['answer_index'],
        explanation=obj['explanation'],
    )
    session.add(q)
    try:
        await session.flush()
        return q
    except IntegrityError:
        await session.rollback()
        return None


async def _record_attempt(session: AsyncSession, course: Course, q: MCQQuestion, selected: int, correct: bool):
    attempt = MCQAttempt(course_id=course.id, question_id=q.id, selected_index=selected, correct=correct)
    session.add(attempt)
    await session.flush()


async def next_question(course_id: str, model: str | None = None) -> Dict[str, Any]:
    mdl = model or DEFAULT_MODEL
    answered = _ANSWERED_CORRECT.setdefault(course_id, set())
    pending = [q for q in _PENDING.get(course_id, []) if q.get("id") not in answered]
    _PENDING[course_id] = pending
    if pending:
        return pending[0]
    # Retry generation a few times for uniqueness
    for _ in range(4):
        q_obj = await _generate_question(course_id, mdl)
        if q_obj["id"] in answered:
            continue
        async for session in get_session():
            course = await _ensure_course(session, course_id)
            persisted = await _persist_question(session, course, q_obj)
            await session.commit()
        _PENDING.setdefault(course_id, []).append(q_obj)
        return q_obj
    raise RuntimeError("Failed to generate a new unique question after retries")


async def submit_answer(course_id: str, question_id: str, selected_index: int) -> Dict[str, Any]:
    answered = _ANSWERED_CORRECT.setdefault(course_id, set())
    pending = _PENDING.get(course_id, [])
    target = next((q for q in pending if q.get("id") == question_id), None)
    if not target:
        return {"status": "not_found"}
    correct = target.get("answer_index") == selected_index
    if correct:
        answered.add(question_id)
        _PENDING[course_id] = [q for q in pending if q.get("id") != question_id]
    async for session in get_session():
        course_res = await session.execute(select(Course).where(Course.course_key == course_id))
        course = course_res.scalar_one_or_none()
        if course:
            q_res = await session.execute(select(MCQQuestion).where(MCQQuestion.course_id == course.id, MCQQuestion.external_id == question_id))
            db_q = q_res.scalar_one_or_none()
            if db_q:
                await _record_attempt(session, course, db_q, selected_index, correct)
                await session.commit()
    return {
        "status": "ok",
        "correct": correct,
        "answer_index": target.get("answer_index"),
        "explanation": target.get("explanation"),
        "question": target.get("question"),
        "options": target.get("options"),
    }
