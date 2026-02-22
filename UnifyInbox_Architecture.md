# UnifyInbox — Technical Architecture
**Version:** 1.0 | **Audience:** Engineering | **Date:** February 2026

---

## 1. System Architecture Overview

UnifyInbox is a multi-layer platform:
- **Ingestion Layer** — connects to communication platforms via APIs/webhooks
- **Agent Layer** — Claude-powered pipeline that classifies, ranks, and enriches messages
- **Delivery Layer** — serves unified UI and enables in-app send actions

### 1.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      CLIENT LAYER                        │
│          React Web App           Mobile App (v2)         │
└───────────────────────┬──────────────────────────────────┘
                        │ HTTPS / WebSocket
┌───────────────────────▼──────────────────────────────────┐
│                     API GATEWAY                          │
│            FastAPI  |  Auth  |  Rate Limiting            │
└───┬──────────┬──────────┬──────────┬──────────┬──────────┘
    │          │          │          │          │
 Feed API  Thread API  Action API  Draft API  WebSocket
    └──────────┴──────────┴──────────┴──────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│                    AGENT LAYER (Python)                   │
│                                                          │
│  Reader Agent → Context Builder → Classifier Agent       │
│                                         │                │
│  Draft Reply Agent ← Sentiment Agent ← Priority Ranker   │
└──────┬──────────────────────────────────────┬────────────┘
       │                                      │
┌──────▼──────────────┐        ┌──────────────▼───────────┐
│   MESSAGE QUEUE      │        │       DATA LAYER         │
│   Redis + Celery     │        │  PostgreSQL (messages)   │
│   - Ingestion jobs   │        │  ChromaDB (embeddings)   │
│   - Priority recalc  │        │  Redis (cache/session)   │
│   - Scheduled sends  │        └──────────────────────────┘
└──────┬──────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│                  PLATFORM ADAPTER LAYER                  │
│   Gmail API   Slack API   Telegram API   Discord API     │
│   (OAuth2)    (OAuth2)    (Bot Token)    (Bot Token)     │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Technology Stack

| Layer | Technology | Purpose | Rationale |
|---|---|---|---|
| Backend API | Python + FastAPI | REST + WebSocket API | Async, fast, great DX |
| Agent Runtime | Python + asyncio | Parallel agent execution | Native async, clean coroutines |
| AI Models | Claude API (Anthropic) | Classification, drafting, summarization | Best reasoning + instruction following |
| Message Queue | Redis + Celery | Background jobs & scheduling | Battle-tested, simple |
| Primary DB | PostgreSQL | Messages, users, contacts | Relational + JSONB for flexibility |
| Vector DB | ChromaDB | Message embeddings for context | Open source, easy self-host |
| Cache | Redis | Session, rate limits, live feed | Sub-ms latency |
| Frontend | React + TailwindCSS | Web app UI | Rapid development |
| Realtime | WebSockets (FastAPI) | Live feed updates | Built into FastAPI |
| Auth | OAuth2 + JWT | User + platform auth | Industry standard |
| Hosting (MVP) | Railway / Render | Deployment | Zero-config deploy |

---

## 2. Agent Architecture

### 2.1 Agent Overview

UnifyInbox uses a pipeline of 6 specialized AI agents. Each agent has a single responsibility. Agents communicate through a shared `MessageState` Pydantic model.

- **Heavy agents** use `claude-sonnet-4-6` for quality
- **Lightweight agents** use `claude-haiku-4-5-20251001` for speed + cost

| Agent | Model | Role |
|---|---|---|
| Reader Agent | No LLM (deterministic) | Pull raw messages, normalize to unified schema |
| Context Builder Agent | claude-haiku | Enrich sender: relationship type, history, VIP status |
| Classifier Agent | claude-haiku | Tag: urgent / action / fyi / social / spam |
| Priority Ranker Agent | claude-haiku | Compute 0.0–1.0 score, rank the feed |
| Sentiment Agent | claude-haiku | Detect tone: positive / neutral / tense / urgent / distressed |
| Draft Reply Agent | claude-sonnet | Generate platform-toned reply draft |

### 2.2 Agent Pipeline Flow

