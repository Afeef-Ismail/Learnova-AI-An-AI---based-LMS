import os
import re
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from .ingestion.pipeline import process_file, process_file_async
from .services.ollama import list_models, pull_model, generate, embed, OllamaError, stream_generate
from .services.qdrant import upsert_texts as qdrant_upsert, search as qdrant_search, fetch_texts_by_course
from .services.embeddings import embed_texts
from .rag.rag import rag_answer
from .summaries.summarize import summarize_course_async, ingest_youtube_url
from .mcq.generator import next_question as mcq_next, submit_answer as mcq_submit
from .mcq.stats import get_stats as mcq_get_stats
from .core.database import init_db, get_session
from .workers.celery_app import celery_app
from .flashcards.service import generate_flashcards, next_flashcard, grade_flashcard, flashcard_stats, get_flashcard, list_flashcards
from sqlalchemy import select
from .models.db_models import Course, MCQQuestion, MCQAttempt, Summary, Flashcard, ChatMessage, User
import time, hmac, hashlib, base64, json as pyjson
import httpx
import threading
from collections import deque

load_dotenv()

app = FastAPI(title="Learnova AI Backend", version="0.1.0")

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", os.getenv("NEXT_PUBLIC_FRONTEND_ORIGIN", "http://localhost:3001"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compression for non-streaming responses
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Basic security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response

@app.on_event("startup")
async def _startup():
    try:
        await init_db()
    except Exception as e:
        print("[startup] DB init failed", e)

@app.get("/health")
def health():
    return {"status": "ok"}

# --- Simple JWT helpers (HS256) ---
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ISSUER = "learnova"

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _sign(data: bytes) -> str:
    sig = hmac.new(JWT_SECRET.encode(), data, hashlib.sha256).digest()
    return _b64url(sig)

def create_jwt(payload: dict, exp_sec: int = 60*60*24*7) -> str:
    now = int(time.time())
    body = {"iss": JWT_ISSUER, "iat": now, "exp": now + exp_sec, **payload}
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url(pyjson.dumps(header, separators=(',',':')).encode())
    b = _b64url(pyjson.dumps(body, separators=(',',':')).encode())
    signing_input = f"{h}.{b}".encode()
    s = _sign(signing_input)
    return f"{h}.{b}.{s}"

def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    # very lightweight: store sha256 hex; in prod use argon2/bcrypt
    return hashlib.sha256(password.encode()).hexdigest() == password_hash

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

async def google_verify_id_token(id_token: str) -> dict | None:
    # Use tokeninfo endpoint for simplicity
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            # Expect email and sub
            if not data.get("email"):
                return None
            # Optional: verify audience if configured
            expected_aud = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("NEXT_PUBLIC_GOOGLE_CLIENT_ID")
            aud = data.get("aud")
            if expected_aud and aud and aud != expected_aud:
                # Audience mismatch, reject
                return None
            return data
    except Exception:
        return None

# --- Lightweight rate limiting (per-IP, per-route) ---
_rate_lock = threading.Lock()
_rate_buckets: dict[tuple[str, str], deque[float]] = {}

def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, str(default)))
        return v if v > 0 else default
    except Exception:
        return default

def rate_limiter(limit: int, window_sec: int):
    async def _dep(request: Request):
        ip = request.client.host if request.client else "unknown"
        key = (ip, request.url.path)
        now = time.time()
        with _rate_lock:
            dq = _rate_buckets.get(key)
            if dq is None:
                dq = deque()
                _rate_buckets[key] = dq
            while dq and (now - dq[0]) > window_sec:
                dq.popleft()
            if len(dq) >= limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            dq.append(now)
    return _dep

# --- Small helpers ---
def _truncate(s: str | None, max_len: int = 2000) -> str:
    t = (s or "")
    return t if len(t) <= max_len else (t[:max_len] + "…")

# Upload endpoint stores file then kicks off (stub) ingestion
@app.post("/upload")
async def upload(file: UploadFile = File(...), course_id: str = Form(...)):
    storage_root = os.getenv("STORAGE_ROOT", "/data/uploads")
    # Store files under a per-course directory
    course_dir = os.path.join(storage_root, course_id)
    os.makedirs(course_dir, exist_ok=True)
    dest = os.path.join(course_dir, file.filename)
    with open(dest, "wb") as f:
        f.write(await file.read())
    # Use async ingestion pipeline
    result = await process_file_async(dest, course_id)
    return {"ok": True, "filename": file.filename, "course_id": course_id, "ingestion": result}

