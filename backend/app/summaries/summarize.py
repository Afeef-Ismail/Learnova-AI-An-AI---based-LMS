import os
import asyncio
import logging
from typing import List, Dict, Any
from ..services.ollama import generate as ollama_generate
from ..services.qdrant import fetch_texts_by_course, upsert_texts
from ..core.database import get_session
from ..models.db_models import Course, Summary
from sqlalchemy import select

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", os.getenv("LLM_MODEL", "llama3.2:3b"))

# Tunable summarization parameters
SUMMARY_MAX_TOTAL_CHARS = 16000        # Hard cap of total characters fed into map stage
SUMMARY_WINDOW = 2200                  # Per chunk window size for map summaries
SUMMARY_OVERLAP = 250                  # Overlap between consecutive windows
SUMMARY_PARTIAL_LIMIT = 24             # Safety cap on number of map calls


def _split_for_summary(texts: List[str], max_total_chars: int) -> List[str]:
    """Join texts, truncate to max_total_chars, then sliding-window split with overlap.
    Falls back to a single chunk if short. Caps total number of chunks."""
    if not texts:
        return []
    combined = "\n\n".join(t for t in texts if t and t.strip())
    if not combined:
        return []
    truncated = combined[:max_total_chars]
    L = len(truncated)
    if L <= SUMMARY_WINDOW:
        return [truncated]
    out: List[str] = []
    start = 0
    while start < L and len(out) < SUMMARY_PARTIAL_LIMIT:
        end = min(start + SUMMARY_WINDOW, L)
        out.append(truncated[start:end])
        if end >= L:
            break
        start = max(end - SUMMARY_OVERLAP, 0)
        if start >= L:
            break
    return out


async def _map_summaries(chunks: List[str], model: str) -> List[str]:
    prompt_tmpl = (
        "You will summarize a learning material chunk.\n"
        "Return concise bullet points: key facts, concepts, definitions, formulas.\n"
        "Chunk:\n\"\"\"\n{chunk}\n\"\"\"\nBullet Summary:"  # Model continues
    )
    tasks = []
    for ch in chunks:
        prompt = prompt_tmpl.format(chunk=ch)
        tasks.append(asyncio.create_task(
            ollama_generate(prompt, model=model, temperature=0.1)
        ))
    return await asyncio.gather(*tasks)


async def _reduce_summary(partials: List[str], model: str) -> str:
    combined = "\n\n".join(partials)
    prompt = (
        "You are an expert course summarizer. Combine the bullet lists into a single structured summary.\n"
        "Sections: Overview; Key Concepts; Important Details; Definitions; Potential Exam Questions.\n"
        "Avoid redundancy. Keep total under ~400 words.\n\nPartial Bullets:\n" + combined + "\n\nFinal Structured Summary:"  # Model continues
    )
    return await ollama_generate(prompt, model=model, temperature=0.2)


async def summarize_course_async(course_id: str, model: str | None = None, max_chunks: int | None = None) -> Dict[str, Any]:
    """Produce a structured summary for a course's ingested chunks.
    max_chunks retained for compatibility (acts as upper bound on fetched texts)."""
    try:
        mdl = model or DEFAULT_SUMMARY_MODEL
        fetch_limit = max_chunks if max_chunks else 800
        raw_texts = fetch_texts_by_course(course_id, limit=fetch_limit)
        if not raw_texts:
            return {"ok": False, "status": "no-text", "course_id": course_id}

        chunks = _split_for_summary(raw_texts, SUMMARY_MAX_TOTAL_CHARS)
        if not chunks:
            return {"ok": False, "status": "no-chunks", "course_id": course_id}

        logger.info("Summarize start course=%s texts=%d windows=%d model=%s", course_id, len(raw_texts), len(chunks), mdl)
        partials = await _map_summaries(chunks, mdl)
        final_summary = await _reduce_summary(partials, mdl)

        # Store summary back into vector store (best-effort)
        try:
            await upsert_texts(course_id, [final_summary], metadata={"type": "summary"})
        except Exception as ve:
            logger.warning("Failed to upsert summary vector: %s", ve)

        # Persist summary to DB summaries table
        try:
            async for session in get_session():
                # ensure course
                res = await session.execute(select(Course).where(Course.course_key == course_id))
                course = res.scalar_one_or_none()
                if course is None:
                    from ..models.db_models import Course as C
                    course = C(course_key=course_id, title=course_id)
                    session.add(course)
                    await session.flush()
                s = Summary(course_id=course.id, content=final_summary, type="course")
                session.add(s)
                await session.commit()
        except Exception as db_e:
            logger.warning("Failed to persist summary to DB: %s", db_e)

        return {
            "ok": True,
            "status": "ok",
            "course_id": course_id,
            "model": mdl,
            "chunks_summarized": len(chunks),
            "partials": len(partials),
            "summary": final_summary,
        }
    except Exception as e:
        logger.exception("Summarization failed course=%s", course_id)
        return {"ok": False, "status": "error", "course_id": course_id, "error": str(e)}


