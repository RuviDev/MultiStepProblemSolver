# Relativity AI — Carrer Intake & Guidance

> AI guidance platform with career/skills intake, insight surveys, and grounded answers.

---

## 🎥 Demo

[![Watch the demo](https://img.youtube.com/vi/nJkWWQKWAHo/hqdefault.jpg)](https://youtu.be/nJkWWQKWAHo)

---

## Table of Contents

* [Overview](#overview)
* [Project Structure](#monorepo-structure)
* [Tech Stack](#tech-stack)
* [Quick Start](#setup)

  * [Backend Setup](#1-backend)
  * [Frontend Setup](#2-frontend)
* [Configuration](#configuration)

  * [Backend Environment Variables](#backend-environment-variables)
  * [Frontend Environment Variables](#frontend-environment-variables)
* [Usage Guide](#usage-guide)
* [Testing](#testing)
* [Responsible AI](#responsible-ai)
* [Security & Privacy](#security--privacy)
* [Deployment](#deployment)
* [Troubleshooting](#troubleshooting)
* [Contributing](#contributing)

---

## Overview

This repository contains a full-stack, AI-assisted guidance platform organized as a **monorepo** with a Python/FastAPI backend and a modern JS frontend. Users create chat sessions, complete a light **User Intake & Analysis (UIA)** (employment category + skills), and receive **insight surveys**. Answers are either LLM-assisted or **RAG-grounded** against a curated knowledge set. The system emphasizes **Responsible AI**: scoped behavior, transparent steps, and privacy-preserving storage.

---

## Monorepo Structure

```
agentic-ai/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ core/
│  │  │  ├─ settings.py
│  │  │  ├─ security.py
│  │  │  ├─ llm.py
│  │  │  └─ openai_client.py
│  │  ├─ db/
│  │  │  ├─ mongo.py
│  │  │  └─ init_db.py
│  │  ├─ api/
│  │  │  ├─ __init__.py
│  │  │  ├─ deps.py
│  │  │  └─ routes/
│  │  │     ├─ health.py
│  │  │     ├─ auth.py
│  │  │     ├─ chats.py
│  │  │     ├─ messages.py
│  │  │     ├─ uia.py
│  │  │     ├─ insights.py
│  │  │     └─ vault.py
│  │  ├─ components/
│  │  │  ├─ component5.py       # Decision Gate (scope/safety)
│  │  │  ├─ component8_rag.py   # Grounded answers with sources
│  │  │  └─ component10.py      # Next-step encouragement
│  │  ├─ models/
│  │  │  ├─ vault.py
│  │  │  ├─ insights.py
│  │  │  ├─ chat.py
│  │  │  └─ alias.py
│  │  ├─ repositories/
│  │  │  ├─ user_repo.py
│  │  │  ├─ token_repo.py
│  │  │  ├─ chats_repo.py
│  │  │  ├─ messages_repo.py
│  │  │  ├─ vault_repo.py
│  │  │  ├─ insight_vault_repo.py
│  │  │  ├─ chat_insights_repo.py
│  │  │  ├─ alias_repo.py
│  │  │  └─ events_repo.py
│  │  ├─ services/
│  │  │  ├─ progress.py
│  │  │  ├─ textnorm.py
│  │  │  ├─ intent_llm.py
│  │  │  ├─ insight_engine.py
│  │  │  ├─ insight_survey.py
│  │  │  ├─ insight_completion.py
│  │  │  ├─ intent.py
│  │  │  ├─ events.py
│  │  │  ├─ survey.py
│  │  │  ├─ seed_vault.py
│  │  │  └─ seed_insight_vault.py
│  │  └─ rag/
│  │     ├─ 0_phase0/
│  │     ├─ 1_raw_pdfs/
│  │     ├─ 2_docling/
│  │     ├─ 3_clean/
│  │     ├─ 4_chunks/
│  │     ├─ 5_index/
│  │     ├─ agentic-rag/
│  │     └─ scripts/
│  │        └─ component8_rag.py
│  ├─ scripts/
│  │  ├─ seed_insight_vault.py
│  │  └─ seed_vault.py
│  ├─ .env
│  ├─ .env.example
│  ├─ requirements.txt
│  ├─ Dockerfile
│  └─ docker-compose.yml
└─ frontend/
   ├─ src/
   │  ├─ app/
   │  │  ├─ aiChat.jsx
   │  │  └─ aiChat-Body/
   │  │     ├─ home.jsx
   │  │     ├─ chat/
   │  │     │  ├─ welcome.jsx
   │  │     │  ├─ messageList.jsx
   │  │     │  ├─ MarkdownMessage.jsx
   │  │     │  └─ AssistantProgress.jsx
   │  │     └─ summary/summary.jsx
   │  ├─ components/
   │  │  ├─ chat/
   │  │  │  ├─ AgentCardsSection.jsx
   │  │  │  ├─ AskField.jsx
   │  │  │  └─ ProblemStatementCard.jsx
   │  │  ├─ common/
   │  │  │  ├─ Header.jsx
   │  │  │  └─ SideBar.jsx
   │  │  └─ surveys/
   │  │     ├─ EmploymentSurvey.jsx
   │  │     ├─ InsightBatch.jsx
   │  │     ├─ InsightQuestionCard.jsx
   │  │     ├─ InsightSurvey.jsx
   │  │     └─ SkillsSurvey.jsx
   │  ├─ pages/
   |  │  ├─ Login.jsx
   |  │  ├─ Signup.jsx
   │  ├─ lib/api.js               # axios client, token storage, endpoints
   │  ├─ App.jsx                  # routes and auth guard
   |  ├─ index.css / App.css
   │  └─ main.jsx                 # app entry
   └─ (.env, package.json, vite config, tailwind config live at frontend root)
```

> **Note:** The backend is built with FastAPI, MongoDB (Motor), and Pydantic v2, using an async OpenAI client for AI-driven logic. The frontend is a React (Vite) app using Axios for secure API communication, React Router for navigation, and Tailwind-style utilities for layout and design.

---

## Tech Stack

**Backend**

* Python 3.11, FastAPI, Uvicorn
* Motor (MongoDB async driver), Pydantic v2
* Auth: passlib/bcrypt, python-jose (JWT access + hashed/rotated refresh tokens)
* OpenAI async client (strict JSON helper)

**Frontend**

* React 18 + React Router v6
* Axios for HTTP with request/response interceptors (auto refresh on 401)
* React Markdown + remark-gfm (rehypeRaw **disabled** for XSS safety)
* lucide-react for icons
* Tailwind-style utility classes used throughout (ensure Tailwind is configured in this project)
* Vite for dev/build
---

## Setup

### Prerequisites

* **Python** 3.11+
* **Node.js** 18+
* **MongoDB** running locally (or reachable via `MONGO_URI` in backend `.env`)

### 1) Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
cp .env.example .env   # fill values (MONGO_URI, DB_NAME, JWT_SECRET, OPENAI_API_KEY, etc.)

# Start the Backend
uvicorn app.main:app --reload --port 8000
```

#### (Optional) Seed Vaults (run only if empty)

```bash
# If Segment Vault is empty, create a sample Vault
python -m scripts.seed_vault

# If Insight Vault is empty, create a sample Insight Vault
python -m scripts.seed_insight_vault
```

### 2) Frontend

```bash
cd frontend
npm install

# Configure API base URL for the browser
printf "VITE_API_URL=http://localhost:8000
" > .env.local

# Start the Frontend
npm run dev
```

---

## Configuration

### Backend Environment Variables

| Variable                       | Required | Example                     | Description                                                              |
| ------------------------------ | -------- | --------------------------- | ------------------------------------------------------------------------ |
| `ENV`                          | No       | `dev`                       | Environment name                                                         |
| `MONGO_URI`                    | Yes      | `mongodb://localhost:27017` | Mongo connection string                                                  |
| `MONGO_DB`                     | Yes      | `agentic_ai`                | Database name                                                            |
| `JWT_SECRET`                   | Yes      | `change_me`                 | HMAC secret for access tokens                                            |
| `ACCESS_TOKEN_MINUTES`         | Yes      | `30`                        | Access token lifetime                                                    |
| `REFRESH_TOKEN_DAYS`           | Yes      | `7`                         | Refresh token lifetime                                                   |
| `OPENAI_API_KEY`               | Yes      | `sk-***`                    | OpenAI key for LLM features                                              |
| `OPENAI_MODEL`                 | Yes      | `gpt-4o-mini`               | Base model for JSON-completions                                          |
| `OPENAI_REQUEST_TIMEOUT`       | No       | `12`                        | Request timeout (seconds) for OpenAI calls                               |
| `INSIGHT_VAULT_VERSION`        | Yes       | `v2025-10-13`               | Which Insight Vault version to use                                       |
| `INSIGHTS_MODEL`               | No       | ``                          | Override model for insights auto-infer                                   |
| `INSIGHTS_TEMPERATURE`         | No       | `0.2`                       | Sampling temperature for insights flows                                  |
| `INSIGHTS_TOP_P`               | No       | `0.3`                       | Top Insights to take                                                     |
| `RAG_LLM_MODEL`                | Yes      | `gpt-4.1`                   | Model for composing grounded answers                                     |
| `RAG_PLANNER_MODEL`            | Yes      | `gpt-4.1-mini`              | Model for query/sub-query planning                                       |
| `RAG_RERANK_MODEL`             | Yes      | `gpt-4.1-mini`              | Model for reranking retrieved chunks                                     |
| `RAG_ALLOW_GENERAL_KNOWLEDGE`  | Yes      | `true`                      | Allow model to supplement beyond retrieved chunks when context is thin   |
| `RAG_MAX_GENERAL_PERCENT`      | Yes      | `0.25`                      | Max fraction (0–1) of response that may be non-RAG general knowledge     |

> Notes:
>
> * If `INSIGHTS_MODEL` is empty, backend will fall back to `OPENAI_MODEL`.
> * `RAG_ALLOW_GENERAL_KNOWLEDGE` should be parsed as a boolean (e.g., `true/false`, case-insensitive).
> * Keep `RAG_MAX_GENERAL_PERCENT` between `0` and `1` (e.g., `0.25` = 25%).

### Frontend Environment Variables

| Variable       | Required | Example                 | Description                                 |
| -------------- | -------- | ----------------------- | ------------------------------------------- |
| `VITE_API_URL` | Yes      | `http://localhost:8000` | Base URL for the backend API used by axios. |

> The code references `import.meta.env.VITE_API_URL`. If not set, it defaults to `http://localhost:8000`.

---

## Usage Guide

1. **Open the app** at the frontend dev URL (usually shown by Vite, e.g., [http://localhost:5173](http://localhost:5173)).
2. **Sign up or sign in**.
3. **Create a chat** (or open an existing one), then **ask a question**.
4. Watch the assistant’s **progress labels** (Decision Gate → UIA → Survey/Answer) update live.
5. If prompted, complete the **Employment Category** survey (single-select), then **Skills** (1–4, or let the system decide).
6. Answer any **Insight** questions shown. Submissions are saved to your chat context.
7. The assistant may provide **grounded answers** (with sources) and **one next step** questions.

> Tips:
>
> * If you see no UIA/Insight questions, seed vaults or verify your backend `.env` and Mongo connection.
> * If tokens expire, the app refreshes them automatically on the next request.

---

## Testing

* **Backend:** Include tests for:

  * Auth flows (signup/signin/refresh/logout)
  * UIA flows (employment category & skills validation)
  * Insight auto-infer → survey build → submission stats
  * RAG planner + grounded answers (source presence)
  * Guardrails (Decision Gate) edge cases
* **Frontend:** unit tests for survey components and markdown renderer; E2E for auth + chat + progress stream

---

## Responsible AI

This system embeds RAI controls **inside the business logic** (not just the UI):

* **Scoped behavior (Decision Gate):** The agent refuses out-of-scope or unsafe requests with a friendly, single-sentence boundary. Short replies to the previous assistant question are treated as valid, reducing bias against terse or ESL users.
* **Fair intake (UIA):** Text normalization + alias indexing recognize employment categories and skills across synonyms/spelling, and enforce **1–4 skills** within the chosen category for consistent, comparable guidance.
* **Structured insights:** Pending insights are inferred via **strict JSON** outputs; surveys are compact and auditable. No sensitive demographics are required.
* **Grounded answers:** The RAG component composes answers using **only retrieved chunks** and stores **sources** for transparency.
* **Deterministic fallbacks:** If an LLM deviates from constraints (e.g., omits required options), the system falls back to **deterministic questions** to ensure clarity and equal treatment.

---

## Security & Privacy

* Passwords hashed with **bcrypt_sha256**; JWT access tokens + **hashed & rotated** refresh tokens (revocable, with UA/IP metadata).
* Minimal PII by design; main data are chats/messages/surveys.
* Mongo indexes created on startup; message/survey data are always scoped to the **current user & chat**.
* In production, restrict `CORS_ALLOW_ORIGINS` and store secrets outside the repo.

---

## Deployment

* **Docker Compose** for local/staging.
* For production, use a managed MongoDB and a reverse proxy/ingress with TLS. Configure environment variables, logging, and resource limits.

---

## Troubleshooting

* **Cannot connect to API:** Ensure the backend is on port `8000` and `VITE_API_URL` points to it.
* **401 loops:** Clear tokens (localStorage `auth_tokens`) and sign in again; make sure `/auth/refresh` works.
* **CORS errors:** Add your frontend origin to backend CORS allowlist in `.env`.
* **No surveys appear:** Seed vaults using the commands above and restart the backend.
* **SSE not updating:** Some networks block EventSource; try a direct connection or check backend logs for progress events.

---

## Contributing

| Name | GitHub | Role | Summary of Responsibilities |
| :--- | :--- | :--- | :--- |
| A. V. Amarathunga | [@Ashan-Amarathunga](https://github.com/Ashan-Amarathunga) | Project Leader | Oversaw full system development, guided architecture and planning, resolved issues across all stages, and enhanced backend agentic + RAG pipelines. |
| M. S. R. V. Amararathna | [@RuviDev](https://github.com/RuviDev) | Backend Lead | Led backend development of agentic AI pipeline, managed frontend–backend integration, and handled system-level debugging and risk mitigation. |
| S. A. R. U. Amarasinghe | [@reshika1219](https://github.com/reshika1219) | Full‑Stack Developer | Built frontend for agentic AI system, developed RAG knowledge base (PDF → FAISS vectors), and contributed to documentation & media. |
| A. A. Gunawardena | [@agunawardena02](https://github.com/agunawardena02) | Full‑Stack Developer | Implemented frontend features, supported RAG knowledge base creation (PDF → FAISS vectors), and produced documentation & demo videos. |
---