# List uploaded materials
@app.get("/materials")
async def list_materials(course_id: str | None = None):
    storage_root = os.getenv("STORAGE_ROOT", "/data/uploads")
    try:
        base_dir = storage_root
        if course_id:
            base_dir = os.path.join(storage_root, course_id)
        if not os.path.isdir(base_dir):
            return {"count": 0, "items": []}
        items: list[dict] = []
        for name in os.listdir(base_dir):
            path = os.path.join(base_dir, name)
            if os.path.isfile(path):
                st_ = os.stat(path)
                items.append({
                    "name": name,
                    "size_bytes": st_.st_size,
                    "modified_at": int(st_.st_mtime),
                })
        items.sort(key=lambda x: x["modified_at"], reverse=True)
        return {"count": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# List courses (by scanning STORAGE_ROOT directories)
@app.get("/courses")
async def list_courses():
    storage_root = os.getenv("STORAGE_ROOT", "/data/uploads")
    try:
        # 1) Collect course ids from filesystem folders
        fs_courses: set[str] = set()
        if os.path.isdir(storage_root):
            for name in os.listdir(storage_root):
                path = os.path.join(storage_root, name)
                if os.path.isdir(path):
                    fs_courses.add(name)

        # 2) Collect distinct course_ids from Qdrant payloads (best-effort)
        qdrant_courses: set[str] = set()
        try:
            from .services.qdrant import get_client, QDRANT_COLLECTION  # lazy import to avoid hard dep at startup
            from qdrant_client.http import models as qmodels  # type: ignore

            client = get_client()
            next_offset = None
            # Scroll a reasonable number of points to harvest distinct course_ids
            # If collection is large, this is still best-effort and fast.
            scanned = 0
            max_scan = 5000  # cap to avoid excessive work
            while scanned < max_scan:
                limit = min(256, max_scan - scanned)
                scroll_res, next_offset = client.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=None,
                    with_payload=True,
                    limit=limit,
                    offset=next_offset,
                )
                if not scroll_res:
                    break
                for pt in scroll_res:
                    payload = pt.payload or {}
                    cid = payload.get("course_id")
                    if isinstance(cid, str) and cid:
                        qdrant_courses.add(cid)
                scanned += len(scroll_res)
                if next_offset is None:
                    break
        except Exception:
            # Swallow Qdrant issues; still return FS courses
            pass

        # 3) Union and sort
        all_ids = sorted(fs_courses.union(qdrant_courses), key=lambda x: x.lower())
        courses = [{"id": cid} for cid in all_ids]
        return {"count": len(courses), "courses": courses}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# List YouTube materials (distinct URLs) for a course, with thumbnails for preview