```
New Message (webhook or poll)
        │
        ▼
  Reader Agent
  (normalize → MessageState)
        │
        ├─────────────────────────── asyncio.gather() ──────────────────────┐
        │                            (runs in parallel)                     │
        ▼                                  ▼                                ▼
Context Builder Agent           Classifier Agent                 Sentiment Agent
(sender relationship)           (label + score)                  (tone detection)
        │                                  │                                │
        └──────────────────────────────────┴────────────────────────────────┘
                                           │
                                    MessageState enriched
                                           │
                                           ▼
                                Priority Ranker Agent
                                (final priority_score)
                                           │
                                           ▼
                              Save to PostgreSQL + push via WebSocket
                                           │
                                           ▼  (on user "Draft Reply" click)
                                  Draft Reply Agent
                              (claude-sonnet, platform tone)
                                           │
                                           ▼
                               User edits → Send API → Platform
```

### 2.3 Shared State Schema

```python
# agents/state.py
from pydantic import BaseModel
from typing import Optional
from enum import Enum

class Platform(str, Enum):
    GMAIL = "gmail"
    SLACK = "slack"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"

class SenderContext(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    username: Optional[str] = None
    relationship: str = "stranger"   # vip | contact | team | stranger | bot
    is_vip: bool = False
    historical_reply_rate: float = 0.0
    last_interaction_days: Optional[int] = None

class AIEnrichment(BaseModel):
    priority_score: float = 0.0
    priority_label: str = "fyi"      # urgent | action | fyi | social | spam
    sentiment: str = "neutral"       # positive | neutral | tense | urgent | distressed
    summary: str = ""
    context_note: str = ""           # shown in UI as "why this priority"
    suggested_actions: list[str] = []

class MessageState(BaseModel):
    id: str
    platform: Platform
    platform_message_id: str
    thread_id: str
    sender: SenderContext
    content_text: str
    timestamp: str
    is_read: bool = False
    is_done: bool = False
    snoozed_until: Optional[str] = None
    ai_enrichment: AIEnrichment = AIEnrichment()
    draft_reply: Optional[str] = None
```

### 2.4 Context Builder Agent

```python
# agents/context_builder.py
import anthropic
import json

client = anthropic.Anthropic()

CONTEXT_PROMPT = """
Given this message sender info and conversation history, determine:
1. relationship_type: vip | close_contact | work_contact | acquaintance | stranger | bot | newsletter
2. estimated_reply_rate: float 0.0-1.0
3. context_summary: one sentence about who this person is

Sender: {sender_raw}
Past interactions (last 20): {history}
Times user replied: {reply_count} out of {total_messages}
Last interaction: {last_interaction_days} days ago

Respond in JSON only. No preamble.
{{
  "relationship_type": "...",
  "reply_rate": 0.0,
  "context_summary": "..."
}}
"""

async def build_context(state: MessageState, db) -> MessageState:
    history = await db.get_sender_history(state.sender.id, state.platform, limit=20)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": CONTEXT_PROMPT.format(
                sender_raw=state.sender.model_dump_json(),
                history=history,
                reply_count=history.get("reply_count", 0),
                total_messages=history.get("total", 0),
                last_interaction_days=state.sender.last_interaction_days or "unknown"
            )
        }]
    )

    result = json.loads(response.content[0].text)
    state.sender.relationship = result["relationship_type"]
    state.sender.historical_reply_rate = result["reply_rate"]
    state.ai_enrichment.context_note = result["context_summary"]
    return state
```

### 2.5 Classifier + Priority Ranker Agent

```python
# agents/classifier.py
CLASSIFY_PROMPT = """
Classify this message. Return JSON only.

Sender relationship: {relationship} (vip > contact > team > stranger > bot)
Historical reply rate: {reply_rate}
Message: {content}
Platform: {platform}

Classification labels:
- urgent: Requires response within hours, time-sensitive
- action: Requires response but not immediately critical
- fyi: Informational, no response needed
- social: Casual/social, low professional priority
- spam: Unsolicited, promotional, low value

Priority score guidance:
- 0.9-1.0: Urgent from VIP (investor, boss, client emergency)
- 0.7-0.89: Action needed from known contact
- 0.5-0.69: Action from stranger OR fyi from VIP
- 0.3-0.49: Social from known contact
- 0.0-0.29: Newsletter, bot, low-value

Return:
{{
  "label": "urgent|action|fyi|social|spam",
  "priority_score": 0.0,
  "time_sensitive": true,
  "reasoning": "one sentence"
}}
"""

async def classify_and_rank(state: MessageState) -> MessageState:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": CLASSIFY_PROMPT.format(
                relationship=state.sender.relationship,
                reply_rate=state.sender.historical_reply_rate,
                content=state.content_text,
                platform=state.platform.value
            )
        }]
    )

    result = json.loads(response.content[0].text)
    state.ai_enrichment.priority_label = result["label"]
    state.ai_enrichment.priority_score = result["priority_score"]
    state.ai_enrichment.context_note += f" | {result['reasoning']}"
    return state
```

