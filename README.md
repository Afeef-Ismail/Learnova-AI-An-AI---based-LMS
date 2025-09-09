# Learnova AI (Free, Local‑First LMS)

Local‑first LMS with AI features (RAG chat, summaries, MCQ, flashcards, YouTube ingest). Everything runs on your machine with Ollama models.

Core services
- Backend (FastAPI + Celery workers)
- PostgreSQL, Qdrant, RabbitMQ
- Ollama (local LLMs + embeddings)
- Frontend (Next.js 14 App Router)

## Quick start (Docker Compose)

Prereqs
- Windows 10/11 with Docker Desktop or Podman Desktop (Compose support)
- Git (optional but recommended)

1) Copy env templates
- Backend: copy `backend/.env.example` to `backend/.env` and adjust values (secrets, Google client id, etc.)
- Frontend: copy `frontend/.env.example` to `frontend/.env`

2) Start stack
- From the `infra` folder, run Compose to start Postgres, Qdrant, RabbitMQ, backend, and frontend.

3) Pull models (first run only)
- With Ollama running in the stack, pull models in a separate terminal.

4) Visit app
- API health: http://localhost:8000/health
- Web UI:    http://localhost:3001

Notes
- All components are local. No cloud calls.
- Uploads stored in a mounted volume, configured via `STORAGE_ROOT`.

## Development (without containers)

Backend
- Python 3.12+ and Poetry/Pip; create a venv
- Set `backend/.env` (see example)
- Run FastAPI app on http://localhost:8000

Frontend
- Node 18+ (LTS)
- Set `frontend/.env`
- Run Next.js dev server on http://localhost:3001

## Environment variables

Backend (see `backend/.env.example`)
- FRONTEND_ORIGIN, JWT_SECRET, GOOGLE_CLIENT_ID
- Postgres: POSTGRES_*
- RabbitMQ/Celery: RABBITMQ_URL, CELERY_RESULT_BACKEND
- Qdrant: QDRANT_HOST/PORT/COLLECTION, EMBEDDING_MODEL/DIM
- Ollama: OLLAMA_HOST, OLLAMA_TIMEOUT, LLM_MODEL, SUMMARY_MODEL
- Rerank/Whisper: RERANK_ENABLED/MODEL, WHISPER_MODEL
- ytdlp: YTDLP_*
- Limits/Truncation: RL_* and MAX_* sizes

Frontend (see `frontend/.env.example`)
- NEXT_PUBLIC_API_BASE (default http://localhost:8000)
- NEXT_PUBLIC_GOOGLE_CLIENT_ID

## Auth
- Backend: `/auth/signup`, `/auth/login`, `/auth/google` produce JWT
- Frontend: `/signup`, `/login` use Google Identity Services when configured
- JWT is kept in localStorage and automatically attached in `frontend/lib/api.ts`

## Share the project with friends

1) GitHub (recommended)
- Initialize a repo, push, and share the URL. Teammates clone, copy the two `.env.example` files to `.env`, and run the Compose stack.

2) Zip + run locally
- Zip the repo excluding large build folders (`node_modules`, `.next`, `__pycache__`).
- Friends unzip, create `.env` files from examples, then run the Compose stack.

3) Docker‑only handoff
- Build and push your images to a registry you all can access (or export with `docker save`).
- Share just the `infra/compose.yaml` and .env files; friends run Compose pulling the images.

4) Portable devcontainer (optional)
- Check in a `.devcontainer` config so VS Code can open and run with the same containerized env.

Tip: Compose is the easiest way—one command starts everything consistently across machines.

## Push to GitHub

1) Initialize and commit locally
- Create a `.gitignore` at repo root (already provided)
- Commit code with the `.env.example` files only (never commit real secrets)

2) Create a new empty GitHub repo (no README/license)

3) Add remote and push main branch

That’s it. Share the GitHub URL with your friends.

## Troubleshooting
- Ports busy: change exposed ports in `infra/compose.yaml`
- Model downloads slow: pull models once and reuse volumes; or pre‑load models and share the Ollama volume
- CORS errors: ensure `FRONTEND_ORIGIN` matches the frontend URL