@app.get("/materials/youtube")
async def list_youtube_materials(course_id: str | None = None):
    if not course_id:
        raise HTTPException(status_code=400, detail="course_id is required")
    try:
        # Lazy imports to avoid coupling
        from .services.qdrant import get_client, QDRANT_COLLECTION
        from qdrant_client.http import models as qmodels  # type: ignore
        import re

        def extract_video_id(u: str) -> str | None:
            # Supports watch?v=, youtu.be/, shorts/
            patterns = [
                r"[?&]v=([A-Za-z0-9_-]{6,})",
                r"youtu\.be/([A-Za-z0-9_-]{6,})",
                r"shorts/([A-Za-z0-9_-]{6,})",
            ]
            for p in patterns:
                m = re.search(p, u)
                if m:
                    return m.group(1)
            return None

        client = get_client()
        flt = qmodels.Filter(must=[
            qmodels.FieldCondition(key="course_id", match=qmodels.MatchValue(value=course_id)),
            qmodels.FieldCondition(key="type", match=qmodels.MatchAny(any=["youtube", "youtube_captions"]))
        ])
        urls: set[str] = set()
        next_offset = None
        while True:
            scroll_res, next_offset = client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=flt,
                with_payload=True,
                limit=128,
                offset=next_offset,
            )
            if not scroll_res:
                break
            for pt in scroll_res:
                payload = pt.payload or {}
                url = payload.get("source") or payload.get("url")
                if isinstance(url, str):
                    urls.add(url)
            if next_offset is None:
                break

        items = []
        for u in sorted(urls):
            vid = extract_video_id(u)
            thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else None
            items.append({
                "url": u,
                "video_id": vid,
                "thumbnail_url": thumb,
            })
        return {"count": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---- Ollama endpoints ----
class ChatRequest(BaseModel):
    prompt: str
    model: str | None = None
    temperature: float | None = 0.2
class ChatMessageItem(BaseModel):
    role: str
    content: str
class ChatEduRequest(BaseModel):
    messages: list[ChatMessageItem] | None = None
    prompt: str | None = None
    model: str | None = None
    temperature: float | None = 0.2

class ChatEduStreamRequest(ChatEduRequest):
    pass

class EmbedRequest(BaseModel):
    texts: list[str]
    model: str | None = None

class UpsertRequest(BaseModel):
    course_id: str
    texts: list[str]
    metadata: dict | None = None
    model: str | None = None

class SearchRequest(BaseModel):
    query: str
    top_k: int | None = 5
    model: str | None = None
    course_id: str | None = None

class RAGRequest(BaseModel):
    query: str
    course_id: str | None = None
    model: str | None = None
    include_summary: bool | None = True
    use_reranker: bool | None = None

class SummarizeRequest(BaseModel):
    course_id: str
    model: str | None = None
    max_chunks: int | None = 400

class YoutubeIngestRequest(BaseModel):
    url: str
    course_id: str
    model: str | None = None
    summarize: bool | None = True

class MCQNextRequest(BaseModel):
    course_id: str
    model: str | None = None

class MCQAnswerRequest(BaseModel):
    course_id: str
    question_id: str
    selected_index: int

class FlashGenRequest(BaseModel):
    course_id: str
    model: str | None = None
    max_context: int | None = 20

class FlashGradeRequest(BaseModel):
    course_id: str
    flashcard_id: int
    correct: bool

class JobYouTubeRequest(BaseModel):
    url: str
    course_id: str
    model: str | None = None
    summarize: bool = False

class JobSummaryRequest(BaseModel):
    course_id: str
    model: str | None = None

@app.get("/models")
async def models():
    try:
        return {"models": await list_models()}
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/models/pull")
async def models_pull(body: dict):
    name = body.get("name")
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    try:
        return await pull_model(name)
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/chat")
async def chat(body: ChatRequest):
    model = body.model or os.getenv("LLM_MODEL", "llama3:8b")
    try:
        text = await generate(body.prompt, model=model, temperature=(body.temperature or 0.2))
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"model": model, "response": text}

# ---- Auth models ----
class SignupRequest(BaseModel):
    name: str | None = None
    email: str
    password: str | None = None

class LoginRequest(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    id_token: str

@app.post("/auth/signup")
async def signup(body: SignupRequest, _rl=Depends(rate_limiter(10, 60))):
    email = (body.email or '').strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    async for session in get_session():
        exists = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = User(email=email, name=(body.name or '').strip(), provider="local", password_hash=hash_password(body.password or ""))
        session.add(user)
        await session.commit()
        token = create_jwt({"sub": str(user.id), "email": user.email, "name": user.name})
        return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}

@app.post("/auth/login")
async def login(body: LoginRequest, _rl=Depends(rate_limiter(20, 60))):
    email = (body.email or '').strip().lower()
    async for session in get_session():
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token = create_jwt({"sub": str(user.id), "email": user.email, "name": user.name})
        return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}

@app.post("/auth/google")
async def login_google(body: GoogleLoginRequest, _rl=Depends(rate_limiter(20, 60))):
    data = await google_verify_id_token(body.id_token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    email = (data.get("email") or '').lower()
    name = data.get("name") or ""
    async for session in get_session():
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            user = User(email=email, name=name, provider="google", password_hash=None)
            session.add(user)
            await session.commit()
        token = create_jwt({"sub": str(user.id), "email": user.email, "name": user.name})
        return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}

