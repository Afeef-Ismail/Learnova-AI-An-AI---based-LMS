import json
import requests
import streamlit as st

st.set_page_config(page_title="Learnova AI", layout="wide")
st.title("Learnova AI")

with st.sidebar:
    st.header("Course")
    base_url = st.text_input("Backend URL", "http://localhost:8000")
    course_id = st.text_input("Course ID", "c1")
    with st.expander("Advanced", expanded=False):
        llm_model = st.text_input("LLM model (chat/MCQ)", "llama3:8b")
        use_reranker = st.checkbox("Use reranker (if available)", value=True)


def api_get(path: str):
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload=None, files=None):
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if files:
        r = requests.post(url, files=files, data=payload or {}, timeout=300)
    else:
        r = requests.post(url, json=payload or {}, timeout=1800)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.reason}\n{r.text}")
    return r.json()


st.subheader("1) Add Content")
uploaded = st.file_uploader("Upload a file (PDF/DOCX/PPTX/TXT)", type=["pdf", "docx", "pptx", "txt", "md"])
if st.button("Upload"):
    if not uploaded:
        st.warning("Select a file first.")
    else:
        try:
            files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}
            data = {"course_id": course_id}
            api_post("upload", payload=data, files=files)
            st.success("Uploaded and ingested.")
        except Exception as e:
            st.error(str(e))


# Materials listing
st.subheader("My Materials")
if st.button("Refresh Materials"):
    try:
        data = api_get(f"materials?course_id={course_id}")
        items = data.get("items", [])
        if not items:
            st.info("No files found.")
        else:
            for it in items:
                st.write(f"- {it['name']} ({it['size_bytes']} bytes)")
    except Exception as e:
        st.error(str(e))


# YouTube ingestion
st.subheader("1b) Add from YouTube")
yt_url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
yt_auto_summary = st.checkbox("Summarize after ingest", value=True)
if st.button("Ingest YouTube"):
    if not yt_url.strip():
        st.warning("Enter a YouTube URL")
    else:
        try:
            payload = {"url": yt_url.strip(), "course_id": course_id, "summarize": yt_auto_summary}
            with st.spinner("Processing video... this can take a few minutes"):
                resp = api_post("ingest/youtube", payload)
            st.success("YouTube content ingested.")
            if yt_auto_summary and resp.get("summary"):
                st.markdown("### Auto Summary")
                summary_obj = resp["summary"]
                if isinstance(summary_obj, dict) and summary_obj.get("summary"):
                    st.text_area("Summary", summary_obj["summary"], height=300)
                else:
                    st.write("Summary unavailable.")
        except Exception as e:
            st.error(str(e))


# YouTube materials list with preview
st.subheader("My YouTube Videos")
if st.button("Refresh YouTube List"):
    try:
        data = api_get(f"materials/youtube?course_id={course_id}")
        items = data.get("items", [])
        if not items:
            st.info("No YouTube videos found for this course.")
        else:
            cols = st.columns(3)
            for idx, it in enumerate(items):
                with cols[idx % 3]:
                    vid = it.get("video_id")
                    thumb = it.get("thumbnail_url")
                    url = it.get("url")
                    if thumb:
                        st.image(thumb, use_column_width=True)
                    st.markdown(f"[Open on YouTube]({url})")
    except Exception as e:
        st.error(str(e))


# Course summarization
st.subheader("2) Summarize Course")
if st.button("Summarize Course"):
    try:
        payload = {"course_id": course_id}
        with st.spinner("Summarizing course..."):
            resp = api_post("summaries/course", payload)
        if resp.get("summary"):
            st.text_area("Course Summary", resp["summary"], height=350)
    except Exception as e:
        st.error(str(e))


# RAG chat
st.subheader("3) Ask the Course")
q = st.text_area("Your question", "What are the key topics in this course?")
include_summary = st.checkbox("Include course summary context", value=True)
if st.button("Ask"):
    try:
        payload = {"query": q, "course_id": course_id, "model": llm_model, "use_reranker": use_reranker, "include_summary": include_summary}
        resp = api_post("rag/chat", payload)
        st.markdown("### Answer")
        st.write(resp.get("answer", ""))
        if resp.get("sources"):
            st.markdown("#### Sources")
            for s in resp["sources"]:
                st.caption(f"[{s.get('idx')}] score={round(s.get('score', 0), 3)}")
    except Exception as e:
        st.error(str(e))


# MCQ Practice
st.subheader("4) MCQ Practice")
if "current_mcq" not in st.session_state:
    st.session_state.current_mcq = None
if "mcq_feedback" not in st.session_state:
    st.session_state.mcq_feedback = None

col_q, col_a = st.columns([2, 1])
with col_q:
    if st.button("Get Next Question"):
        try:
            st.session_state.mcq_feedback = None
            st.session_state.current_mcq = api_post("mcq/next", {"course_id": course_id, "model": llm_model})
        except Exception as e:
            st.error(str(e))

    mcq = st.session_state.current_mcq
    if mcq:
        st.markdown(f"**Question:** {mcq.get('question')}")
        options = mcq.get('options', [])
        st.session_state.selected_option = st.radio("Options", options, index=0, key="mcq_opts")