### 2.6 Draft Reply Agent

```python
# agents/draft_reply.py
TONE_PROFILES = {
    "gmail": "Professional email. Full sentences, proper greeting with their name, formal sign-off. Max 150 words.",
    "slack": "Slack message. No greeting. Under 3 sentences. Conversational but professional. Emoji ok if appropriate.",
    "telegram": "Telegram. Short and direct. Warm if known, neutral if stranger. 1-3 sentences max.",
    "discord": "Discord. Casual community tone. 1-2 sentences. Use @{sender} if channel reply.",
    "whatsapp": "WhatsApp. Personal and warm. Short sentences. Natural spoken language. 1-3 sentences.",
}

DRAFT_PROMPT = """
Draft a reply on behalf of the user. Return ONLY the reply text, nothing else.
Never start with "Certainly!" or "Of course!" — sound human.

Platform: {platform}
Tone: {tone}
Sender: {sender_name} ({relationship})
Sentiment of their message: {sentiment}
{careful_note}

Thread history (newest last):
{thread_history}

Message to reply to:
{message}
"""

async def draft_reply(state: MessageState, thread_context: list[str]) -> str:
    careful_note = ""
    if state.ai_enrichment.sentiment in ["tense", "distressed"]:
        careful_note = "NOTE: This message has a tense/distressed tone. Be empathetic and careful."

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": DRAFT_PROMPT.format(
                platform=state.platform.value,
                tone=TONE_PROFILES[state.platform.value],
                sender_name=state.sender.name,
                relationship=state.sender.relationship,
                sentiment=state.ai_enrichment.sentiment,
                careful_note=careful_note,
                thread_history="\n".join(thread_context[-5:]),
                message=state.content_text
            )
        }]
    )
    return response.content[0].text.strip()
```

### 2.7 Agent Pipeline Orchestrator

```python
# agents/pipeline.py
import asyncio

async def run_pipeline(state: MessageState, db) -> MessageState:
    """
    Runs the full agent pipeline for a single message.
    Context, Classifier, and Sentiment run in parallel.
    """
    # Step 1: Run enrichment agents in parallel
    state, _, _ = await asyncio.gather(
        build_context(state, db),
        classify_and_rank(state),
        detect_sentiment(state)
    )

    # Step 2: Save to database
    await db.upsert_message(state)

    # Step 3: Push to connected WebSocket clients
    await ws_manager.push_to_user(state.sender.id, "new_message", state.dict())

    return state
```

---

## 3. Platform Adapter Layer

### 3.1 Adapter Interface

```python
# adapters/base.py
from abc import ABC, abstractmethod

class PlatformAdapter(ABC):

    @abstractmethod
    async def fetch_new_messages(self, user_id: str, since: datetime) -> list[dict]:
        """Fetch raw messages from platform API"""
        pass

    @abstractmethod
    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert platform-specific message to MessageState"""
        pass

    @abstractmethod
    async def send_message(self, thread_id: str, text: str, credentials: dict) -> bool:
        """Send reply through the platform's API"""
        pass

    @abstractmethod
    async def setup_webhook(self, user_id: str, webhook_url: str) -> bool:
        """Register webhook for realtime delivery"""
        pass
```

### 3.2 Gmail Adapter

