# UnifyInbox — API Integration Spec + Agent Design Guide
**Version:** 1.0 | **Audience:** Engineering | **Date:** February 2026

---

## 1. Platform Integration Specifications

### 1.1 OAuth2 Flow (Same Pattern for All Platforms)

```
Client                  UnifyInbox Backend          Platform OAuth Server
  │                           │                            │
  │  1. Click "Connect Gmail" │                            │
  │──────────────────────────▶│                            │
  │                           │  2. Generate state token   │
  │  3. Redirect to OAuth     │────────────────────────────▶
  │◀──────────────────────────│                            │
  │                           │                            │
  │  4. User approves         │                            │
  │───────────────────────────────────────────────────────▶│
  │                           │                            │
  │  5. Redirect with ?code=  │                            │
  │──────────────────────────▶│                            │
  │                           │  6. Exchange code →        │
  │                           │     access_token +         │
  │                           │     refresh_token          │
  │                           │────────────────────────────▶
  │                           │                            │
  │  7. "Connected!"          │  8. Encrypt + store tokens │
  │◀──────────────────────────│                            │
```

---

### 1.2 Gmail

| Property | Value |
|---|---|
| OAuth Endpoint | `https://accounts.google.com/o/oauth2/auth` |
| Token Endpoint | `https://oauth2.googleapis.com/token` |
| Required Scopes | `gmail.readonly`, `gmail.send`, `gmail.modify` |
| API Base URL | `https://gmail.googleapis.com/gmail/v1` |
| Realtime Method | Gmail Push Notifications (Pub/Sub) — preferred over polling |
| Token Expiry | 1 hour (access) / 6 months (refresh) |
| Rate Limit | 250 quota units/user/sec (list=5u, get=5u, send=100u) |

**Push Notification Setup:**

```python
# adapters/gmail.py — Push notification setup
def setup_gmail_push(credentials, user_id: str):
    service = build('gmail', 'v1', credentials=credentials)
    result = service.users().watch(userId='me', body={
        'labelIds': ['INBOX'],
        'topicName': f'projects/{GCP_PROJECT}/topics/gmail-{user_id}'
    }).execute()
    return result['historyId']

# Webhook endpoint
@router.post("/webhooks/gmail")
async def gmail_webhook(request: Request):
    data = await request.json()
    message = base64.b64decode(data['message']['data'])
    payload = json.loads(message)
    user_email = payload['emailAddress']
    history_id = payload['historyId']
    await sync_gmail_since_history.delay(user_email, history_id)
```

---

### 1.3 Slack

| Property | Value |
|---|---|
| OAuth Endpoint | `https://slack.com/oauth/v2/authorize` |
| Required Scopes | `channels:history`, `im:history`, `chat:write`, `users:read` |
| API Base URL | `https://slack.com/api/` |
| Realtime Method | Slack Events API (webhooks) |
| Rate Limits | Tier 1: 1/sec · Tier 2: 20/min · Tier 3: 50/min |

**Events API Webhook Handler:**

```python
@router.post("/webhooks/slack")
async def slack_webhook(request: Request):
    body = await request.json()

    # One-time URL verification
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    # Validate Slack signature
    if not verify_slack_signature(request):
        raise HTTPException(403)

    event = body.get("event", {})
    if event.get("type") in ["message", "app_mention"]:
        if event.get("bot_id"):   # skip bot messages
            return {"ok": True}

        await process_slack_message.delay({
            "user_id": event["user"],
            "channel": event["channel"],
            "text": event["text"],
            "ts": event["ts"],
            "thread_ts": event.get("thread_ts")
        })
    return {"ok": True}
```

---

### 1.4 Telegram

| Property | Value |
|---|---|
| Bot Creation | `t.me/BotFather` — create bot, get token |
| API Base URL | `https://api.telegram.org/bot{token}/` |
| Realtime Method | `setWebhook` (prod) or `getUpdates` long polling (dev) |
| Rate Limit | 30 msg/sec to different chats, 20 msg/min to same chat |
| User Auth | Telegram Login Widget for user identity |

**Webhook Setup + Handler:**

