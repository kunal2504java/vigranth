# UnifyInbox

**AI-native universal communication OS.** Consolidates Gmail, Slack, Discord, and Telegram into a single AI-ranked priority feed with draft replies and cross-platform send.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [AI Agent Pipeline](#ai-agent-pipeline)
- [Platform Adapters](#platform-adapters)
- [Priority Scoring](#priority-scoring)
- [API Endpoints](#api-endpoints)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Docker Services](#docker-services)
- [Frontend](#frontend)
- [Pricing Tiers](#pricing-tiers)
- [Specs & Documentation](#specs--documentation)
- [License](#license)

---

## Overview

UnifyInbox pulls messages from multiple communication platforms, runs them through a 6-agent AI pipeline (powered by Claude), and presents a single ranked feed. Users see what matters first, get AI-drafted replies, and send responses back to the original platform without switching apps.

**Key capabilities:**

- Unified inbox across Gmail, Slack, Discord, Telegram
- AI priority ranking with 6 weighted signals
- One-click AI draft replies with configurable tone profiles
- Cross-platform send (reply from UnifyInbox, delivered on the original platform)
- Real-time WebSocket feed with live updates
- Webhook ingestion for instant message arrival
- Background sync, snooze, and priority decay via Celery

---

## Architecture

```
                          +------------------+
                          |   Next.js 16     |
                          |   Frontend       |
                          +--------+---------+
                                   |
                              WebSocket / REST
                                   |
                          +--------+---------+
                          |   FastAPI        |
                          |   API Server     |
                          +--------+---------+
                                   |
                 +-----------------+-----------------+
                 |                 |                 |
          +------+------+  +------+------+  +-------+-----+
          | PostgreSQL  |  |    Redis    |  |  ChromaDB   |
          | (messages,  |  | (cache,     |  | (vector     |
          |  users,     |  |  pub/sub,   |  |  embeddings)|
          |  contacts)  |  |  sessions)  |  +-------------+
          +-------------+  +------+------+
                                  |
                           +------+------+
                           |   Celery    |
                           | Worker+Beat |
                           +------+------+
                                  |
                    +-------------+-------------+
                    |             |             |
              Platform Sync  Snooze Check  Score Decay
               (every 2m)    (every 1m)    (every 1h)
```

---

## Tech Stack

| Layer          | Technology                                      |
| -------------- | ----------------------------------------------- |
| **Frontend**   | Next.js 16, React 19, Tailwind CSS, Framer Motion, shadcn/ui |
| **API**        | FastAPI, Pydantic v2, Uvicorn                   |
| **AI**         | Anthropic Claude (via `anthropic` SDK)           |
| **Database**   | PostgreSQL 16 (async via SQLAlchemy 2 + asyncpg) |
| **Cache**      | Redis 7 (caching, pub/sub, session store)       |
| **Vectors**    | ChromaDB (semantic search, message embeddings)  |
| **Task Queue** | Celery 5.4 with Redis broker + beat scheduler   |
| **Auth**       | JWT + AES-256-GCM token encryption at rest      |
| **Infra**      | Docker Compose (6 services), Python 3.12        |

---

## Project Structure

```
vigranth/
|
|-- backend/
|   |-- main.py                  # FastAPI app entry point, lifespan, routers
|   |-- core/
|   |   |-- config.py            # Pydantic settings, all env vars
|   |   |-- database.py          # Async SQLAlchemy engine + session factory
|   |   |-- redis.py             # Redis cache with typed get/set/delete
|   |   |-- celery_app.py        # Celery app + beat schedule config
|   |   |-- security.py          # JWT auth + AES-256-GCM encryption
|   |   |-- pubsub.py            # Redis Pub/Sub bridge (Celery -> WebSocket)
|   |   |-- vector_store.py      # ChromaDB wrapper for embeddings
|   |
|   |-- agents/
|   |   |-- state.py             # Pydantic models (MessageState, API schemas)
|   |   |-- context_builder.py   # Enriches messages with sender history
|   |   |-- classifier.py        # Categorizes: urgent/actionable/fyi/noise
|   |   |-- priority_ranker.py   # Scores 0-100 using 6 weighted signals
|   |   |-- sentiment.py         # Detects tone + emotional intensity
|   |   |-- draft_reply.py       # Generates reply with tone profiles
|   |   |-- summarizer.py        # Thread/conversation summarization
|   |   |-- pipeline.py          # Orchestrator: parallel agents + fallbacks
|   |
|   |-- adapters/
|   |   |-- base.py              # Abstract base adapter interface
|   |   |-- gmail.py             # Gmail API + OAuth2 + Pub/Sub webhooks
|   |   |-- slack.py             # Slack Web API + Events API
|   |   |-- discord.py           # Discord bot + OAuth2
|   |   |-- telegram.py          # Telegram Bot API + webhook updates
|   |   |-- registry.py          # Factory: platform name -> adapter instance
|   |
|   |-- api/
|   |   |-- auth.py              # Register, login, OAuth callbacks
|   |   |-- feed.py              # Ranked priority feed + thread view
|   |   |-- actions.py           # AI draft, send reply, reclassify
|   |   |-- platforms.py         # Connect/disconnect/status per platform
|   |   |-- webhooks.py          # Gmail Pub/Sub, Slack Events, Telegram Bot
|   |   |-- websocket.py         # Live feed via WebSocket connections
|   |
|   |-- models/
|   |   |-- database.py          # SQLAlchemy ORM (users, messages, contacts, credentials, sync_states)
|   |
|   |-- tasks/
|   |   |-- sync.py              # Celery tasks: platform sync, snooze, decay
|   |
|   |-- alembic/                 # Database migrations
|       |-- env.py
|       |-- versions/            # Migration scripts
|
|-- frontend/                    # Next.js 16 + Tailwind + Framer Motion
|   |-- app/
|   |   |-- layout.tsx           # Root layout, metadata, SEO
|   |   |-- page.tsx             # Landing page composition
|   |-- components/
|       |-- navbar.tsx           # UNIFYINBOX brand, nav links
|       |-- hero-section.tsx     # "READ. RANK. REPLY." hero
|       |-- workflow-diagram.tsx # Ingest > Classify > Rank > Draft pipeline
|       |-- feature-grid.tsx     # Feature showcase bento grid
|       |-- about-section.tsx    # Mission + stats
|       |-- pricing-section.tsx  # Free / Pro / Team tiers
|       |-- footer.tsx           # Footer + links
|       |-- glitch-marquee.tsx   # Scrolling platform integrations
|       |-- bento/               # Bento grid cards (terminal, metrics, status, dither)
|
|-- docker-compose.yml           # 6 services: api, worker, beat, postgres, redis, chromadb
|-- Dockerfile                   # Python 3.12-slim
|-- requirements.txt             # Python dependencies
|-- alembic.ini                  # Alembic config
|-- .env.example                 # All required environment variables
|-- .gitignore
|
|-- UnifyInbox_PRD.md            # Product requirements document
|-- UnifyInbox_Architecture.md   # Technical architecture spec
|-- UnifyInbox_Integration_Spec.md  # Integration & agent prompt spec
```

---

## AI Agent Pipeline

Messages flow through a 6-agent pipeline. Context Builder, Classifier, and Sentiment run **in parallel** for speed. Priority Ranker runs after (depends on their outputs). Draft Reply runs on-demand.

```
Message Ingested
       |
       +---> Context Builder --+
       |     (sender history)  |
       |                       |
       +---> Classifier -------+--> Priority Ranker --> Feed
       |     (urgent/fyi/      |    (score 0-100)
       |      actionable/noise)|
       |                       |
       +---> Sentiment --------+
             (tone + intensity)

                         User clicks "Draft Reply"
                                    |
                              Draft Reply Agent
                              (tone-aware response)
```

**All agents have rule-based fallbacks.** If the Claude API is unavailable, classification, scoring, and sentiment analysis continue using keyword and heuristic rules. The system never goes fully offline.

---

## Platform Adapters

Each platform has a dedicated adapter implementing a common interface:

| Platform     | Auth Method          | Ingestion             | Send Support |
| ------------ | -------------------- | --------------------- | ------------ |
| **Gmail**    | OAuth 2.0            | Pub/Sub webhook + poll | Yes (API)   |
| **Slack**    | OAuth 2.0            | Events API webhook    | Yes (API)    |
| **Discord**  | Bot Token + OAuth    | Gateway + webhook     | Yes (API)    |
| **Telegram** | Bot Token            | Bot webhook           | Yes (API)    |

Adapters are loaded via a **registry factory** -- `get_adapter("gmail")` returns the correct implementation.

---

## Priority Scoring

Messages are scored 0--100 using 6 weighted signals defined in the PRD:

| Signal                      | Weight |
| --------------------------- | ------ |
| Sender Relationship         | 30%    |
| Urgency Keywords            | 20%    |
| Time Sensitivity            | 15%    |
| Historical Response Rate    | 15%    |
| Thread Activity             | 10%    |
| Sentiment Intensity         | 10%    |

Scores decay over time via a Celery periodic task (every hour). Users can manually reclassify messages to train the ranker.

---

## API Endpoints

### Auth
| Method | Endpoint                       | Description                |
| ------ | ------------------------------ | -------------------------- |
| POST   | `/auth/register`               | Create account             |
| POST   | `/auth/login`                  | Get JWT token              |
| GET    | `/auth/gmail/callback`         | Gmail OAuth callback       |
| GET    | `/auth/slack/callback`         | Slack OAuth callback       |
| GET    | `/auth/discord/callback`       | Discord OAuth callback     |

### Feed
| Method | Endpoint                       | Description                |
| ------ | ------------------------------ | -------------------------- |
| GET    | `/feed`                        | Ranked priority feed       |
| GET    | `/feed/thread/{thread_id}`     | Thread conversation view   |

### Actions
| Method | Endpoint                       | Description                |
| ------ | ------------------------------ | -------------------------- |
| POST   | `/actions/draft`               | Generate AI draft reply    |
| POST   | `/actions/send`                | Send reply to platform     |
| POST   | `/actions/reclassify`          | Manually reclassify msg    |

### Platforms
| Method | Endpoint                       | Description                |
| ------ | ------------------------------ | -------------------------- |
| GET    | `/platforms/status`            | All connected platforms    |
| POST   | `/platforms/connect`           | Initiate platform OAuth    |
| POST   | `/platforms/disconnect`        | Disconnect a platform      |

### Webhooks
| Method | Endpoint                       | Description                |
| ------ | ------------------------------ | -------------------------- |
| POST   | `/webhooks/gmail`              | Gmail Pub/Sub push         |
| POST   | `/webhooks/slack`              | Slack Events API           |
| POST   | `/webhooks/telegram`           | Telegram bot updates       |

### WebSocket
| Endpoint            | Description                          |
| ------------------- | ------------------------------------ |
| `ws://host/ws`      | Live feed updates (JWT auth on connect) |

---

## Getting Started

### Prerequisites

- **Docker** and **Docker Compose** (for backend)
- **Node.js 20+** and **pnpm** (for frontend)
- API keys: Anthropic, Gmail OAuth, Slack OAuth, Discord Bot, Telegram Bot

### 1. Clone and configure

```bash
git clone <repo-url> && cd vigranth
cp .env.example .env
# Fill in your API keys and secrets in .env
```

### 2. Start backend services

```bash
docker-compose up --build
```

This starts 6 services:

| Service      | Port  | Description                    |
| ------------ | ----- | ------------------------------ |
| `api`        | 8000  | FastAPI server                 |
| `worker`     | --    | Celery task worker             |
| `beat`       | --    | Celery beat scheduler          |
| `postgres`   | 5432  | PostgreSQL 16                  |
| `redis`      | 6379  | Redis 7                        |
| `chromadb`   | 8001  | ChromaDB vector store          |

### 3. Run database migrations

```bash
docker-compose exec api alembic upgrade head
```

### 4. Start frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend runs at `http://localhost:3000`. Backend API at `http://localhost:8000`.

---

## Environment Variables

See `.env.example` for the full list. Key groups:

| Group              | Variables                                            |
| ------------------ | ---------------------------------------------------- |
| **Database**       | `DATABASE_URL`, `DATABASE_URL_SYNC`                  |
| **Redis**          | `REDIS_URL`                                          |
| **ChromaDB**       | `CHROMA_URL`                                         |
| **AI**             | `ANTHROPIC_API_KEY`                                  |
| **JWT**            | `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_HOURS`    |
| **Encryption**     | `ENCRYPTION_KEY` (AES-256 for OAuth tokens at rest)  |
| **Gmail**          | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI` |
| **Slack**          | `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI` |
| **Discord**        | `DISCORD_BOT_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI` |
| **Telegram**       | `TELEGRAM_BOT_TOKEN`                                 |
| **App**            | `FRONTEND_URL`, `WEBHOOK_BASE_URL`, `APP_ENV`, `LOG_LEVEL` |

---

## Docker Services

```yaml
services:
  api        # FastAPI server (port 8000), hot-reload enabled
  worker     # Celery worker (solo pool), processes background tasks
  beat       # Celery beat, schedules periodic tasks
  postgres   # PostgreSQL 16 Alpine, health-checked
  redis      # Redis 7 Alpine, health-checked
  chromadb   # ChromaDB latest, vector embeddings
```

**Celery beat schedule:**

| Task             | Interval | Description                                |
| ---------------- | -------- | ------------------------------------------ |
| `sync_platforms` | 2 min    | Pull new messages from all connected platforms |
| `check_snoozes`  | 1 min    | Resurface snoozed messages when due        |
| `decay_scores`   | 1 hour   | Reduce priority scores on aging messages   |

---

## Frontend

The frontend is a **Next.js 16** app using a brutalist design system:

- **Tailwind CSS** + **shadcn/ui** components
- **Framer Motion** animations
- **JetBrains Mono** + **Geist** fonts
- Orange accent theme (`#ea580c`)

It currently serves as a **marketing/landing page** with product info, pricing tiers, a pipeline visualization, and platform status display. The authenticated dashboard (inbox feed, thread view, settings) is the next build phase.

---

## Pricing Tiers

| Tier     | Price     | Platforms | AI Drafts     | Features                              |
| -------- | --------- | --------- | ------------- | ------------------------------------- |
| **Free** | $0/mo     | 2         | 50/month      | Basic priority feed, email support    |
| **Pro**  | $15/mo    | 7         | Unlimited     | Custom rules, analytics, snooze, API  |
| **Team** | $49/mo    | 7         | Unlimited     | Shared inboxes, RBAC, SSO, SLA       |

---

## Specs & Documentation

The project is built from three specification documents (source of truth):

| Document                          | Contents                                          |
| --------------------------------- | ------------------------------------------------- |
| `UnifyInbox_PRD.md`               | Product requirements, user stories, pricing, scoring weights, notification rules |
| `UnifyInbox_Architecture.md`      | System architecture, agent pipeline, data layer, API spec, Docker config |
| `UnifyInbox_Integration_Spec.md`  | OAuth flows, webhook handlers, agent prompts, frontend spec, error handling |

---

## License

Proprietary. All rights reserved.