# Simple heuristic to determine if a query is educational or mathematical
def _is_educational_text(text: str) -> bool:
    s = (text or "").lower()
    subject_keywords = [
        # STEM
    'math','algebra','geometry','calculus','trigonometry','probability','statistics','equation','integral','derivative','matrix','linear algebra','number theory','proof','theorem','logic',
    'physics','chemistry','biology','geology','astronomy','computer science','programming','algorithm','data structure','machine learning','neural network','database','operating system',
        # Humanities & Social Sciences
        'history','geography','economics','psychology','sociology','philosophy','political science','civics','law',
        # History topics
        'world war','ww1','ww2','wwi','wwii','world war 1','world war 2','world war i','world war ii','second world war','first world war','civil war','cold war',
        'french revolution','american revolution','industrial revolution','revolution','enlightenment','renaissance','medieval','ancient','roman empire','ottoman empire','byzantine','napoleon','napoleonic',
        # Language & Literature
        'grammar','literature','poetry','prose','essay','rhetoric','linguistics','vocabulary','spelling','reading comprehension',
        # Education phrasing
        'explain','define','derive','prove','solve','calculate','evaluate','simplify','compare','contrast','homework','assignment','exam','test'
    ]
    math_pattern = re.compile(r"([0-9]+\s*[+\-*/^%()]\s*[0-9]+)|=|√|π|theta|sin|cos|tan|log|ln|derivative|integral|matrix|vector|limit", re.I)
    # Generic history terms used with question starters (to avoid allowing non-educational topics)
    history_terms = [
        'revolution','enlightenment','war','empire','dynasty','constitution','treaty','monarchy','republic','independence','colony','colonial','king','queen','president','pharaoh'
    ]
    question_starters = re.compile(r"\b(what is|what's|whats|who (is|was)|tell me about|when (did|was)|where (is|was)|why (is|was)|how (did|does|is))\b", re.I)
    has_subject = any(k in s for k in subject_keywords)
    has_math = bool(math_pattern.search(text or ""))
    has_history_question = bool(question_starters.search(s)) and any(t in s for t in history_terms)
    return has_subject or has_math or has_history_question

def _is_followup_reference(text: str) -> bool:
    s = (text or "").lower().strip()
    if not s:
        return False
    # Phrases that typically refer back to the previous educational topic
    followup_phrases = [
        'example', 'another example', 'give me an example', 'can you give me an example',
        'more', 'explain more', 'elaborate', 'continue', 'go on', 'tell me more',
        'clarify', 'why is that', 'how does that', 'what about', 'similar problem', 'another one',
        'practice problem', 'exercise', 'walk me through', 'step by step', 'prove it', 'derive it'
    ]
    if any(p in s for p in followup_phrases):
        # Avoid obvious topic-switches
        banned = ['cook', 'recipe', 'noodle', 'noodles', 'spaghetti', 'pasta', 'gaming', 'travel']
        if any(b in s for b in banned):
            return False
        return True
    return False

# Heuristic: detect cooking/recipe how-to queries while allowing educational framings
def _is_cooking_or_recipe(text: str | None) -> bool:
    s = (text or "").lower()
    if not s:
        return False
    # Allow if clearly educational/analytical rather than a how-to
    allow_markers = [
        'maillard', 'food science', 'chemistry of', 'nutrition', 'nutritional',
        'history of', 'origin of', 'cultural history', 'food safety', 'microbiology',
        'spaghetti code'  # avoid CS false positive
    ]
    if any(am in s for am in allow_markers):
        return False
    # Core signals for recipe/how-to requests
    cooking_verbs = [
        'cook', 'bake', 'fry', 'boil', 'saute', 'sauté', 'grill', 'roast', 'steam', 'simmer',
        'knead', 'marinate', 'preheat', 'mix', 'stir-fry', 'air fry'
    ]
    food_terms = [
        'noodle', 'noodles', 'pasta', 'spaghetti', 'ramen', 'maggi', 'udon', 'soba',
        'rice', 'biryani', 'curry', 'dal', 'lentil', 'paneer', 'tofu', 'omelette', 'omelet',
        'chapati', 'roti', 'paratha', 'bread', 'cake', 'cookie', 'cookies', 'brownies', 'pizza', 'burger', 'salad',
        'chicken', 'fish', 'egg', 'eggs', 'soup', 'sauce'
    ]
    phrases = [
        'how to make', 'how do i make', 'how to cook', 'how do i cook', 'recipe', 'ingredients', 'step by step recipe',
        'steps to make', 'best recipe', 'easy recipe'
    ]
    # If they ask a how-to phrase and mention common food terms, treat as cooking
    if any(p in s for p in phrases) and any(f in s for f in food_terms):
        return True
    # Or if they combine a cooking verb with a food term
    if any(v in s for v in cooking_verbs) and any(f in s for f in food_terms):
        return True
    return False