```python
# Setup
async def setup_telegram_webhook(bot_token: str, webhook_url: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "allowed_updates": ["message", "edited_message"],
                "drop_pending_updates": True
            }
        )

# Handler
@router.post("/webhooks/telegram/{user_id}")
async def telegram_webhook(user_id: str, request: Request):
    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    await process_telegram_message.delay({
        "user_id": user_id,
        "from": message["from"],
        "chat": message["chat"],
        "text": message.get("text", ""),
        "date": message["date"],
        "message_id": message["message_id"]
    })
    return {"ok": True}
```

---

### 1.5 Discord

| Property | Value |
|---|---|
| Bot Permissions | Read Messages, Send Messages, Read Message History |
| OAuth Scopes | `bot`, `identify`, `messages.read` |
| API Base URL | `https://discord.com/api/v10` |
| Realtime Method | Discord Gateway (persistent WebSocket) |
| Events | `MESSAGE_CREATE`, `DIRECT_MESSAGE_CREATE` |
| Rate Limit | 50 req/sec global, 5 req/sec per route |

**Gateway WebSocket Connection:**

```python
# adapters/discord.py
import websockets, json, asyncio

class DiscordGateway:
    GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

    async def connect(self, bot_token: str, on_message):
        async with websockets.connect(self.GATEWAY_URL) as ws:
            hello = json.loads(await ws.recv())
            heartbeat_interval = hello['d']['heartbeat_interval']

            # Identify
            await ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": bot_token,
                    "intents": 32768,  # DIRECT_MESSAGES intent
                    "properties": {"os": "linux", "browser": "unifyinbox", "device": "unifyinbox"}
                }
            }))

            asyncio.create_task(self._heartbeat(ws, heartbeat_interval))

            async for raw in ws:
                event = json.loads(raw)
                if event.get('t') == 'MESSAGE_CREATE':
                    await on_message(event['d'])
```

---

## 2. Complete Agent Prompt Library

> All prompts are versioned. Track performance in the DB. A/B test before promoting.

### 2.1 Context Builder Agent

```python
SYSTEM = """
You are a relationship intelligence agent. Analyze communication patterns
and determine the sender's relationship with the user.
Respond with valid JSON only. No preamble.
"""

USER = """
SENDER INFO:
- Name: {sender_name}
- Identifier: {sender_identifier}
- Platform: {platform}
- First seen: {first_seen}

PAST INTERACTIONS (last 20):
{interaction_history}

USER REPLY BEHAVIOR:
- Total messages: {total_messages}
- Times replied: {reply_count}
- Avg reply time: {avg_reply_hours}h
- Last interaction: {last_interaction_days} days ago

Return JSON:
{{
  "relationship_type": "vip|close_contact|work_contact|acquaintance|stranger|bot|newsletter",
  "reply_rate": 0.0,
  "context_summary": "one sentence who this person is",
  "is_likely_important": true
}}
"""
```

### 2.2 Classifier Agent

```python
SYSTEM = """
You are a message priority classifier.
Respond with valid JSON only.
"""

USER = """
SENDER: {relationship_type} | reply rate: {reply_rate} | VIP: {is_vip}
PLATFORM: {platform}
TIME: {timestamp}

MESSAGE:
{message_text}

LABELS:
- urgent: Requires response within hours, time-sensitive
- action: Requires response, not immediately critical
- fyi: Informational, no response needed
- social: Casual, low professional priority
- spam: Unsolicited, promotional, low value

SCORE GUIDE:
- 0.9-1.0: Urgent from VIP
- 0.7-0.89: Action from known contact
- 0.5-0.69: Action from stranger OR fyi from VIP
- 0.3-0.49: Social from known contact
- 0.0-0.29: Newsletter, bot, spam

Return JSON:
{{
  "label": "urgent|action|fyi|social|spam",
  "priority_score": 0.0,
  "time_sensitive": true,
  "reasoning": "one sentence max"
}}
"""
```

### 2.3 Sentiment Agent

```python
SYSTEM = """
You detect emotional tone in messages to help users approach
sensitive conversations appropriately.
Respond with JSON only.
"""

USER = """
MESSAGE: {message_text}
SENDER: {sender_name} ({relationship_type})
PLATFORM: {platform}

Tone options:
- positive: Warm, appreciative, excited
- neutral: Factual, professional, routine
- tense: Frustrated, disappointed, formal complaint
- urgent: Panicked, overwhelmed, needs immediate help
- distressed: Significant distress or crisis signals

Return JSON:
{{
  "sentiment": "positive|neutral|tense|urgent|distressed",
  "is_complaint": false,
  "needs_careful_response": false,
  "suggested_approach": "one sentence on how to reply"
}}
"""
```

