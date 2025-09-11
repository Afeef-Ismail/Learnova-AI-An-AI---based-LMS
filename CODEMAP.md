# Learnova AI – Code Map (Plain Language)

Last updated: 2025-09-09

This document explains every file in the project, in simple terms: what it is for, what it does, and how it fits in. It follows the repository layout from top to bottom.

---

## Root (top-level)

- .gitignore
  - Tells Git which files/folders to ignore (build outputs, caches, local .env files, etc.). Keeps the repo clean and safe.

- README.md
  - The project overview and quick start instructions. Shows what the app does and how to run it.

- app.py
  - Small helper script to run the backend during local development. Not used in Docker.

---

## backend/ (server API, AI, background jobs)

- backend/.env.example
  - Example backend settings. Copy to `backend/.env` and fill in local values. Never commit real secrets.

- backend/Dockerfile
  - Steps to build the backend container image (install Python, dependencies, set start command).

- backend/pyproject.toml
  - Python dependencies and tool settings for the backend (what to install and how).

### backend/app/ (backend source code)

- backend/app/__init__.py
  - Marks this folder as a Python package so other modules can import from it.

- backend/app/core/database.py
  - Connects to the Postgres database. Provides a helper to get a database session in API routes.

#### Flashcards
- backend/app/flashcards/__init__.py
  - Empty file that marks the `flashcards` folder as a Python package.

- backend/app/flashcards/service.py
  - Creates Q/A flashcards from text using the AI model. Think “term → definition” pairs.

#### Ingestion
- backend/app/ingestion/pipeline.py
  - The content pipeline: takes uploaded files or links, extracts text, splits it into chunks, stores info in the database, and sends chunks for embeddings.

#### Main API and routes
- backend/app/main.py
  - The main FastAPI app. Adds CORS, compression, and security headers.
  - Health check `/health`: lets Docker know the service is ready.
  - Auth: signup, login, Google sign-in; returns JWTs used by the frontend.
  - Edu Chat: `/chat/edu` and `/chat/edu/stream` for general educational Q&A with safe limits and streaming responses.
  - Vectors: upsert/search endpoints to store and query embeddings in Qdrant.
  - RAG: `/rag/chat` answers questions using your uploaded course materials.
  - Summaries / MCQ / Flashcards: endpoints to generate study aids for a course.
  - Guards (e.g., no recipe how‑tos) and a date hint (“as of YYYY‑MM‑DD”) for time‑sensitive answers.

#### MCQ (Quiz)
- backend/app/mcq/__init__.py
  - Empty file marking the MCQ folder as a package.

- backend/app/mcq/generator.py
  - Generates multiple‑choice questions from given text. Asks the AI for question, options, answer, and explanation.

- backend/app/mcq/stats.py
  - Basic stats about quiz attempts (e.g., correct rate, counts).

#### Database models (tables)
- backend/app/models/db_models.py
  - Table definitions (Users, Courses, Materials, Summaries, MCQs, Flashcards, ChatMessages, etc.). Describes fields and relationships.

#### RAG (retrieve and answer)
- backend/app/rag/rag.py
  - Finds the most relevant chunks from Qdrant and asks the AI to answer using those chunks as context.

#### Services (helpers)
- backend/app/services/embeddings.py
  - Turns text into vectors (embeddings). Used when saving content and when searching.

- backend/app/services/ollama.py
  - Wraps calls to the local AI model (generate text, stream tokens).

- backend/app/services/qdrant.py
  - Connects to Qdrant (vector database). Creates collections, upserts vectors, and searches similar chunks.

- backend/app/services/reranker.py
  - Optional quality step. Reorders retrieved chunks so the most helpful appear first.

#### Summaries
- backend/app/summaries/__init__.py
  - Empty package marker for the `summaries` folder.

- backend/app/summaries/summarize.py
  - Creates concise summaries of course materials by prompting the AI.

#### Background workers
- backend/app/workers/celery_app.py
  - Configures Celery (the background job system) and connects to RabbitMQ.

- backend/app/workers/tasks.py
  - The background jobs themselves: process uploads, compute embeddings, store in Qdrant, summarize, generate MCQs/flashcards, process YouTube, etc.

---

## frontend/ (web app UI)

- frontend/.env.example
  - Example frontend settings. Copy to `frontend/.env` for local runs (e.g., API base URL).

- frontend/Dockerfile
  - Steps to build the frontend container (install Node, install deps, start or build Next.js).

### Global config, styles, and types
- frontend/next-env.d.ts
  - Auto‑generated TypeScript types for Next.js. Do not edit.

- frontend/next.config.js
  - Next.js settings. Also whitelists image hostnames (e.g., YouTube thumbnails) so images load.

- frontend/tailwind.config.js
  - Tailwind CSS setup. Tells Tailwind where to scan for class names and sets theme tokens.