@app.post("/chat/edu")
async def chat_edu(body: ChatEduRequest, _rl=Depends(rate_limiter(_env_int("RL_CHAT", 30), _env_int("RL_CHAT_WINDOW", 60)))):
    # Determine latest user query for filtering
    latest_user: str | None = None
    if body.messages and len(body.messages) > 0:
        # find last user role
        for m in reversed(body.messages):
            if (m.role or '').lower() == 'user':
                latest_user = m.content
                break
    if latest_user is None and body.prompt:
        latest_user = body.prompt
    if not latest_user:
        raise HTTPException(status_code=400, detail="prompt or messages with a user turn is required")
    model = body.model or os.getenv("LLM_MODEL", "llama3:8b")
    temperature = (body.temperature or 0.2)
    # Strong system instruction (includes general knowledge but excludes practical cooking how-tos)
    today = time.strftime("%Y-%m-%d")
    instruction = (
        "System: You are Learnova, a helpful tutor for education, general knowledge, mathematics, and technology. "
        "General knowledge includes history, geography, science facts, sports records, notable people, world facts, and current affairs basics. "
        f"Answer concisely and accurately; for time-sensitive facts (e.g., current leaders or records), include a brief 'as of {today}' note and proceed. "
        "Do not provide practical cooking or recipe instructions (e.g., 'how to make noodles'); instead, offer an educational angle such as food science (Maillard reaction), nutrition basics, or cultural history. "
        "Politely refuse clearly inappropriate requests (e.g., explicit content, personal gossip, self-harm, illegal activity, or detailed medical/legal/financial advice). "
        "Style: be clear and concise; explain step-by-step for math/problems; include short definitions, formulas, and 1-2 key insights; show small code snippets when technical. "
        "Follow-ups may refer to prior context (e.g., 'another example')."
    )

    # Early guard for cooking/recipe how-to
    if _is_cooking_or_recipe(latest_user):
        refusal = (
            "I focus on education, general knowledge, mathematics, and technology. "
            "I can’t provide cooking or recipe how‑to steps. If you’d like, I can explain the science behind boiling pasta, basics of nutrition, or the cultural history of noodles."
        )
        return {"model": model, "response": refusal}

    # Build conversation prompt
    if body.messages and len(body.messages) > 0:
        # limit to last N messages to cap prompt length
        msgs = body.messages[-16:]
        lines: list[str] = [instruction, ""]
        for m in msgs:
            role = (m.role or '').lower()
            content = _truncate(m.content)
            if role == 'assistant':
                lines.append(f"Assistant: {content}")
            elif role == 'user':
                lines.append(f"User: {content}")
            else:
                # skip other roles, instruction is enough
                continue
        lines.append("Assistant:")
        full_prompt = "\n".join(lines)
    else:
        full_prompt = f"{instruction}\n\nUser: {_truncate(latest_user)}\nAssistant:"

    try:
        text = await generate(full_prompt, model=model, temperature=temperature)
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"model": model, "response": text}