```python
# adapters/gmail.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GmailAdapter(PlatformAdapter):

    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

    async def fetch_new_messages(self, user_id: str, since: datetime) -> list[dict]:
        creds = await self._get_credentials(user_id)
        service = build('gmail', 'v1', credentials=creds)

        query = f"after:{int(since.timestamp())} in:inbox"
        results = service.users().messages().list(userId='me', q=query).execute()

        messages = []
        for ref in results.get('messages', []):
            msg = service.users().messages().get(
                userId='me', id=ref['id'], format='full'
            ).execute()
            messages.append(msg)
        return messages

    def normalize(self, raw: dict, user_id: str) -> MessageState:
        headers = {h['name']: h['value'] for h in raw['payload']['headers']}
        body = self._extract_body(raw['payload'])

        return MessageState(
            id=str(uuid4()),
            platform=Platform.GMAIL,
            platform_message_id=raw['id'],
            thread_id=raw['threadId'],
            sender=SenderContext(
                id=headers.get('From', ''),
                name=self._parse_name(headers.get('From', '')),
                email=self._parse_email(headers.get('From', ''))
            ),
            content_text=body,
            timestamp=headers.get('Date', '')
        )

    async def send_message(self, thread_id: str, text: str, credentials: dict) -> bool:
        creds = Credentials(**credentials)
        service = build('gmail', 'v1', credentials=creds)
        # Build MIMEText, encode as base64, send via messages().send()
        ...
        return True
```

### 3.3 Slack Adapter

```python
# adapters/slack.py
from slack_sdk.web.async_client import AsyncWebClient

class SlackAdapter(PlatformAdapter):

    async def fetch_new_messages(self, user_id: str, since: datetime) -> list[dict]:
        token = await self._get_token(user_id)
        client = AsyncWebClient(token=token)

        conversations = await client.conversations_list(types="im,mpim")
        messages = []

        for channel in conversations['channels']:
            history = await client.conversations_history(
                channel=channel['id'],
                oldest=str(since.timestamp()),
                limit=50
            )
            for msg in history['messages']:
                msg['channel_id'] = channel['id']
                messages.append(msg)

        return messages

    def normalize(self, raw: dict, user_id: str) -> MessageState:
        return MessageState(
            id=str(uuid4()),
            platform=Platform.SLACK,
            platform_message_id=raw['ts'],
            thread_id=raw.get('thread_ts', raw['ts']),
            sender=SenderContext(id=raw['user'], name=raw.get('username', raw['user'])),
            content_text=raw.get('text', ''),
            timestamp=raw['ts']
        )
```

### 3.4 Platform API Comparison

| Platform | Auth | Realtime | Rate Limit |
|---|---|---|---|
| Gmail | OAuth2 (Google) | Push Notifications (Pub/Sub) | 250 quota units/user/sec |
| Slack | OAuth2 (Slack) | Events API (webhooks) | Tier 1: 1/sec |
| Telegram | Bot Token | Webhooks / Long polling | 30 msg/sec |
| Discord | Bot Token + OAuth2 | WebSocket Gateway | 50 req/sec |
| WhatsApp | Meta OAuth2 | Webhooks | 80 msg/sec |

---

## 4. Data Architecture

### 4.1 PostgreSQL Schema

```sql
-- Users and credentials
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    settings    JSONB DEFAULT '{}'
);

CREATE TABLE platform_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    access_token    TEXT NOT NULL,  -- AES-256 encrypted at rest
    refresh_token   TEXT,
    token_expiry    TIMESTAMPTZ,
    platform_user_id TEXT,
    UNIQUE(user_id, platform)
);

-- Normalized messages
CREATE TABLE messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    platform            TEXT NOT NULL,
    platform_message_id TEXT NOT NULL,
    thread_id           TEXT,
    sender_id           TEXT NOT NULL,
    sender_name         TEXT,
    sender_email        TEXT,
    content_text        TEXT,
    timestamp           TIMESTAMPTZ NOT NULL,
    is_read             BOOLEAN DEFAULT FALSE,
    is_done             BOOLEAN DEFAULT FALSE,
    snoozed_until       TIMESTAMPTZ,
    priority_score      FLOAT DEFAULT 0.0,
    priority_label      TEXT DEFAULT 'fyi',
    sentiment           TEXT DEFAULT 'neutral',
    ai_context_note     TEXT,
    summary             TEXT,
    draft_reply         TEXT,
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, platform, platform_message_id)
);

-- Indexes
CREATE INDEX idx_messages_feed ON messages(user_id, priority_score DESC, timestamp DESC);
CREATE INDEX idx_messages_platform ON messages(user_id, platform);
CREATE INDEX idx_messages_thread ON messages(thread_id);
CREATE INDEX idx_messages_snooze ON messages(snoozed_until) WHERE snoozed_until IS NOT NULL;

-- Contact relationship graph
CREATE TABLE contacts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    contact_identifier  TEXT NOT NULL,
    platform            TEXT NOT NULL,
    display_name        TEXT,
    relationship        TEXT DEFAULT 'stranger',
    is_vip              BOOLEAN DEFAULT FALSE,
    reply_rate          FLOAT DEFAULT 0.0,
    message_count       INT DEFAULT 0,
    last_interaction    TIMESTAMPTZ,
    UNIQUE(user_id, platform, contact_identifier)
);
```

