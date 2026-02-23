# UnifyInbox — Setup Requirements

Everything you need to get the full stack running locally.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Frontend (no keys needed)](#frontend-no-keys-needed)
- [Backend Services (Docker)](#backend-services-docker)
- [API Keys & Credentials](#api-keys--credentials)
  - [1. Anthropic (Claude AI)](#1-anthropic-claude-ai)
  - [2. Gmail OAuth2 (Google Cloud)](#2-gmail-oauth2-google-cloud)
  - [3. Slack OAuth2](#3-slack-oauth2)
  - [4. Discord Bot + OAuth2](#4-discord-bot--oauth2)
  - [5. Telegram Bot](#5-telegram-bot)
- [Security Secrets (self-generated)](#security-secrets-self-generated)
- [Webhook Setup (for production)](#webhook-setup-for-production)
- [Complete .env Reference](#complete-env-reference)
- [Testing Checklist](#testing-checklist)
- [Common Issues](#common-issues)

---

## Prerequisites

Install these before anything else:

| Tool             | Version | What it's for           | Install                                   |
| ---------------- | ------- | ----------------------- | ----------------------------------------- |
| **Docker**       | 24+     | Backend services        | https://docs.docker.com/get-docker/       |
| **Docker Compose** | v2+   | Orchestrates 6 services | Included with Docker Desktop              |
| **Node.js**      | 20+     | Frontend runtime        | https://nodejs.org/                       |
| **pnpm**         | 9+      | Frontend package manager| `npm install -g pnpm`                     |
| **Git**          | 2.40+   | Version control         | https://git-scm.com/                      |

Optional (for running backend without Docker):

| Tool             | Version | Install                                     |
| ---------------- | ------- | ------------------------------------------- |
| **Python**       | 3.12+   | https://www.python.org/downloads/           |
| **PostgreSQL**   | 16+     | https://www.postgresql.org/download/        |
| **Redis**        | 7+      | https://redis.io/download                   |

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> && cd vigranth

# 2. Create .env from template
cp .env.example .env
# Fill in API keys (see sections below)

# 3. Start backend (6 Docker containers)
docker-compose up --build -d

# 4. Run database migrations
docker-compose exec api alembic upgrade head

# 5. Start frontend
cd frontend
pnpm install
pnpm dev
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs (Swagger UI)

---

## Frontend (no keys needed)

The frontend runs entirely on mock data. No API keys or backend required to test the UI.

```bash
cd frontend
pnpm install
pnpm dev
```

This gives you the full flow:
1. Landing page (`/`)
2. Auth screen (`/auth`) — mock auth, no real Google OAuth
3. Platform onboarding (`/onboarding`) — simulates OAuth connections
4. Sync animation (`/sync`)
5. Dashboard (`/dashboard`) — 19 mock messages, thread views, AI draft simulation
6. Settings (`/dashboard/settings`)

**To test the frontend, you need nothing else.** Everything below is for the backend.

---

## Backend Services (Docker)

`docker-compose up --build` starts these 6 services:

| Service      | Image / Build    | Port  | Purpose                                    |
| ------------ | ---------------- | ----- | ------------------------------------------ |
| `api`        | Dockerfile       | 8000  | FastAPI server (all API routes + WebSocket) |
| `worker`     | Dockerfile       | --    | Celery worker (background task processing)  |
| `beat`       | Dockerfile       | --    | Celery beat (periodic task scheduler)       |
| `postgres`   | postgres:16-alpine | 5432 | Primary database                           |
| `redis`      | redis:7-alpine   | 6379  | Cache, Pub/Sub, Celery broker              |
| `chromadb`   | chromadb/chroma  | 8001  | Vector store for message embeddings        |

PostgreSQL, Redis, and ChromaDB require **zero configuration** — Docker handles everything. The credentials in `.env.example` already match the Docker Compose defaults.

---

## API Keys & Credentials

You need credentials from **5 external services**. Here's exactly how to get each one.

---

### 1. Anthropic (Claude AI)

**What it's for:** AI classification, priority scoring, sentiment analysis, draft replies.
**Required:** Yes — core functionality. Without it, agents fall back to rule-based heuristics.

| Variable           | Value                    |
| ------------------ | ------------------------ |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...`      |

**How to get it:**

1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Go to **API Keys** in the left sidebar
4. Click **Create Key**
5. Copy the key — starts with `sk-ant-`
6. Paste into `.env` as `ANTHROPIC_API_KEY`

**Pricing:** Pay-per-use. Claude Haiku is ~$0.25/million input tokens. For testing, expect < $1 total.

---

### 2. Gmail OAuth2 (Google Cloud)

**What it's for:** Reading Gmail emails, sending replies via Gmail API.
**Required:** Only if you want to connect Gmail.

| Variable              | Value                                              |
| --------------------- | -------------------------------------------------- |
| `GMAIL_CLIENT_ID`     | `123456789-abc.apps.googleusercontent.com`         |
| `GMAIL_CLIENT_SECRET` | `GOCSPX-...`                                       |
| `GMAIL_REDIRECT_URI`  | `http://localhost:8000/auth/gmail/callback`         |

**How to get it:**

1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable these APIs:
   - **Gmail API** — search "Gmail API" in the API Library and click Enable
   - **Google People API** — for contact info (optional)
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID**
6. Application type: **Web application**
7. Name: `UnifyInbox Dev`
8. Authorized redirect URIs: add `http://localhost:8000/auth/gmail/callback`
9. Click Create — copy Client ID and Client Secret
10. Go to **APIs & Services > OAuth consent screen**
11. Set User Type to **External** (for testing)
12. Fill in app name, support email
13. Add scopes:
    - `https://www.googleapis.com/auth/gmail.readonly`
    - `https://www.googleapis.com/auth/gmail.send`
    - `https://www.googleapis.com/auth/gmail.modify`
14. Add your own email as a **test user** (required while in "Testing" mode)
15. Paste credentials into `.env`

**Note:** While the OAuth consent screen is in "Testing" mode, only emails you add as test users can authenticate. Publish the app to remove this restriction.

---

### 3. Slack OAuth2

**What it's for:** Reading Slack DMs, channel messages, mentions. Sending replies.
**Required:** Only if you want to connect Slack.

| Variable              | Value                                          |
| --------------------- | ---------------------------------------------- |
| `SLACK_CLIENT_ID`     | `123456789.987654321`                          |
| `SLACK_CLIENT_SECRET` | `abcdef1234567890`                             |
| `SLACK_REDIRECT_URI`  | `http://localhost:8000/auth/slack/callback`     |

**How to get it:**

1. Go to https://api.slack.com/apps
2. Click **Create New App > From scratch**
3. App Name: `UnifyInbox Dev`, pick your workspace
4. Go to **OAuth & Permissions**
5. Add these **Bot Token Scopes**:
   - `channels:history` — read channel messages
   - `channels:read` — list channels
   - `chat:write` — send messages
   - `im:history` — read DMs
   - `im:read` — list DMs
   - `users:read` — user info
   - `users:read.email` — user emails
6. Add Redirect URL: `http://localhost:8000/auth/slack/callback`
7. Go to **Basic Information** — copy Client ID and Client Secret
8. Go to **Event Subscriptions**:
   - Enable events
   - Request URL: `https://your-domain.com/webhooks/slack` (needs public URL — see [Webhook Setup](#webhook-setup-for-production))
   - Subscribe to bot events: `message.channels`, `message.im`
9. Install app to your workspace
10. Paste credentials into `.env`

**For local testing without webhooks:** The app will use polling (Celery sync every 2 min) to fetch messages. Webhooks are only needed for real-time.

---

### 4. Discord Bot + OAuth2

**What it's for:** Reading Discord server messages, DMs. Sending replies.
**Required:** Only if you want to connect Discord.

| Variable                | Value                                            |
| ----------------------- | ------------------------------------------------ |
| `DISCORD_BOT_TOKEN`     | `MTIzNDU2Nzg5...` (long token)                  |
| `DISCORD_CLIENT_ID`     | `123456789012345678`                             |
| `DISCORD_CLIENT_SECRET` | `abcdefghijklmnop`                               |
| `DISCORD_REDIRECT_URI`  | `http://localhost:8000/auth/discord/callback`     |

**How to get it:**

1. Go to https://discord.com/developers/applications
2. Click **New Application**, name it `UnifyInbox Dev`
3. Go to **Bot** tab:
   - Click **Add Bot**
   - Enable **Message Content Intent** (under Privileged Gateway Intents)
   - Copy the **Bot Token**
4. Go to **OAuth2** tab:
   - Copy **Client ID** and **Client Secret**
   - Add Redirect: `http://localhost:8000/auth/discord/callback`
5. Go to **OAuth2 > URL Generator**:
   - Select scopes: `bot`, `identify`, `guilds`
   - Select bot permissions: `Read Messages/View Channels`, `Send Messages`, `Read Message History`
   - Copy the generated URL and open it to invite the bot to your test server
6. Paste credentials into `.env`

---

### 5. Telegram Bot

**What it's for:** Reading Telegram messages forwarded to the bot. Sending replies.
**Required:** Only if you want to connect Telegram.

| Variable              | Value                          |
| --------------------- | ------------------------------ |
| `TELEGRAM_BOT_TOKEN`  | `7123456789:AAF...` (BotFather token) |

**How to get it:**

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name: `UnifyInbox Dev`
4. Choose a username: `unifyinbox_dev_bot` (must end in `bot`)
5. BotFather gives you a token — copy it
6. Optionally send `/setdescription` to describe the bot
7. Paste the token into `.env` as `TELEGRAM_BOT_TOKEN`

**Setting up the webhook (for real-time):**

```bash
# Replace {TOKEN} and {YOUR_DOMAIN}
curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -d "url=https://{YOUR_DOMAIN}/webhooks/telegram"
```

For local testing, messages are fetched via Celery polling (every 2 min).

---

## Security Secrets (self-generated)

These don't come from external services. Generate them yourself.

### JWT Secret

Used to sign authentication tokens.

```bash
# Generate a secure random string
openssl rand -hex 32
```

| Variable       | Example                                                            |
| -------------- | ------------------------------------------------------------------ |
| `JWT_SECRET`   | `a1b2c3d4e5f6...` (64-char hex string)                            |
| `JWT_ALGORITHM`| `HS256` (default, don't change)                                    |
| `JWT_EXPIRY_HOURS` | `24` (default)                                                |

### AES-256 Encryption Key

Used to encrypt OAuth tokens stored in the database.

```bash
# Generate a 32-byte hex key (64 hex characters)
openssl rand -hex 32
```

| Variable         | Example                                                          |
| ---------------- | ---------------------------------------------------------------- |
| `ENCRYPTION_KEY` | `e4f8a2b1c9d7...` (64-char hex string)                          |

**Important:** If you lose or change this key, all stored OAuth tokens become unreadable and users must re-connect their platforms.

---

## Webhook Setup (for production)

Webhooks allow platforms to push messages to your server in real-time instead of polling. For **local development**, webhooks are optional — Celery polls every 2 minutes instead.

To test webhooks locally, use a tunnel:

### Using ngrok (recommended for dev)

```bash
# Install ngrok: https://ngrok.com/download
ngrok http 8000
```

This gives you a public URL like `https://abc123.ngrok.io`. Set it as:

```env
WEBHOOK_BASE_URL=https://abc123.ngrok.io
```

Then configure each platform's webhook URL:

| Platform  | Webhook URL                                    | Where to configure                    |
| --------- | ---------------------------------------------- | ------------------------------------- |
| Gmail     | `{WEBHOOK_BASE_URL}/webhooks/gmail`            | Google Cloud Pub/Sub push subscription|
| Slack     | `{WEBHOOK_BASE_URL}/webhooks/slack`            | Slack App > Event Subscriptions       |
| Telegram  | `{WEBHOOK_BASE_URL}/webhooks/telegram`         | Telegram Bot API `setWebhook`         |
| Discord   | Uses Gateway (WebSocket), no webhook needed    | N/A                                   |

---

## Complete .env Reference

Copy `.env.example` to `.env` and fill in:

```env
# ── Infrastructure (defaults work with Docker Compose) ──
DATABASE_URL=postgresql+asyncpg://app:secret@localhost:5432/unifyinbox
DATABASE_URL_SYNC=postgresql://app:secret@localhost:5432/unifyinbox
REDIS_URL=redis://localhost:6379/0
CHROMA_URL=http://localhost:8001

# ── AI (REQUIRED for AI features) ───────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── Security (REQUIRED — generate with openssl rand -hex 32) ─
JWT_SECRET=<your-64-char-hex>
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24
ENCRYPTION_KEY=<your-64-char-hex>

# ── Gmail OAuth2 (optional — only for Gmail integration) ─
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REDIRECT_URI=http://localhost:8000/auth/gmail/callback

# ── Slack OAuth2 (optional — only for Slack integration) ─
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_REDIRECT_URI=http://localhost:8000/auth/slack/callback

# ── Telegram (optional — only for Telegram integration) ──
TELEGRAM_BOT_TOKEN=

# ── Discord (optional — only for Discord integration) ────
DISCORD_BOT_TOKEN=
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DISCORD_REDIRECT_URI=http://localhost:8000/auth/discord/callback

# ── App ──────────────────────────────────────────────────
FRONTEND_URL=http://localhost:3000
WEBHOOK_BASE_URL=http://localhost:8000
APP_ENV=development
LOG_LEVEL=INFO
```

### What's required vs optional

| Variable           | Required? | Notes                                          |
| ------------------ | --------- | ---------------------------------------------- |
| `DATABASE_URL`     | Yes       | Defaults work with Docker Compose              |
| `REDIS_URL`        | Yes       | Defaults work with Docker Compose              |
| `CHROMA_URL`       | Yes       | Defaults work with Docker Compose              |
| `ANTHROPIC_API_KEY`| Yes*      | Without it, AI features use rule-based fallback|
| `JWT_SECRET`       | Yes       | Generate a unique value per environment        |
| `ENCRYPTION_KEY`   | Yes       | Generate a unique value per environment        |
| `GMAIL_*`          | No        | Only if connecting Gmail                       |
| `SLACK_*`          | No        | Only if connecting Slack                       |
| `TELEGRAM_*`       | No        | Only if connecting Telegram                    |
| `DISCORD_*`        | No        | Only if connecting Discord                     |
| `WEBHOOK_BASE_URL` | No        | Only for real-time webhook delivery            |

---

## Testing Checklist

### Frontend only (zero setup)

- [ ] Run `pnpm dev` in `frontend/`
- [ ] Open http://localhost:3000
- [ ] Click "Get Started" — should go to `/auth`
- [ ] Sign up (mock) — should go to `/onboarding`
- [ ] Connect 1+ platforms — should go to `/sync`
- [ ] Watch terminal animation — should auto-redirect to `/dashboard`
- [ ] Browse messages, click to open thread panel
- [ ] Click "Draft with AI" — typewriter fills reply
- [ ] Hover a message — snooze, done actions work
- [ ] Check keyboard shortcuts (press `?`)
- [ ] Visit Settings via sidebar
- [ ] Test all 4 settings tabs

### Backend + Frontend (full stack)

- [ ] `docker-compose up --build` — all 6 services healthy
- [ ] `docker-compose exec api alembic upgrade head` — migrations run
- [ ] `curl http://localhost:8000/docs` — Swagger UI loads
- [ ] `POST /auth/register` — create a user
- [ ] `POST /auth/login` — get JWT token
- [ ] Connect at least 1 platform via OAuth
- [ ] `GET /feed` — returns ranked messages
- [ ] `POST /actions/draft` — AI generates reply
- [ ] WebSocket `ws://localhost:8000/ws` — live feed updates
- [ ] Check Celery worker logs: `docker-compose logs worker`
- [ ] Check beat scheduler: `docker-compose logs beat`

---

## Common Issues

### Docker Compose fails to start

```
Error: port 5432 already in use
```

You have a local PostgreSQL running. Either stop it or change the port mapping in `docker-compose.yml`:

```yaml
ports:
  - "5433:5432"  # Map to 5433 instead
```

Then update `DATABASE_URL` in `.env` to use port `5433`.

### ChromaDB image pull fails

```
Error: manifest for chromadb/chroma:latest not found
```

Try pinning the version:

```yaml
chromadb:
  image: chromadb/chroma:0.5.20
```

### Gmail OAuth "redirect_uri_mismatch"

The redirect URI in your Google Cloud Console must **exactly match** `GMAIL_REDIRECT_URI` in `.env`:

```
http://localhost:8000/auth/gmail/callback
```

No trailing slash. Protocol matters (`http` vs `https`).

### Slack "invalid_redirect_uri"

Same as Gmail — the redirect URL in your Slack App settings must exactly match `SLACK_REDIRECT_URI`.

### Celery worker not processing tasks

Check that Redis is healthy:

```bash
docker-compose exec redis redis-cli ping
# Should return: PONG
```

Check worker logs:

```bash
docker-compose logs -f worker
```

### "ENCRYPTION_KEY invalid" on startup

The key must be exactly 64 hex characters (representing 32 bytes). Generate with:

```bash
openssl rand -hex 32
```

### Frontend build warnings about workspace root

This is a harmless Next.js warning about detecting multiple lockfiles. Can be ignored, or add to `next.config.mjs`:

```js
const nextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  typescript: {
    ignoreBuildErrors: true,
  },
}
```