@app.post("/chat/edu/stream")
async def chat_edu_stream(body: ChatEduStreamRequest, _rl=Depends(rate_limiter(_env_int("RL_CHAT", 30), _env_int("RL_CHAT_WINDOW", 60)))):
    # Determine latest user query for filtering
    latest_user: str | None = None
    if body.messages and len(body.messages) > 0:
        for m in reversed(body.messages):
            if (m.role or '').lower() == 'user':
                latest_user = m.content
                break
    if latest_user is None and body.prompt:
        latest_user = body.prompt
    if not latest_user:
        raise HTTPException(status_code=400, detail="prompt or messages with a user turn is required")

    # Build instruction and prompt (includes general knowledge; excludes cooking how-tos)
    today = time.strftime("%Y-%m-%d")
    instruction = (
        "System: You are Learnova, a helpful tutor for education, general knowledge, mathematics, and technology. "
        "General knowledge includes history, geography, science facts, sports records, notable people, world facts, and current affairs basics. "
        f"Answer concisely and accurately; for time-sensitive facts (e.g., current leaders or records), include a brief 'as of {today}' note and proceed. "
        "Do not provide practical cooking or recipe instructions (e.g., 'how to make noodles'); instead, offer an educational angle such as food science (Maillard reaction), nutrition basics, or cultural history. "
        "Politely refuse clearly inappropriate requests (e.g., explicit content, personal gossip, self-harm, illegal activity, or detailed medical/legal/financial advice). "
        "Style: be clear and concise; explain step-by-step for math/problems; include short definitions, formulas, and 1-2 key insights; show small code snippets when technical."
    )

    # Early guard for cooking/recipe how-to (stream a short refusal)
    if _is_cooking_or_recipe(latest_user):
        refusal = (
            "I focus on education, general knowledge, mathematics, and technology. "
            "I can’t provide cooking or recipe how‑to steps. If you’d like, I can explain the science behind boiling pasta, basics of nutrition, or the cultural history of noodles."
        )
        async def token_gen_refusal():
            yield refusal.encode()
        return StreamingResponse(token_gen_refusal(), media_type="text/plain")

    if body.messages and len(body.messages) > 0:
        msgs = body.messages[-16:]
        lines: list[str] = [instruction, ""]
        for m in msgs:
            role = (m.role or '').lower()
            content = _truncate(m.content)
            if role == 'assistant':
                lines.append(f"Assistant: {content}")
            elif role == 'user':
                lines.append(f"User: {content}")
        lines.append("Assistant:")
        full_prompt = "\n".join(lines)
    else:
        full_prompt = f"{instruction}\n\nUser: {_truncate(latest_user)}\nAssistant:"

    model = body.model or os.getenv("LLM_MODEL", "llama3:8b")
    temperature = (body.temperature or 0.2)

    async def token_gen():
        async for chunk in stream_generate(full_prompt, model=model, temperature=temperature):
            # Stream plain text chunks
            yield chunk.encode()

    return StreamingResponse(token_gen(), media_type="text/plain")

@app.post("/embed")
async def embeddings(body: EmbedRequest, _rl=Depends(rate_limiter(_env_int("RL_EMBED", 60), _env_int("RL_EMBED_WINDOW", 60)))):
    model = body.model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    try:
        texts = [ _truncate(t, 4000) for t in body.texts ]
        vecs = await embed(texts, model=model)
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"model": model, "vectors": vecs, "count": len(vecs)}

@app.post("/embed2")
async def embeddings2(body: EmbedRequest, _rl=Depends(rate_limiter(_env_int("RL_EMBED", 60), _env_int("RL_EMBED_WINDOW", 60)))):
    model = body.model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    vecs = await embed_texts([ _truncate(t, 4000) for t in body.texts ], model=model)
    return {"model": model, "vectors": vecs, "count": len(vecs)}

@app.post("/vectors/upsert")
async def vectors_upsert(body: UpsertRequest, _rl=Depends(rate_limiter(_env_int("RL_VECT_UPSERT", 120), _env_int("RL_VECT_UPSERT_WINDOW", 60)))):
    res = await qdrant_upsert(body.course_id, [ _truncate(t, 4000) for t in body.texts ], metadata=body.metadata, model=body.model)
    return res

@app.post("/vectors/search")
async def vectors_search(body: SearchRequest, _rl=Depends(rate_limiter(_env_int("RL_VECT_SEARCH", 120), _env_int("RL_VECT_SEARCH_WINDOW", 60)))):
    res = await qdrant_search(_truncate(body.query), top_k=(body.top_k or 5), model=body.model, course_id=body.course_id)
    return res

