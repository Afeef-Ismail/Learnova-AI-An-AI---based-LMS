from __future__ import annotations
from typing import Dict, Any
from sqlalchemy import select, func, desc
from ..core.database import get_session
from ..models.db_models import Course, MCQAttempt, MCQQuestion


async def _get_course(course_key: str):
    async for session in get_session():
        res = await session.execute(select(Course).where(Course.course_key == course_key))
        return res.scalar_one_or_none()


async def get_stats(course_key: str, recent_limit: int = 20) -> Dict[str, Any]:
    course = await _get_course(course_key)
    if not course:
        return {
            "course_id": course_key,
            "total_attempts": 0,
            "correct": 0,
            "accuracy": 0.0,
            "streak": 0,
            "recent": [],
        }

    async for session in get_session():
        total_q = await session.execute(
            select(func.count(MCQAttempt.id)).where(MCQAttempt.course_id == course.id)
        )
        total = int(total_q.scalar() or 0)
        correct_q = await session.execute(
            select(func.count(MCQAttempt.id)).where(MCQAttempt.course_id == course.id, MCQAttempt.correct == True)  # noqa: E712
        )
        correct = int(correct_q.scalar() or 0)
        accuracy = (correct / total) * 100.0 if total else 0.0

        streak = 0
        streak_res = await session.execute(
            select(MCQAttempt.correct)
            .where(MCQAttempt.course_id == course.id)
            .order_by(desc(MCQAttempt.created_at))
            .limit(100)
        )
        for (is_correct,) in streak_res.all():
            if is_correct:
                streak += 1
            else:
                break

        recent_res = await session.execute(
            select(
                MCQAttempt.created_at,
                MCQAttempt.correct,
                MCQAttempt.selected_index,
                MCQAttempt.question_id,
                MCQQuestion.question,
                MCQQuestion.answer_index,
            )
            .join(MCQQuestion, MCQQuestion.id == MCQAttempt.question_id)
            .where(MCQAttempt.course_id == course.id)
            .order_by(desc(MCQAttempt.created_at))
            .limit(recent_limit)
        )
        recent = [
            {
                "created_at": str(row[0]),
                "correct": bool(row[1]),
                "selected_index": int(row[2]),
                "question_id": int(row[3]),
                "question": row[4],
                "answer_index": int(row[5]),
            }
            for row in recent_res.all()
        ]

        return {
            "course_id": course_key,
            "total_attempts": total,
            "correct": correct,
            "accuracy": round(accuracy, 2),
            "streak": streak,
            "recent": recent,
        }
