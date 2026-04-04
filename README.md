# Site Audit AI

An AI-powered website auditing tool built with **FastAPI**, **Playwright**, **Lighthouse**, and **Claude** (Anthropic). Submit any public URL and get back a comprehensive audit covering SEO, content quality, accessibility, performance, and technical health.

---

## Architecture

```
site-audit/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app & lifespan hooks
│   │   ├── config.py        # Pydantic Settings (env vars)
│   │   ├── database.py      # Async SQLAlchemy engine + Redis client
│   │   ├── models/audit.py  # SQLAlchemy ORM models
│   │   ├── schemas/audit.py # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── crawler.py   # Playwright multi-page crawler
│   │   │   ├── analyzer.py  # Claude AI analysis
│   │   │   └── lighthouse.py# Lighthouse CLI wrapper
│   │   └── api/routes.py    # All HTTP endpoints
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── docker-compose.yml
└── README.md
```

---

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose
- An Anthropic API key

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and set ANTHROPIC_API_KEY
```

### 3. Start services

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`.

---

## API Reference

### Health Check

```
GET /health
```

Returns the operational status of the API, database, and Redis.

**Response**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "redis": "ok"
}
```

---

### Submit an Audit

```
POST /api/audit
Content-Type: application/json
```

**Request body**
```json
{
  "url": "https://example.com",
  "max_pages": 10,
  "include_lighthouse": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | string (URL) | — | The website to audit (required) |
| `max_pages` | integer | `10` | Maximum pages to crawl (1–50) |
| `include_lighthouse` | boolean | `true` | Run Lighthouse performance audit |

**Response** `202 Accepted`
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "message": "Audit job accepted and queued."
}
```

---

### Get Audit Results

```
GET /api/audit/{job_id}
```

**Response** `200 OK`
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "url": "https://example.com",
  "status": "completed",
  "error_message": null,
  "ai_summary": "The site performs well overall…",
  "category_scores": [
    {
      "id": "…",
      "category": "SEO",
      "score": 0.82,
      "label": "Good",
      "details": {
        "findings": ["All pages have unique titles"],
        "recommendations": ["Add meta descriptions to 3 pages"]
      }
    }
  ],
  "created_at": "2026-04-04T12:00:00Z",
  "started_at": "2026-04-04T12:00:01Z",
  "completed_at": "2026-04-04T12:01:15Z"
}
```

**Status values:** `pending` → `running` → `completed` | `failed`

---

## Interactive Docs

| URL | Description |
|---|---|
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/redoc` | ReDoc |

---

## Local Development (without Docker)

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Install Playwright browsers
playwright install chromium

# Copy and edit environment variables
cp backend/.env.example backend/.env

# Run the development server (from the backend directory)
cd backend
uvicorn app.main:app --reload --port 8000
```

Ensure PostgreSQL and Redis are running locally and that `DATABASE_URL` / `REDIS_URL` in `.env` point to them.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` | Async PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-opus-4-5` | Claude model to use for analysis |
| `CLAUDE_MAX_TOKENS` | `4096` | Maximum tokens in Claude response |
| `MAX_CRAWL_PAGES` | `10` | Default page crawl limit |
| `PLAYWRIGHT_TIMEOUT_MS` | `30000` | Playwright navigation timeout (ms) |
| `LIGHTHOUSE_BINARY` | `lighthouse` | Path / name of the Lighthouse CLI |
| `LIGHTHOUSE_TIMEOUT_MS` | `60000` | Lighthouse execution timeout (ms) |
| `CACHE_TTL_SECONDS` | `3600` | Redis cache TTL for completed jobs |
| `DEBUG` | `false` | Enable SQLAlchemy query logging |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + SQLAlchemy 2 (async) |
| Cache | Redis 7 |
| Crawling | Playwright (Chromium, headless) |
| Performance | Lighthouse CLI |
| AI analysis | Anthropic Claude API |
| Containerisation | Docker + Docker Compose |