### 2.4 Draft Reply Agent

```python
SYSTEM = """
You draft messages on behalf of users across communication platforms.

Rules:
1. Match the platform's communication style exactly
2. Address the actual question/request — not a generic reply
3. Sound human — never start with "Certainly!" or "Of course!"
4. Return ONLY the reply text, nothing else
"""

USER = """
PLATFORM: {platform}
TONE: {tone_profile}
SENDER: {sender_name} ({relationship_type})
SENTIMENT: {sentiment}
{careful_note}

THREAD (newest last):
{thread_history}

MESSAGE TO REPLY:
{message_text}
"""

TONE_PROFILES = {
    "gmail":    "Professional email. Proper greeting with name. Full sentences. Formal sign-off. Max 150 words.",
    "slack":    "Slack. No greeting. Under 3 sentences. Casual-professional. Emoji ok if appropriate.",
    "telegram": "Telegram. Short and direct. Warm if known, neutral if stranger. 1-3 sentences.",
    "discord":  "Discord. Community casual. 1-2 sentences. Use @name if channel reply.",
    "whatsapp": "WhatsApp. Personal and warm. Short sentences. Natural spoken language. 1-3 sentences.",
}
```

### 2.5 Thread Summarizer Agent

```python
SYSTEM = """
You summarize conversation threads into actionable bullet points.
Respond with JSON only.
"""

USER = """
PLATFORM: {platform}
PARTICIPANTS: {participants}
MESSAGES ({message_count} total):
{messages}

Return JSON:
{{
  "key_points": ["max 3 bullets of what was discussed/decided"],
  "action_items": ["any actions requested or agreed to"],
  "current_status": "one sentence where things stand",
  "next_step": "what user needs to do, or null"
}}
"""
```

---

## 3. Frontend Component Specification

### 3.1 Component Tree

```
App
├── Sidebar
│   ├── PlatformFilter  (All | Gmail | Slack | Telegram | Discord)
│   ├── PriorityFilter  (All | Urgent | Action | FYI | Social)
│   └── UserSettings
└── MainContent
    ├── FeedHeader       (counts + last-sync time)
    ├── PriorityFeed
    │   ├── UrgentSection     (priority_score >= 0.85)
    │   │   └── MessageCard[]
    │   ├── ActionSection     (0.60 <= score < 0.85)
    │   │   └── MessageCard[]
    │   └── LowPriorityCollapsible
    │       └── MessageCard[]
    └── ThreadModal
        ├── ThreadHeader     (sender info, platform badge)
        ├── MessageList      (full thread history)
        ├── AISummaryBanner  (shown if thread > 5 messages)
        ├── SentimentAlert   (shown if tense/urgent/distressed)
        └── ReplyComposer
            ├── DraftButton  (triggers AI draft)
            ├── EditableTextarea
            ├── CharCount + ToneIndicator
            └── SendButton
```

### 3.2 MessageCard Component

```typescript
// components/MessageCard.tsx
interface MessageCardProps {
  message: MessageState;
  onOpen: (id: string) => void;
  onSnooze: (id: string, until: Date) => void;
  onMarkDone: (id: string) => void;
}

const PLATFORM_STYLES = {
  gmail:    { color: "EA4335", label: "Gmail" },
  slack:    { color: "4A154B", label: "Slack" },
  telegram: { color: "229ED9", label: "Telegram" },
  discord:  { color: "5865F2", label: "Discord" },
};

const PRIORITY_STYLES = {
  urgent: { color: "EF4444", label: "Urgent" },
  action: { color: "F59E0B", label: "Action" },
  fyi:    { color: "3B82F6", label: "FYI" },
  social: { color: "6B7280", label: "Social" },
  spam:   { color: "9CA3AF", label: "Spam" },
};

export function MessageCard({ message, onOpen, onSnooze, onMarkDone }: MessageCardProps) {
  const platform = PLATFORM_STYLES[message.platform];
  const priority = PRIORITY_STYLES[message.ai_enrichment.priority_label];

  return (
    <div className="message-card" onClick={() => onOpen(message.id)}>
      <PlatformBadge platform={platform} />
      <SenderAvatar name={message.sender.name} isVIP={message.sender.is_vip} />

      <div className="card-body">
        <div className="card-header">
          <span className="sender-name">{message.sender.name}</span>
          <PriorityBadge priority={priority} />
          <TimeAgo timestamp={message.timestamp} />
        </div>
        <div className="preview">{message.content_text.slice(0, 120)}...</div>
        {message.ai_enrichment.context_note && (
          <div className="ai-note">💡 {message.ai_enrichment.context_note}</div>
        )}
      </div>

      <div className="actions">
        <button onClick={e => { e.stopPropagation(); onSnooze(message.id, snoozeOptions); }}>
          Snooze
        </button>
        <button onClick={e => { e.stopPropagation(); onMarkDone(message.id); }}>
          Done
        </button>
      </div>
    </div>
  );
}
```

