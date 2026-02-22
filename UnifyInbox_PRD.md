# UnifyInbox — Product Requirements Document
**Version:** 1.0 | **Status:** Draft | **Date:** February 2026

---

## 1. Executive Summary

UnifyInbox is the first AI-native universal communication OS that consolidates every messaging platform into a single intelligent feed — ranked by priority, enriched with context, and actionable without switching tabs.

### The Problem

The average knowledge worker uses 6–10 communication platforms daily — Gmail, WhatsApp, Slack, Discord, Telegram, and more. There is no unified interface to see, prioritize, and respond to all of them.

- 2.5+ hours lost daily to context switching across platforms
- Critical messages buried under noise with no intelligent triage
- Zero cross-platform priority intelligence
- Replying requires opening each app individually

### The Solution

UnifyInbox connects to every communication platform via official APIs, runs a multi-agent AI pipeline to rank messages by true priority, and surfaces them in a clean unified feed. Users can read, triage, draft AI-assisted replies, and send — all without leaving UnifyInbox.

---

## 2. Target Users

| Segment | Primary Pain | Willingness to Pay |
|---|---|---|
| Startup Founders | Juggling investors, team, customers across platforms | High ($20–50/mo) |
| College Students | Discord, WhatsApp, email from professors all competing | Medium ($10–15/mo) |
| Working Professionals | Work Slack + personal WhatsApp + email chaos | High ($15–30/mo) |
| Freelancers | Client comms scattered across 5+ platforms | High ($20–40/mo) |

---

## 3. User Personas

### Persona A — Startup Founder
- **Name:** Aryan, 27
- **Tools:** Gmail, Slack, WhatsApp (investors), Discord (community), Telegram (dev group)
- **Pain:** Misses investor messages buried in WhatsApp while dealing with team Slack fires
- **Goal:** Never miss a high-priority message; respond to what matters first
- **Quote:** "I spend more time finding messages than actually responding to them"

### Persona B — College Student
- **Name:** Priya, 21
- **Tools:** Gmail (professors), WhatsApp (family/friends), Discord (study groups)
- **Pain:** Misses assignment deadlines because professor emails drown in social notifications
- **Goal:** Academic and work messages surface above social noise automatically

### Persona C — Working Professional
- **Name:** Marcus, 34
- **Tools:** Gmail, Slack (work), WhatsApp (personal + some work), LinkedIn DMs
- **Pain:** Can't tell what's genuinely urgent vs can wait
- **Goal:** Clear separation of urgent/non-urgent + ability to reply from one place

---

## 4. Feature Requirements

### 4.1 Platform Integrations

| Platform | Priority | API Type | Notes |
|---|---|---|---|
| Gmail | **Must Have** | Gmail API (OAuth2) | Read + send + label |
| Slack | **Must Have** | Slack Web API | Channels + DMs + threads |
| Telegram | **Must Have** | Bot API | Personal + group messages |
| Discord | **Must Have** | Discord API | DMs + server channels |
| WhatsApp | Should Have | WhatsApp Business API | Requires Meta approval |
| Microsoft Outlook | Should Have | Microsoft Graph API | Enterprise users |
| Twitter/X DMs | Nice to Have | X API v2 | Paid tier required |
| iMessage | Out of Scope | No official API | Not feasible |

### 4.2 AI Agent Features

| Feature | Priority | Agent | Description |
|---|---|---|---|
| Message Normalization | **Must Have** | Reader Agent | Unified schema across all platforms |
| Sender Context Building | **Must Have** | Context Builder Agent | Who is this person + relationship history |
| Message Classification | **Must Have** | Classifier Agent | Tag: urgent / action / fyi / social / spam |
| Priority Ranking | **Must Have** | Priority Ranker Agent | Single sorted feed across platforms |
| Draft Reply Generation | **Must Have** | Draft Reply Agent | One-click AI draft per platform tone |
| Sentiment Detection | Should Have | Sentiment Agent | Flag tense/angry/delicate messages |
| Thread Summarization | Should Have | Summarizer Agent | Condense long threads to 3 bullets |
| Smart Snooze | Should Have | Scheduler Agent | Resurface at predicted right time |
| Style Learning | Nice to Have | Style Agent | Learn user's voice from sent history |