- frontend/postcss.config.js
  - Enables Tailwind via PostCSS so Tailwind classes turn into CSS.

- frontend/app/globals.css
  - Global CSS: base styles and shared utility classes (buttons, cards, layout).

### TypeScript config and package metadata
- frontend/tsconfig.json
  - TypeScript compiler settings (strictness, path aliases).

- frontend/tsconfig.tsbuildinfo
  - Build cache produced by TypeScript. Safe to ignore.

- frontend/package.json
  - Frontend dependencies and scripts (dev, build, start).

- frontend/package-lock.json
  - Exact dependency versions for reproducible installs.

### App Router pages (user screens)
- frontend/app/layout.tsx
  - The common shell for all pages (sidebar + top bar). Includes theme provider and auth guard (redirects to /login when needed).

- frontend/app/page.tsx
  - Home page. Greets the user (e.g., “Welcome back”) and links to key features.

- frontend/app/login/page.tsx
  - Login screen (email/password + Google Sign‑In).

- frontend/app/signup/page.tsx
  - Sign‑up screen (name, email, password + Google).

- frontend/app/settings/page.tsx
  - App settings (e.g., light/dark theme).

- frontend/app/profile/page.tsx
  - Shows the current user’s info from the token (name, email).

- frontend/app/browse/page.tsx
  - Browse public or available courses/materials (read‑only view).

- frontend/app/upload/page.tsx
  - Upload files or add a YouTube link to a named course. Sends requests to the backend; workers handle heavy processing.

- frontend/app/courses/page.tsx
  - “My Courses” dashboard. Shows course cards and a kebab menu (Rename/Delete). The menu uses a portal so it renders above other elements.

- frontend/app/courses/[id]/page.tsx
  - Course detail page with tabs. Defaults to Materials. Other tabs: Summarize, MCQ Practice, Flashcards, YouTube, and Course Chat (RAG). RAG answers have a Copy button.

- frontend/app/courses/[id]/flashcards/page.tsx
  - Flashcards practice for the selected course (flip cards, mark correct/incorrect).

- frontend/app/mcq/page.tsx
  - Multiple‑choice practice page (question, options, answer feedback, simple stats).

- frontend/app/flashcards/page.tsx
  - Flashcards hub for quick practice outside a specific course.

- frontend/app/chat/page.tsx
  - Edu Chatbot page. Supports streaming answers, Stop, Regenerate, Continue, Edit‑and‑resend, Copy buttons, and conversation rename/delete/persist.

### Reusable UI components
- frontend/components/FlipCard.tsx
  - A flippable card component for flashcards (front/back).

- frontend/components/KebabMenu.tsx
  - Three‑dot menu. Renders via a portal so it isn’t hidden by other cards.

- frontend/components/Skeleton.tsx
  - Loading placeholders (gray bars) while data is fetched.

- frontend/components/Spinner.tsx
  - Small loading spinner for pending actions.

- frontend/components/Toaster.tsx
  - Toast notifications (small success/error popups).

### Frontend helper
- frontend/lib/api.ts
  - Tiny wrapper for fetch:
    - Attaches JWT to requests.
    - On 401 (Unauthorized), clears token and redirects to /login.
    - Central place to set API base URL.

---

## infra/ (run everything with Docker Compose)

- infra/.env.example
  - Example env file for Compose (IDs and other values). Copy to `infra/.env`; never commit real values.

- infra/compose.yaml
  - Starts all services together:
    - postgres (database)
    - rabbitmq (message queue)
    - qdrant (vector search)
    - backend (FastAPI API)
    - worker (Celery background jobs)
    - frontend (Next.js UI)
  - Health checks, restart policies, volume mounts (persistent data), and port mappings.
  - Reads configuration from `infra/.env` so you don’t hardcode IDs in the repo.

---

## How all parts work together (quick recap)
- Frontend (Next.js) is the app people see and use.
- Backend (FastAPI) handles requests from the frontend and talks to databases and the AI model.
- Postgres stores regular tables (users, courses, messages, etc.).
- Qdrant stores embeddings (numeric “fingerprints” of text) for smart search.
- RabbitMQ + Celery run long jobs in the background so the UI stays fast.
- AI powers Edu Chat and course Q&A; answers stream in live for a smooth experience.

---

## Demo script (optional presenter notes)
1) Log in (show Google sign‑in).
2) Open My Courses (kebab menu works reliably).
3) Open a course → Materials tab (default), show uploads.
4) Upload page → add a YouTube link or file to a course by name.
5) Summaries, MCQ, Flashcards tabs → show generated study aids.
6) Course Chat (RAG) → ask a question, copy the answer.
7) Edu Chat → ask general academic/tech questions; show streaming, Stop/Regenerate/Continue/Copy; show that recipes are politely refused.

---

Need this customized further or printed? I can generate a PDF‑friendly version and tailor it to any new files you add.