### 3.3 ReplyComposer Component

```typescript
// components/ReplyComposer.tsx
export function ReplyComposer({ message, thread }: ReplyComposerProps) {
  const [draft, setDraft] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const generateDraft = async () => {
    setIsGenerating(true);
    try {
      const res = await api.post(`/draft/${message.id}`);
      setDraft(res.data.draft);
    } finally {
      setIsGenerating(false);
    }
  };

  const sendReply = async () => {
    setIsSending(true);
    try {
      await api.post(`/send/${message.id}`, { text: draft });
      toast.success(`Sent via ${message.platform}`);
      onClose();
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="reply-composer">
      {message.ai_enrichment.needs_careful_response && (
        <SentimentAlert
          tone={message.ai_enrichment.sentiment}
          approach={message.ai_enrichment.suggested_approach}
        />
      )}
      <textarea
        value={draft}
        onChange={e => setDraft(e.target.value)}
        placeholder="Write a reply or click 'Draft with AI'..."
        rows={4}
      />
      <div className="footer">
        <ToneIndicator platform={message.platform} />
        <button onClick={generateDraft} disabled={isGenerating}>
          {isGenerating ? "Generating..." : "✨ Draft with AI"}
        </button>
        <button onClick={sendReply} disabled={!draft || isSending}>
          {isSending ? "Sending..." : `Send via ${message.platform}`}
        </button>
      </div>
    </div>
  );
}
```

### 3.4 useFeed Hook (WebSocket + REST)

```typescript
// hooks/useFeed.ts
export function useFeed(filters: FeedFilters) {
  const [messages, setMessages] = useState<MessageState[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const ws = useRef<WebSocket | null>(null);

  // Initial load
  useEffect(() => {
    api.get('/feed', { params: filters })
      .then(res => setMessages(res.data.messages))
      .finally(() => setIsLoading(false));
  }, [filters]);

  // WebSocket for live updates
  useEffect(() => {
    ws.current = new WebSocket(`${WS_URL}/ws/feed?token=${getToken()}`);

    ws.current.onmessage = (event) => {
      const { event: type, data } = JSON.parse(event.data);

      if (type === 'new_message') {
        setMessages(prev => {
          const updated = [data, ...prev.filter(m => m.id !== data.id)];
          return updated.sort((a, b) => b.ai_enrichment.priority_score - a.ai_enrichment.priority_score);
        });
      }

      if (type === 'priority_updated') {
        setMessages(prev => prev.map(m =>
          m.id === data.message_id
            ? { ...m, ai_enrichment: { ...m.ai_enrichment, priority_score: data.new_score } }
            : m
        ));
      }
    };

    return () => ws.current?.close();
  }, []);

  const snooze = (id: string, until: Date) => {
    api.patch(`/message/${id}`, { snoozed_until: until.toISOString() });
    setMessages(prev => prev.filter(m => m.id !== id));
  };

  const markDone = (id: string) => {
    api.patch(`/message/${id}`, { is_done: true });
    setMessages(prev => prev.filter(m => m.id !== id));
  };

  return { messages, isLoading, snooze, markDone };
}
```

---

## 4. Error Handling