### 4.3 UI Features

| Feature | Priority |
|---|---|
| Unified Priority Feed | **Must Have** |
| Thread View | **Must Have** |
| Inline Reply Box | **Must Have** |
| Platform Filter | **Must Have** |
| Priority Filter (Urgent / Action / FYI) | **Must Have** |
| Snooze | **Must Have** |
| Mark as Done | **Must Have** |
| Keyboard Shortcuts | Should Have |
| Dark Mode | Should Have |
| Mobile App (iOS/Android) | Nice to Have (v2) |

---

## 5. User Stories

### Onboarding
- As a new user, I want to connect my Gmail account via OAuth so that my emails are imported without sharing my password
- As a new user, I want to see a setup checklist so I know which platforms are connected
- As a new user, I want the system to learn my priority preferences from my first 48 hours of usage

### Core Feed
- As a user, I want to see all messages from all platforms in a single ranked feed so I know what to handle first
- As a user, I want each message to show platform source, sender name, preview, and priority badge
- As a user, I want to see WHY a message is ranked a certain priority (e.g., "investor contact, first message in 30 days") so I trust the AI
- As a user, I want to filter the feed by platform or priority level

### Reply & Actions
- As a user, I want to click "Draft Reply" and get an AI-generated reply in the right tone for that platform
- As a user, I want to edit the AI draft before sending
- As a user, I want to send the reply directly from UnifyInbox without opening the original platform
- As a user, I want to snooze a message for 2 hours / tomorrow / next week

### AI Intelligence
- As a user, I want messages from VIP contacts (investors, manager, clients) to always rank highest
- As a user, I want the system to flag emotionally tense messages with a warning
- As a user, I want long Slack threads auto-summarized to 3 bullets

---

## 6. Functional Specification

### 6.1 Message Normalization Schema

```python
class MessageState(BaseModel):
    id: str                          # internal UUID
    platform: Platform               # gmail | slack | telegram | discord | whatsapp
    platform_message_id: str         # original ID from source platform
    thread_id: str
    sender: SenderContext
    content_text: str
    timestamp: str
    is_read: bool = False
    ai_enrichment: AIEnrichment = AIEnrichment()
    draft_reply: Optional[str] = None

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
    priority_score: float = 0.0      # 0.0 - 1.0
    priority_label: str = "fyi"      # urgent | action | fyi | social | spam
    sentiment: str = "neutral"       # positive | neutral | tense | urgent | distressed
    summary: str = ""
    context_note: str = ""           # "why this priority" explanation
    suggested_actions: list[str] = []
```

### 6.2 Priority Scoring Algorithm

| Signal | Weight | Description |
|---|---|---|
| Sender Relationship | 30% | VIP > Known Contact > Team > Stranger > Bot |
| Explicit Urgency Keywords | 20% | ASAP, urgent, deadline, today, help, call me |
| Time Sensitivity | 15% | Messages older than 24hrs decay in score |
| Historical Response Rate | 15% | You've replied to this person 80% of the time |
| Thread Activity | 10% | Active thread with multiple recent replies |
| Sentiment Intensity | 10% | Distressed or tense messages rank higher |

### 6.3 Notification Rules

- `priority_score >= 0.85` → push notification + red badge
- `priority_score 0.60–0.84` → yellow badge, no push
- `priority_score 0.30–0.59` → appears in feed, no badge
- `priority_score < 0.30` → collapsed into "Low Priority" section

### 6.4 Draft Reply Tone Profiles

