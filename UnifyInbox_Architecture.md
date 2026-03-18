# UnifyInbox — Technical Architecture
**Version:** 1.1 | **Audience:** Engineering | **Date:** March 2026

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
│  Reader Agent → Enrichment Agent → Priority Ranker        │
│                                         │                │
│  Draft Reply Agent ←────────────────────┘                │
└──────┬──────────────────────────────────────┬────────────┘
       │                                      │
┌──────▼──────────────┐        ┌──────────────▼───────────┐
│   MESSAGE QUEUE      │        │       DATA LAYER         │
│   Redis + Celery     │        │  PostgreSQL (messages)   │
│   - Ingestion jobs   │        │  Redis (cache/session)   │
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
| Cache | Redis | Session, rate limits, live feed | Sub-ms latency |
| Frontend | React + TailwindCSS | Web app UI | Rapid development |
| Realtime | WebSockets (FastAPI) | Live feed updates | Built into FastAPI |
| Auth | OAuth2 + JWT | User + platform auth | Industry standard |
| Hosting (MVP) | Railway / Render | Deployment | Zero-config deploy |

---

## 2. Agent Architecture

### 2.1 Agent Overview

UnifyInbox uses a 4-agent pipeline. Agents communicate through a shared `MessageState` Pydantic model.

- **Enrichment Agent** uses `claude-haiku-4-5-20251001` — single call covering context, classification, and sentiment
- **Draft Reply Agent** uses `claude-sonnet-4-6` for reply quality
- **Priority Ranker** and **Reader** are deterministic (no LLM)

| Agent | Model | Role |
|---|---|---|
| Reader Agent | No LLM | Pull raw messages, normalize to unified schema |
| Enrichment Agent | claude-haiku | Sender context + classification + sentiment — one call |
| Priority Ranker Agent | No LLM | Compute 0.0–1.0 score from enrichment outputs (deterministic) |
| Draft Reply Agent | claude-sonnet | Generate platform-toned reply draft (on demand) |

### 2.2 Agent Pipeline Flow

```
New Message (webhook or poll)
        │
        ▼
  Reader Agent
  (normalize → MessageState)
        │
        ▼
  Enrichment Agent  [single claude-haiku call]
  - relationship_type, reply_rate, context_summary
  - label (urgent/action/fyi/social/spam), priority_score
  - sentiment, is_complaint, needs_careful_response
        │
        ▼
  Priority Ranker Agent  [deterministic, no LLM]
  (final priority_score 0-100 from 6 weighted signals)
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

### 2.4 Enrichment Agent

Replaces the former Context Builder, Classifier, and Sentiment agents. Makes **one** claude-haiku call per message and returns all enrichment data in a single structured JSON response.

```python
# agents/enrich.py
SYSTEM_PROMPT = """
You are a message enrichment agent. Analyze a message and its sender context.
Respond with valid JSON only. No preamble.
"""

USER_PROMPT = """
SENDER: {sender_name} ({sender_identifier}) on {platform}
EMAIL: {sender_email}
PAST INTERACTIONS ({total_messages} total, {reply_count} replied):
{interaction_history}

MESSAGE:
{message_text}

Return JSON with ALL of these fields:
{
  "relationship_type": "vip|close_contact|work_contact|acquaintance|stranger|bot|newsletter",
  "reply_rate": 0.0,
  "context_summary": "one sentence who this person is",
  "is_likely_important": true,
  "label": "urgent|action|fyi|social|spam",
  "priority_score": 0.0,
  "time_sensitive": false,
  "reasoning": "one sentence on priority",
  "sentiment": "positive|neutral|tense|urgent|distressed",
  "is_complaint": false,
  "needs_careful_response": false,
  "suggested_approach": "one sentence on how to reply"
}
"""

async def enrich_message(state, interaction_history, reply_count, total_messages) -> MessageState:
    # Single API call → all enrichment fields populated on state
    ...
```

**Fallback:** If the API call fails, a combined rule-based function handles relationship classification, urgency scoring, and sentiment detection using keyword matching. The system never goes offline.

### 2.5 Draft Reply Agent

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

### 2.6 Agent Pipeline Orchestrator

```python
# agents/pipeline.py
async def run_pipeline(state: MessageState, db, ws_manager=None) -> MessageState:
    """
    Runs the full agent pipeline for a single message.
    """
    # Step 1: Fetch sender history from DB
    interaction_history, reply_count, total_messages = await _get_sender_stats(db, ...)

    # Step 2: Single enrichment call (context + classification + sentiment)
    state = await enrich_message(state, interaction_history, reply_count, total_messages)

    # Step 3: Deterministic priority scoring
    state = await compute_priority(state, thread_message_count, thread_recent_replies)

    # Step 4: Persist to PostgreSQL
    await _upsert_message(db, state)
    await _upsert_contact(db, state)

    # Step 5: Push to WebSocket clients
    if ws_manager:
        await ws_manager.push_to_user(state.user_id, "new_message", state.model_dump())

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

### 4.2 Redis Caching Strategy

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

volumes:
  pg_data:
```

### 6.2 Environment Variables

```bash
# .env
DATABASE_URL=postgresql://app:secret@postgres:5432/unifyinbox
REDIS_URL=redis://redis:6379/0
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
│   │   └── security.py            # JWT + token encryption
│   ├── agents/
│   │   ├── state.py               # Pydantic MessageState model
│   │   ├── pipeline.py            # Orchestrates agent pipeline
│   │   ├── enrich.py              # Unified enrichment (context + classification + sentiment)
│   │   ├── priority_ranker.py     # Deterministic scoring
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