### 4.2 ChromaDB (Vector Store)

```python
# core/vector_store.py
import chromadb

chroma = chromadb.Client()
collection = chroma.get_or_create_collection("message_history")

async def embed_message(state: MessageState):
    collection.add(
        documents=[state.content_text],
        metadatas=[{
            "user_id": state.sender.id,
            "platform": state.platform.value,
            "timestamp": state.timestamp,
            "sender_id": state.sender.id
        }],
        ids=[state.id]
    )

async def get_similar_messages(query: str, user_id: str, n=10) -> list[str]:
    results = collection.query(
        query_texts=[query],
        n_results=n,
        where={"user_id": user_id}
    )
    return results['documents'][0]
```

### 4.3 Redis Caching Strategy

| Cache Key | TTL | Contents |
|---|---|---|
| `feed:{user_id}` | 30 seconds | Ranked priority feed (50 items) |
| `contact:{user_id}:{platform}:{id}` | 1 hour | Sender context + relationship |
| `thread:{platform}:{thread_id}` | 5 minutes | Full thread messages |
| `session:{token}` | 24 hours | User session data |
| `platform_token:{user_id}:{platform}` | Until expiry | OAuth access tokens |

---

## 5. API Specification

### 5.1 Authentication

```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

JWT tokens expire in 24 hours. Refresh tokens rotate on use.

### 5.2 Feed Endpoints

```
GET /api/v1/feed
  ?limit=50&offset=0&platform=gmail&priority=urgent
  → { messages: [MessageState], total: int, has_more: bool }

GET /api/v1/thread/{platform}/{thread_id}
  → { messages: [MessageState], summary: str }

PATCH /api/v1/message/{message_id}
  body: { is_done: bool, snoozed_until: datetime, is_read: bool }
  → { success: bool }
```

### 5.3 AI Action Endpoints

```
POST /api/v1/draft/{message_id}
  → { draft: str, tone_used: str }

PUT /api/v1/draft/{message_id}
  body: { edited_draft: str }
  → { success: bool }

POST /api/v1/send/{message_id}
  body: { text: str }
  → { success: bool, platform_message_id: str }

POST /api/v1/message/{message_id}/reclassify
  body: { correct_label: str }   # user feedback to improve model
  → { success: bool }
```

### 5.4 Platform Management

```
GET /api/v1/platforms
  → [{ platform: str, connected: bool, last_sync: datetime }]

POST /api/v1/platforms/{platform}/connect
  body: { auth_code: str }       # from OAuth2 callback
  → { success: bool, platform_user_id: str }

DELETE /api/v1/platforms/{platform}
  → { success: bool }
```

### 5.5 WebSocket — Live Feed

```
WS /ws/feed?token={jwt_token}

# Server → Client
{ "event": "new_message",      "data": MessageState }
{ "event": "priority_updated", "data": { message_id, new_score, new_label } }
{ "event": "sync_status",      "data": { platform, status: "syncing|done|error" } }

# Client → Server
{ "event": "mark_read",  "message_id": str }
{ "event": "snooze",     "message_id": str, "until": datetime }
```

---

## 6. Infrastructure

### 6.1 Docker Compose (Development)

```yaml
# docker-compose.yml
version: '3.9'
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    volumes: [".:/app"]
    depends_on: [postgres, redis]
    command: uvicorn main:app --reload --host 0.0.0.0

  worker:
    build: .
    env_file: .env
    depends_on: [redis, postgres]
    command: celery -A core.celery worker --loglevel=info

  beat:
    build: .
    env_file: .env
    depends_on: [redis]
    command: celery -A core.celery beat --loglevel=info

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: unifyinbox
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    volumes: [pg_data:/var/lib/postgresql/data]
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  chromadb:
    image: chromadb/chroma:latest
    ports: ["8001:8000"]