| Platform | Tone Profile |
|---|---|
| Gmail | Professional, full sentences, proper greeting/sign-off |
| Slack | Concise, casual-professional, no greeting needed, emoji ok |
| WhatsApp | Warm, personal, short sentences, match sender tone |
| Telegram | Variable — formal for biz contacts, casual for personal |
| Discord | Community casual, brief, use @mention |

---

## 7. Monetization

### Pricing Tiers

| Feature | Free | Pro ($15/mo) | Team ($49/mo) |
|---|---|---|---|
| Platforms | 2 | All (7+) | All (7+) |
| Messages/Day | 50 | Unlimited | Unlimited |
| AI Draft Replies | 5/day | Unlimited | Unlimited |
| Thread Summarization | ❌ | ✅ | ✅ |
| VIP Contacts | 3 | Unlimited | Unlimited |
| Shared Team Inbox | ❌ | ❌ | ✅ |
| Analytics Dashboard | ❌ | ✅ | ✅ |

### Revenue Projections

| Period | Customers | MRR |
|---|---|---|
| Month 3 | 100 Pro + 10 Team | $2,000 |
| Month 6 | 500 Pro + 50 Team | $10,000 |
| Month 12 | 2,000 Pro + 200 Team | $40,000 |
| Month 18 | 8,000 Pro + 1,000 Team | $169,000 |

---

## 8. Product Roadmap

### Phase 1 — MVP (Months 1–2)
Goal: 100 users active daily with Gmail + Slack + Telegram + Discord

- OAuth connection for Gmail, Slack, Telegram, Discord
- Message ingestion + normalization pipeline
- Reader, Context Builder, Classifier, Priority Ranker agents
- Unified priority feed UI (React web app)
- Thread view + one-click AI Draft Reply
- Send reply through original platform API
- Snooze + mark done actions

### Phase 2 — Growth (Months 3–5)
Goal: 1,000 MAU + $10k MRR

- WhatsApp Business API integration
- Sentiment Detection + Thread Summarization agents
- VIP contacts management
- Priority explanation tooltip
- Mobile-responsive UI
- Billing integration (Stripe)

### Phase 3 — Intelligence Layer (Months 6–9)
Goal: Differentiate on AI quality — this is where the moat gets built

- Style Learning Agent (learns your writing voice)
- Smart Snooze (AI predicts best time to resurface)
- Follow-up Reminder Agent
- Cross-platform contact graph (same person on 3 platforms = unified contact)

### Phase 4 — Team & Enterprise (Months 10–12)
Goal: $40k MRR + enterprise pilot

- Shared team inbox + message delegation
- Team analytics (response time, volume trends)
- SSO / SAML for enterprise
- Microsoft Outlook + Teams integration
- API access for custom integrations

---

## 9. Success Metrics

### Product Health

| Metric | Target (Month 6) |
|---|---|
| DAU/MAU Ratio | 40% |
| Avg Sessions/Day | 3+ |
| Draft Reply Acceptance Rate | >60% sent unchanged |
| 30-Day Retention | >45% |
| 90-Day Retention | >30% |

### AI Quality

| Metric | Target |
|---|---|
| Priority Classification Accuracy | >85% user agreement |
| Draft Edit Rate | <40% require significant edits |
| False Urgent Rate | <5% |
| Missed Urgent Rate | <2% |

---

## 10. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| WhatsApp API denied by Meta | High | Launch without WA; make Gmail+Slack+Telegram compelling enough |
| API rate limits causing delays | Medium | Smart polling with exponential backoff; use webhooks where available |
| Privacy concerns about reading messages | High | End-to-end encrypted processing, no plaintext storage |
| AI priority ranking feels wrong | Medium | Show priority reasoning; let users correct AI (feedback loop) |
| Low draft quality killing trust | High | Use claude-sonnet for high-priority drafts; allow tone adjustment |
| User adoption friction from OAuth | Medium | One-click OAuth; show value within 5 minutes |
