"""
Shared Pydantic state models for the agent pipeline.
These models flow through every agent and accumulate enrichments.

From Architecture doc Section 2.3 — this is the single source of truth
for message state as it passes through the pipeline.
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class Platform(str, Enum):
    GMAIL = "gmail"
    SLACK = "slack"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"


class RelationshipType(str, Enum):
    VIP = "vip"
    CLOSE_CONTACT = "close_contact"
    WORK_CONTACT = "work_contact"
    ACQUAINTANCE = "acquaintance"
    STRANGER = "stranger"
    BOT = "bot"
    NEWSLETTER = "newsletter"


class PriorityLabel(str, Enum):
    URGENT = "urgent"
    ACTION = "action"
    FYI = "fyi"
    SOCIAL = "social"
    SPAM = "spam"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    TENSE = "tense"
    URGENT = "urgent"
    DISTRESSED = "distressed"


class SenderContext(BaseModel):
    """Sender information enriched by the Context Builder Agent."""
    id: str
    name: str
    email: Optional[str] = None
    username: Optional[str] = None
    relationship: str = RelationshipType.STRANGER.value
    is_vip: bool = False
    historical_reply_rate: float = 0.0
    last_interaction_days: Optional[int] = None
    context_summary: str = ""


class AIEnrichment(BaseModel):
    """AI-generated enrichments accumulated across agents."""
    priority_score: float = Field(default=0.0, ge=0.0, le=1.0)
    priority_label: str = PriorityLabel.FYI.value
    sentiment: str = Sentiment.NEUTRAL.value
    summary: str = ""
    context_note: str = ""  # shown in UI as "why this priority"
    suggested_actions: list[str] = Field(default_factory=list)
    is_complaint: bool = False
    needs_careful_response: bool = False
    suggested_approach: str = ""
    time_sensitive: bool = False
    classification_reasoning: str = ""


class MessageState(BaseModel):
    """
    The unified message schema that flows through the entire pipeline.
    Every agent reads from and writes to this model.
    """
    id: str
    user_id: str = ""
    platform: Platform
    platform_message_id: str
    thread_id: str
    sender: SenderContext
    content_text: str
    timestamp: str
    is_read: bool = False
    is_done: bool = False
    snoozed_until: Optional[str] = None
    ai_enrichment: AIEnrichment = Field(default_factory=AIEnrichment)
    draft_reply: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        use_enum_values = True


# --- API Request/Response models ---

class MessageUpdateRequest(BaseModel):
    """PATCH /api/v1/message/{id}"""
    is_read: Optional[bool] = None
    is_done: Optional[bool] = None
    snoozed_until: Optional[str] = None


class DraftResponse(BaseModel):
    """POST /api/v1/draft/{message_id}"""
    draft: str
    tone_used: str


class SendRequest(BaseModel):
    """POST /api/v1/send/{message_id}"""
    text: str


class SendResponse(BaseModel):
    success: bool
    platform_message_id: Optional[str] = None
    error: Optional[str] = None


class FeedResponse(BaseModel):
    messages: list[MessageState]
    total: int
    has_more: bool


class ReclassifyRequest(BaseModel):
    """User feedback to correct AI classification."""
    correct_label: str


class PlatformStatus(BaseModel):
    platform: str
    connected: bool
    last_sync: Optional[str] = None
    platform_user_id: Optional[str] = None


class ConnectRequest(BaseModel):
    auth_code: str


class ConnectResponse(BaseModel):
    success: bool
    platform_user_id: Optional[str] = None
    error: Optional[str] = None


# --- Auth models ---

class UserCreate(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    created_at: Optional[str] = None