volumes:
  pg_data:
```

### 6.2 Environment Variables

```bash
# .env
DATABASE_URL=postgresql://app:secret@postgres:5432/unifyinbox
REDIS_URL=redis://redis:6379/0
CHROMA_URL=http://chromadb:8000
ANTHROPIC_API_KEY=sk-ant-...

# Gmail
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...

# Slack
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...

# Telegram
TELEGRAM_BOT_TOKEN=...

# Discord
DISCORD_BOT_TOKEN=...
DISCORD_CLIENT_ID=...
DISCORD_CLIENT_SECRET=...

# App
JWT_SECRET=your-secret-here
JWT_EXPIRY_HOURS=24
FRONTEND_URL=http://localhost:3000
WEBHOOK_BASE_URL=https://your-domain.com
```

### 6.3 Celery Background Jobs

```python
# core/tasks.py
from celery import Celery

celery = Celery('unifyinbox', broker=REDIS_URL, backend=REDIS_URL)

@celery.task
async def sync_platform_messages(user_id: str, platform: str):
    adapter = get_adapter(platform)
    since = await get_last_sync_time(user_id, platform)
    raw_messages = await adapter.fetch_new_messages(user_id, since)
    for raw in raw_messages:
        state = adapter.normalize(raw, user_id)
        await run_pipeline(state, db)

@celery.task
async def check_snoozed_messages():
    expired = await db.get_expired_snoozed(datetime.utcnow())
    for msg in expired:
        await db.unsnooze(msg.id)
        await ws_manager.push_to_user(msg.user_id, "new_message", msg)

# Celery Beat Schedule
celery.conf.beat_schedule = {
    'sync-all-platforms': {
        'task': 'core.tasks.sync_all_users',
        'schedule': 120.0,          # every 2 minutes
    },
    'check-snoozed': {
        'task': 'core.tasks.check_snoozed_messages',
        'schedule': 60.0,           # every minute
    },
    'decay-scores': {
        'task': 'core.tasks.recalculate_priority_scores',
        'schedule': 3600.0,         # every hour
    },
}
```

### 6.4 Security

- OAuth tokens encrypted at rest with AES-256 before DB storage
- Message content never stored in plaintext longer than needed for processing
- JWT tokens expire in 24 hours; refresh tokens rotate on use
- All API endpoints rate-limited: 100 req/min standard, 10 req/min for AI actions
- WebSocket connections validated on upgrade with JWT
- Platform webhooks validated with HMAC signatures
- CORS configured to accept only known frontend domains

---

## 7. Project Structure

```
unifyinbox/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── core/
│   │   ├── config.py              # settings + env vars
│   │   ├── database.py            # SQLAlchemy async engine
│   │   ├── redis.py               # Redis connection pool
│   │   ├── celery.py              # Celery app + beat schedule
│   │   ├── vector_store.py        # ChromaDB wrapper
│   │   └── security.py            # JWT + token encryption
│   ├── agents/
│   │   ├── state.py               # Pydantic MessageState model
│   │   ├── pipeline.py            # Orchestrates agent pipeline
│   │   ├── context_builder.py
│   │   ├── classifier.py
│   │   ├── priority_ranker.py
│   │   ├── sentiment.py
│   │   └── draft_reply.py
│   ├── adapters/
│   │   ├── base.py                # Abstract adapter interface
│   │   ├── gmail.py
│   │   ├── slack.py
│   │   ├── telegram.py
│   │   └── discord.py
│   ├── api/
│   │   ├── auth.py                # Login + OAuth callbacks
│   │   ├── feed.py                # Feed + message endpoints
│   │   ├── actions.py             # Draft, send, snooze
│   │   ├── platforms.py           # Connect/disconnect platforms
│   │   └── websocket.py           # WS live feed
│   ├── models/
│   │   └── database.py            # SQLAlchemy ORM models
│   └── tasks/
│       └── sync.py                # Celery background tasks
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Feed.tsx
│       │   ├── MessageCard.tsx
│       │   ├── ThreadView.tsx
│       │   └── ReplyComposer.tsx
│       ├── hooks/
│       │   ├── useFeed.ts
│       │   └── useDraft.ts
│       └── pages/
│           ├── App.tsx
│           └── Connect.tsx
│
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