async def ingest_youtube_url(url: str, course_id: str) -> Dict[str, Any]:
    """Download audio + transcript via yt-dlp + faster-whisper, then ingest chunks.
    If media download fails, fall back to fetching subtitles via youtube-transcript-api.
    Returns ingestion stats.
    """
    import tempfile
    import subprocess
    from faster_whisper import WhisperModel
    with tempfile.TemporaryDirectory() as tmp:
        audio_base = os.path.join(tmp, "audio")
        # Support override via env
        preferred_format = os.getenv("YTDLP_FORMAT", "ba[ext=m4a]/bestaudio[ext=m4a]/140/bestaudio/best")
        # Try a few common audio itags if generic selectors fail
        format_candidates = [
            preferred_format,
            "140/251/250/249",  # m4a or webm opus
            "bestaudio[acodec!=none]",
            "bestaudio",
            "worstaudio",
        ]
        success_path = None
        last_err = None
        cookies_path = os.getenv("YTDLP_COOKIES")
        for fmt in format_candidates:
            # Try each format pattern; yt-dlp chooses extension
            cmd = [
                "yt-dlp", url,
                "-f", fmt,
                "--no-playlist",
                "--ignore-errors",
                "--no-cache-dir",
                "--extract-audio",
                "--audio-format", "mp3",
                "--retries", os.getenv("YTDLP_RETRIES", "3"),
                "--fragment-retries", os.getenv("YTDLP_FRAGMENT_RETRIES", "3"),
                "-N", os.getenv("YTDLP_CONCURRENT_FRAGMENTS", "1"),  # concurrent fragments
                "-o", audio_base + ".%(ext)s",
            ]
            if cookies_path and os.path.exists(cookies_path):
                cmd.extend(["--cookies", cookies_path])
            proc = subprocess.run(cmd, capture_output=True, text=True)
            # Find produced file (any audio extension we requested mp3 ideally)
            produced_mp3 = audio_base + ".mp3"
            if proc.returncode == 0 and os.path.exists(produced_mp3):
                success_path = produced_mp3
                break
            last_err = f"Format '{fmt}' failed: rc={proc.returncode} stderr={proc.stderr[:300]}"
        if not success_path:
            # Fall back: fetch subtitles/transcript via youtube-transcript-api
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                import re
                # basic video id extraction
                vid = None
                m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})", url)
                if m:
                    vid = m.group(1)
                if not vid:
                    raise RuntimeError("cannot extract video id")
                transcript = YouTubeTranscriptApi.get_transcript(vid, languages=["en", "en-US", "en-GB"])  # type: ignore
                lines = [seg.get("text", "").strip() for seg in transcript if seg.get("text")]
                transcript_text = "\n".join([l for l in lines if l])
                if not transcript_text.strip():
                    raise RuntimeError("empty transcript from API")
                transcript_chunks = _split_for_summary([transcript_text], max_total_chars=150000)
                if not transcript_chunks:
                    raise RuntimeError("No transcript chunks from API")
                await upsert_texts(course_id, transcript_chunks, metadata={"source": url, "type": "youtube_captions"})
                return {"course_id": course_id, "url": url, "transcript_chars": len(transcript_text), "chunks": len(transcript_chunks), "source": "captions"}
            except Exception as t_err:
                raise RuntimeError(f"yt-dlp failed all formats. Last error: {last_err}; captions fallback error: {t_err}")
        model_size = os.getenv("WHISPER_MODEL", "small")
        whisper = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = whisper.transcribe(success_path, beam_size=1)
        lines: List[str] = []
        for seg in segments:
            if seg.text:
                lines.append(seg.text.strip())
        transcript_text = "\n".join(l for l in lines if l)
        if not transcript_text.strip():
            raise RuntimeError("Empty transcript")
        transcript_chunks = _split_for_summary([transcript_text], max_total_chars=150000)
        if not transcript_chunks:
            raise RuntimeError("No transcript chunks")
        await upsert_texts(course_id, transcript_chunks, metadata={"source": url, "type": "youtube"})
    return {"course_id": course_id, "url": url, "transcript_chars": len(transcript_text), "chunks": len(transcript_chunks)}