@app.post("/rag/chat")
async def rag_chat(body: RAGRequest, _rl=Depends(rate_limiter(_env_int("RL_RAG", 60), _env_int("RL_RAG_WINDOW", 60)))):
    # Truncate user query to keep prompts bounded
    q = _truncate(body.query)
    res = await rag_answer(q, course_id=body.course_id, model=body.model, include_summary=body.include_summary if body.include_summary is not None else True, use_reranker=body.use_reranker)
    # Persist chat message
    async for session in get_session():
        # Ensure course exists
        cr = await session.execute(select(Course).where(Course.course_key == body.course_id))
        course = cr.scalar_one_or_none()
        if not course:
            course = Course(course_key=body.course_id, title=body.course_id)
            session.add(course)
            await session.flush()
        session.add(ChatMessage(course_id=course.id, question=body.query, answer=res.get("answer", "")))
        await session.commit()
    return res

@app.get("/chat/history")
async def chat_history(course_id: str, limit: int = 50, offset: int = 0):
    from sqlalchemy import func, desc
    async for session in get_session():
        cr = await session.execute(select(Course).where(Course.course_key == course_id))
        course = cr.scalar_one_or_none()
        if not course:
            return {"items": [], "total": 0}
        total_q = await session.execute(select(func.count()).select_from(ChatMessage).where(ChatMessage.course_id == course.id))
        total = int(total_q.scalar() or 0)
        rows = (await session.execute(
            select(ChatMessage).where(ChatMessage.course_id == course.id).order_by(desc(ChatMessage.created_at)).limit(limit).offset(offset)
        )).scalars().all()
        return {"items": [{"id": m.id, "q": m.question, "a": m.answer, "t": m.created_at.isoformat()} for m in rows], "total": total}