with col_a:
    if st.button("Submit Answer") and st.session_state.get("current_mcq"):
        mcq = st.session_state.current_mcq
        try:
            selected_idx = mcq.get('options', []).index(st.session_state.selected_option)
            res = api_post("mcq/answer", {
                "course_id": course_id,
                "question_id": mcq.get('id'),
                "selected_index": selected_idx
            })
            st.session_state.mcq_feedback = res
            if res.get("correct"):
                st.session_state.current_mcq = None
        except Exception as e:
            st.error(str(e))

    if st.session_state.get("mcq_feedback"):
        fb = st.session_state.mcq_feedback
        if fb.get("status") == "ok":
            correct = fb.get("correct")
            if correct:
                st.success("Correct!")
            else:
                st.error(f"Incorrect. Correct answer index: {fb.get('answer_index')}")
            st.write("Explanation:")
            st.info(fb.get("explanation"))
        else:
            st.warning(fb)


# Flashcards
st.subheader("5) Flashcards")
col_fg, col_fn = st.columns(2)
with col_fg:
    if st.button("Generate Flashcards"):
        try:
            resp = api_post("flashcards/generate", {"course_id": course_id, "model": llm_model, "max_context": 20})
            st.success(f"Created: {resp.get('created', 0)}")
        except Exception as e:
            st.error(str(e))

if "flash_current" not in st.session_state:
    st.session_state.flash_current = None
if "flash_show_answer" not in st.session_state:
    st.session_state.flash_show_answer = False

with col_fn:
    if st.button("Get Next Card"):
        try:
            st.session_state.flash_show_answer = False
            st.session_state.flash_current = api_get(f"flashcards/next?course_id={course_id}")
        except Exception as e:
            st.error(str(e))

card = st.session_state.flash_current
if card and card.get("status") == "ok":
    st.markdown(f"**Q:** {card.get('question')}")
    if not st.session_state.flash_show_answer:
        if st.button("Show Answer"):
            st.session_state.flash_show_answer = True
    else:
        try:
            detailed = api_get(f"flashcards/get?course_id={course_id}&flashcard_id={card.get('id')}")
            if detailed.get("status") == "ok":
                st.success(detailed.get("answer"))
            else:
                st.info("No answer available.")
        except Exception as e:
            st.error(str(e))
    col_c, col_i = st.columns(2)
    with col_c:
        if st.button("I was Correct ✅"):
            try:
                api_post("/flashcards/grade", {"course_id": course_id, "flashcard_id": card.get("id"), "correct": True})
                st.session_state.flash_current = None
                st.success("Noted. Next due updated.")
            except Exception as e:
                st.error(str(e))
    with col_i:
        if st.button("I was Incorrect ❌"):
            try:
                api_post("/flashcards/grade", {"course_id": course_id, "flashcard_id": card.get("id"), "correct": False})
                st.session_state.flash_current = None
                st.info("Reset to box 1. Keep practicing!")
            except Exception as e:
                st.error(str(e))
    # small stats
    try:
        stats = api_get(f"flashcards/stats?course_id={course_id}")
        counts = stats.get("counts", {})
        due = stats.get("due", 0)
        st.caption(f"Due: {due} | Boxes 1-5: {counts.get(1,0)}/{counts.get(2,0)}/{counts.get(3,0)}/{counts.get(4,0)}/{counts.get(5,0)}")
    except Exception:
        pass

st.subheader("7) Background Jobs")
st.markdown("YouTube Ingest (Background)")
yt_bg_url = st.text_input("YouTube URL (bg)", key="yt_bg_url")
yt_bg_auto = st.checkbox("Auto-summarize after ingest (bg)", value=True, key="yt_bg_auto")
if st.button("Enqueue YouTube Ingest (bg)"):
    if not yt_bg_url.strip():
        st.warning("Enter a YouTube URL")
    else:
        try:
            payload = {"url": yt_bg_url.strip(), "course_id": course_id, "summarize": yt_bg_auto, "model": llm_model}
            resp = api_post("jobs/ingest/youtube", payload)
            st.session_state["yt_job_id"] = resp.get("job_id")
            st.success(f"Queued job: {st.session_state['yt_job_id']}")
        except Exception as e:
            st.error(str(e))

if st.button("Check YouTube Job Status") and st.session_state.get("yt_job_id"):
    try:
        jid = st.session_state["yt_job_id"]
        st.write(f"Job ID: {jid}")
        st.json(api_get(f"jobs/{jid}"))
    except Exception as e:
        st.error(str(e))

st.markdown("Summarize Course (Background)")
if st.button("Enqueue Summary (bg)"):
    try:
        resp = api_post("jobs/summaries/course", {"course_id": course_id, "model": llm_model})
        st.session_state["sum_job_id"] = resp.get("job_id")
        st.success(f"Queued job: {st.session_state['sum_job_id']}")
    except Exception as e:
        st.error(str(e))

if st.button("Check Summary Job Status") and st.session_state.get("sum_job_id"):
    try:
        jid = st.session_state["sum_job_id"]
        st.write(f"Job ID: {jid}")
        st.json(api_get(f"jobs/{jid}"))
    except Exception as e:
        st.error(str(e))