| Error | Strategy | User Sees |
|---|---|---|
| Platform API rate limit (429) | Exponential backoff, retry up to 5x | "Syncing..." (transparent) |
| OAuth token expired | Auto-refresh, retry request | Nothing |
| OAuth token revoked | Flag platform as disconnected | "Reconnect Gmail to continue" |
| Claude API error | Fallback to rule-based classification | Nothing |
| Claude API timeout | Return message without AI enrichment | Message shown without AI note |
| Send failure (network) | Retry 3x with backoff | "Failed to send, retrying..." |
| Send failure (platform rejected) | Do not retry, log | "Message rejected by [platform]" |

---

## 5. Overnight Build Checklist

> Build in this exact order. Don't polish. Don't skip ahead. Get it working first.

### Hour 0–1: Project Setup
- [ ] Create repo, Python venv, install `fastapi uvicorn anthropic python-dotenv sqlalchemy asyncpg`
- [ ] Create `agents/state.py` with full Pydantic MessageState model
- [ ] Create `core/database.py` with async SQLAlchemy + messages table
- [ ] Copy `.env.example`, add `ANTHROPIC_API_KEY`
- [ ] `main.py` with basic FastAPI returning `{"status": "ok"}`

### Hour 1–2.5: Gmail Adapter
- [ ] Set up Google OAuth2 credentials in Google Cloud Console
- [ ] `GET /auth/gmail/connect` — redirect to Google OAuth
- [ ] `GET /auth/gmail/callback` — exchange code, store encrypted token
- [ ] `GmailAdapter.fetch_new_messages()` — poll inbox
- [ ] `GmailAdapter.normalize()` — raw Gmail → MessageState
- [ ] **Test:** manually trigger sync, verify 5 emails appear in DB

### Hour 2.5–4: Agent Pipeline
- [ ] `ClassifierAgent` (claude-haiku) — just 3 labels to start: urgent | action | rest
- [ ] `PriorityRankerAgent` — rule-based scoring using relationship + label
- [ ] `agents/pipeline.py` — orchestrate: normalize → classify → score → save
- [ ] Wire pipeline into Gmail sync
- [ ] **Test:** sync Gmail, verify messages have `priority_score` and `priority_label`

### Hour 4–5: Feed API
- [ ] `GET /api/v1/feed` — messages sorted by `priority_score DESC`
- [ ] Add `platform` and `priority` query param filters
- [ ] `PATCH /api/v1/message/{id}` for `is_done` + `snoozed_until`
- [ ] **Test:** `curl /api/v1/feed`, verify sort order

### Hour 5–6: Draft Reply
- [ ] `DraftReplyAgent` (claude-sonnet) with Gmail tone profile
- [ ] `POST /api/v1/draft/{message_id}`
- [ ] `POST /api/v1/send/{message_id}` — calls `GmailAdapter.send_message()`
- [ ] **Test:** generate a draft for a real email, send it, verify delivery

### Hour 6–8: React UI
- [ ] `npx create-react-app frontend --template typescript` + TailwindCSS
- [ ] `FeedPage` — fetch `/api/v1/feed`, render MessageCard list
- [ ] `MessageCard` — sender, preview, priority badge, platform badge
- [ ] `ThreadModal` — click card → show messages → `ReplyComposer`
- [ ] `ReplyComposer` — textarea + "Draft AI" button + "Send" button
- [ ] Wire Draft AI → call `/draft/{id}` → populate textarea
- [ ] Wire Send → call `/send/{id}` → toast success

---

**✅ You now have a working product.** Gmail inbox, AI-ranked, one-click AI drafts, in-app send.

### Hour 8+: Stretch Goals
- [ ] Add Slack adapter (same pattern as Gmail)
- [ ] Add Telegram adapter
- [ ] Add Context Builder Agent (sender relationship enrichment)
- [ ] Add Sentiment Agent + SentimentAlert in ReplyComposer
- [ ] Add WebSocket for live feed updates (`/ws/feed`)
- [ ] Add `ContextNote` tooltip in MessageCard explaining "why this priority"
- [ ] Add Celery + Redis for background polling

---

## 6. Requirements File

```txt
# requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.32.0
anthropic==0.40.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
redis==5.2.0
celery==5.4.0
chromadb==0.5.20
python-dotenv==1.0.1
pydantic==2.10.0
pydantic-settings==2.6.0
httpx==0.28.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
google-auth==2.37.0
google-auth-oauthlib==1.2.1
google-api-python-client==2.157.0
slack-sdk==3.33.4
python-telegram-bot==21.9
websockets==14.1
```