@app.post("/summaries/course")
async def summarize_course(body: SummarizeRequest, _rl=Depends(rate_limiter(_env_int("RL_SUMMARY", 20), _env_int("RL_SUMMARY_WINDOW", 60)))):
    try:
        result = await summarize_course_async(body.course_id, model=body.model, max_chunks=body.max_chunks or 400)
        return result
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/ingest/youtube")
async def ingest_youtube(body: YoutubeIngestRequest, _rl=Depends(rate_limiter(_env_int("RL_YT", 10), _env_int("RL_YT_WINDOW", 300)))):
    try:
        # Ensure a per-course folder exists so the course appears in listings even if only YT content is present
        storage_root = os.getenv("STORAGE_ROOT", "/data/uploads")
        course_dir = os.path.join(storage_root, body.course_id)
        os.makedirs(course_dir, exist_ok=True)

        ingest_res = await ingest_youtube_url(body.url, body.course_id)
        summary = None
        if body.summarize:
            try:
                summary = await summarize_course_async(body.course_id, model=body.model, max_chunks=400)
            except Exception as e:  # summarization optional
                summary = {"error": str(e)}
        return {"ingestion": ingest_res, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/mcq/next")
async def mcq_next_endpoint(body: MCQNextRequest):
    q = await mcq_next(body.course_id, model=body.model)
    return q

@app.post("/mcq/answer")
async def mcq_answer_endpoint(body: MCQAnswerRequest):
    res = await mcq_submit(body.course_id, body.question_id, body.selected_index)
    return res

@app.get("/mcq/stats")
async def mcq_stats(course_id: str, recent_limit: int = 20):
    return await mcq_get_stats(course_id, recent_limit=recent_limit)

# ---- Flashcards ----
@app.post("/flashcards/generate")
async def flashcards_generate(body: FlashGenRequest):
    return await generate_flashcards(body.course_id, model=body.model, max_context=body.max_context or 20)

@app.get("/flashcards/next")
async def flashcards_next(course_id: str, reveal: bool = False, exclude_id: int | None = None):
    return await next_flashcard(course_id, reveal=reveal, exclude_id=exclude_id)

@app.post("/flashcards/grade")
async def flashcards_grade(body: FlashGradeRequest):
    return await grade_flashcard(body.course_id, body.flashcard_id, body.correct)

@app.get("/flashcards/stats")
async def flashcards_stats(course_id: str):
    return await flashcard_stats(course_id)

@app.get("/flashcards/get")
async def flashcards_get(course_id: str, flashcard_id: int):
    return await get_flashcard(course_id, flashcard_id)

@app.get("/flashcards/list")
async def flashcards_list(course_id: str, limit: int = 200, offset: int = 0, box: int | None = None):
    return await list_flashcards(course_id, limit=limit, offset=offset, box=box)

# ---- Background Jobs ----
@app.post("/jobs/ingest/youtube")
async def jobs_ingest_youtube(req: JobYouTubeRequest):
    t = celery_app.send_task("workers.ingest_youtube", args=[req.url, req.course_id], kwargs={"model": req.model, "summarize": req.summarize})
    return {"job_id": t.id, "status": "queued"}

@app.post("/jobs/summaries/course")
async def jobs_summaries_course(req: JobSummaryRequest):
    t = celery_app.send_task("workers.summarize_course", args=[req.course_id], kwargs={"model": req.model})
    return {"job_id": t.id, "status": "queued"}

@app.get("/jobs/{job_id}")
async def jobs_status(job_id: str):
    # Local import to avoid optional dependency issues during static checks
    from celery.result import AsyncResult  # type: ignore
    res = AsyncResult(job_id, app=celery_app)
    out = {"job_id": job_id, "state": res.state}
    if res.state == "SUCCESS":
        out["result"] = res.result
    elif res.state == "FAILURE":
        out["error"] = str(res.result)
    return out

# ---- Deletion Endpoints ----
@app.delete("/materials")
async def delete_material(course_id: str, name: str):
    """Delete a single uploaded file from the course folder and remove its vectors by source."""
    storage_root = os.getenv("STORAGE_ROOT", "/data/uploads")
    course_dir = os.path.join(storage_root, course_id)
    target = os.path.join(course_dir, name)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="file not found")
    # Remove file first
    try:
        os.remove(target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to delete file: {e}")
    # Best-effort: remove vectors whose payload.source == filename
    try:
        from .services.qdrant import delete_by_course_and_source
        delete_by_course_and_source(course_id, name)
    except Exception:
        pass
    return {"ok": True}


@app.get("/materials/download")
async def download_material(course_id: str, name: str):
    """Return a file from the course folder as a download.
    Ensures access is restricted to the specific course directory.
    """
    storage_root = os.getenv("STORAGE_ROOT", "/data/uploads")
    course_dir = os.path.join(storage_root, course_id)
    if not os.path.isdir(course_dir):
        raise HTTPException(status_code=404, detail="course not found")
    # Resolve absolute paths to avoid traversal
    abs_course = os.path.abspath(course_dir)
    file_path = os.path.abspath(os.path.join(course_dir, name))
    if not file_path.startswith(abs_course + os.sep):
        raise HTTPException(status_code=400, detail="invalid path")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(file_path, filename=name)


@app.delete("/materials/youtube")
async def delete_youtube_entry(course_id: str, url: str):
    """Delete YouTube ingested vectors by source url for a course."""
    try:
        from .services.qdrant import delete_by_course_and_source
        res = delete_by_course_and_source(course_id, url)
        return {"ok": True, "qdrant": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/courses/{course_id}")
async def delete_course(course_id: str):
    """Delete everything related to a course: filesystem folder, Qdrant points, and DB artifacts."""
    # 1) Filesystem
    storage_root = os.getenv("STORAGE_ROOT", "/data/uploads")
    course_dir = os.path.join(storage_root, course_id)
    if os.path.isdir(course_dir):
        import shutil
        try:
            shutil.rmtree(course_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"failed to delete course folder: {e}")
    # 2) Qdrant vectors
    try:
        from .services.qdrant import delete_by_course
        delete_by_course(course_id)
    except Exception:
        pass
    # 3) DB artifacts (MCQ, attempts, summaries, flashcards, and the course itself)
    try:
        async for session in get_session():
            res = await session.execute(select(Course).where(Course.course_key == course_id))
            course = res.scalar_one_or_none()
            if course:
                # Delete children first where cascade might not be configured everywhere
                await session.execute(MCQAttempt.__table__.delete().where(MCQAttempt.course_id == course.id))
                await session.execute(MCQQuestion.__table__.delete().where(MCQQuestion.course_id == course.id))
                await session.execute(Summary.__table__.delete().where(Summary.course_id == course.id))
                await session.execute(Flashcard.__table__.delete().where(Flashcard.course_id == course.id))
                await session.delete(course)
                await session.commit()
    except Exception:
        # best-effort; do not fail the whole request if DB clean-up has issues
        pass
    return {"ok": True}
