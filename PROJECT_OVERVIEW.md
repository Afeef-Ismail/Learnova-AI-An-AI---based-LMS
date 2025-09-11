# Learnova AI – Project Overview (Plain Language)

Last updated: 2025-09-09

This document explains what Learnova AI is, what it does, how it works behind the scenes, and which technologies we used. It is written for a non‑technical audience.

---

## What is Learnova AI?
Learnova AI is a personal learning assistant. You can create courses, upload study materials, get short summaries, practice with multiple‑choice questions (MCQs) and flashcards, and chat with an educational AI tutor. Everything runs on your computer using Docker.

---

## What can it do? (Features)
- Accounts and sign‑in (email/password or Google).
- Courses: create and manage your own courses.
- Upload materials: files and YouTube links.
- Summaries: short, clear explanations of long content.
- MCQ practice: AI‑generated quiz questions and answers.
- Flashcards: quick Q/A cards for revision.
- Edu Chatbot: ask general educational questions (math, science, tech, GK); answers stream in live.
- Course Q&A (RAG): ask questions about your uploaded materials; answers include relevant content.

---

## How does it work? (End‑to‑end)
1) You open the web app in your browser.
2) The frontend (the website) sends requests to the backend (the server).
3) The backend saves normal information (users, courses, messages) in a database called Postgres.
4) The backend turns your text into special numbers called embeddings and stores them in a vector database called Qdrant. This lets the app find the most relevant passages quickly.
5) When you do heavy work (like processing a big file or YouTube), we put it on a task queue so it runs in the background. This keeps the app fast.
6) For Edu Chat and Course Q&A, the backend asks a local AI model to write the answer. It streams the answer in small pieces so you see it appear live.

---

## The technology stack (simple words)
- Frontend: Next.js (React). The user interface — the screens, buttons, inputs.
- Backend: FastAPI (Python). The application brain — receives requests, checks permissions, saves data, calls AI.
- Database: Postgres. Stores tables like users, courses, summaries, etc.
- Vector store: Qdrant. Stores embeddings (number fingerprints of text) for quick, meaning‑based search.
- Background work: Celery + RabbitMQ. Runs long tasks in the background so the interface stays responsive.
- AI model: accessed locally (via Ollama). Generates summaries, explanations, quizzes, and chat responses.
- Docker Compose: one command to start everything consistently.
- Tailwind CSS: modern styles and responsive layout.

Why these choices?
- Easy to understand, widely used, and free/open‑source.
- Runs locally (no cloud billing). Works offline after the first model downloads.

---

## Data flow (with an example)
Example: You upload a PDF to a course.
- The file is saved to storage. The backend extracts text.
- The text is split into small chunks. Each chunk is converted to an embedding (numbers) and stored in Qdrant, while the file info and course info go to Postgres.
- Later, you ask a course question. The backend searches Qdrant for the most relevant chunks, then asks the AI model to answer, using those chunks as context. You see the answer stream in immediately.

---

## Security and performance choices
- CORS locked to the frontend website to avoid cross‑site misuse.
- Gzip compression and basic security headers on the API.
- Rate limits to prevent spam and accidental overload.
- Truncation of very long prompts to keep AI stable.
- Google Sign‑In is supported without exposing secrets. The Client ID is public by design; real secrets stay in local `.env` files that are not committed.
- Health checks and restarts so services stay up.

---

## How to run it (summary)
- Prerequisite: Docker Desktop (or Podman) running.
- Copy example env files to real ones and fill values:
  - `backend/.env` (backend settings)
  - `frontend/.env` (frontend settings)
  - `infra/.env` (compose-level values like Google Client ID)
- Start all services:
  - On Windows PowerShell: `docker compose -f infra/compose.yaml up -d --build`
- First run only, pull AI models inside the Ollama container (if included), or run Ollama locally.
- Visit http://localhost:3001 (web) and http://localhost:8000/health (API).

---

## How the main parts work (slightly deeper)
- Frontend (Next.js):
  - Pages like Login, Signup, My Courses, Upload, Course Detail (Materials, Summaries, MCQ, Flashcards, YouTube, Course Chat), and Edu Chat.
  - Uses a small helper to call the API and attach your login token.
  - Shows streaming answers, copy buttons, and helpful messages.

- Backend (FastAPI):
  - Auth: creates accounts, verifies logins, checks Google tokens, and returns a JWT.
  - Edu Chat: builds a “system instruction” so the AI focuses on education; refuses non‑scope how‑tos (like recipes). Adds the current date for clarity.
  - RAG: stores vectors in Qdrant, finds relevant chunks, and asks the AI to answer based on your materials.
  - Content generation: makes summaries, MCQs, and flashcards with clear prompts and limits.
  - Background jobs: processes big files and YouTube so the website stays fast.

- Databases:
  - Postgres: reliable tables and relationships (users, courses, materials, messages, etc.).
  - Qdrant: quick similarity search on embeddings for accurate, context‑aware answers.

---

## What makes it “demo‑ready”
- Clean UI with sensible defaults.
- Streaming chat for a lively presentation.
- Copy buttons for answers and code blocks.
- Kebab menus that don’t get hidden.
- Default tab set to Materials for course view.
- Clear error handling and loading states (spinners, skeletons, toasts).

---

## Suggested demo script
1) Sign in with Google.
2) Go to My Courses → open a course.
3) Materials tab: show uploads.
4) Upload page: add a YouTube link or file to a course by name.
5) Summaries tab: show short summaries.
6) MCQ and Flashcards tabs: practice quickly.
7) Course Chat: ask a question about the course and copy the answer.
8) Edu Chat: ask a general academic/tech question; show streaming, Stop/Regenerate/Continue; show polite refusal for non‑educational how‑tos.

---

## FAQ (expected panel questions)
- Does it need the cloud? No. It runs locally with Docker and a local AI model.
- Is my data private? Yes. Everything stays on your machine unless you choose to share it.
- Is the Google Client ID a secret? No. It’s public by design. We keep real secrets only in local `.env` files.
- What happens if the file is huge? We chunk and process it in the background. The UI remains responsive.
- Can it handle images or only text? This version focuses on text. Images can be added later with OCR or vision models.

---

If you need a shorter or more visual version for slides, I can generate slide bullets or a one‑pager next.
