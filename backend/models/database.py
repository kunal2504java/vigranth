"""
SQLAlchemy ORM models mapping to the PostgreSQL schema.
Follows the schema defined in Architecture doc Section 4.1.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Float,
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)  # nullable for OAuth-only users
    created_at = Column(DateTime(timezone=True), default=utcnow)
    settings = Column(JSON, default=dict)

    # Relationships
    credentials = relationship("PlatformCredential", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"


class PlatformCredential(Base):
    """Stores encrypted OAuth tokens for each connected platform."""
    __tablename__ = "platform_credentials"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)
    access_token = Column(Text, nullable=False)  # AES-256 encrypted
    refresh_token = Column(Text, nullable=True)   # AES-256 encrypted
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    platform_user_id = Column(String(255), nullable=True)
    scopes = Column(Text, nullable=True)
    webhook_id = Column(String(255), nullable=True)  # for tracking registered webhooks
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Unique constraint: one credential per user per platform
    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_user_platform"),
    )

    # Relationships
    user = relationship("User", back_populates="credentials")

    def __repr__(self):
        return f"<PlatformCredential {self.platform} for user {self.user_id}>"


class Message(Base):
    """Normalized messages from all platforms, enriched by AI agents."""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)
    platform_message_id = Column(String(255), nullable=False)
    thread_id = Column(String(255), nullable=True)

    # Sender info
    sender_id = Column(String(255), nullable=False)
    sender_name = Column(String(255), nullable=True)
    sender_email = Column(String(255), nullable=True)

    # Content
    content_text = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    # User actions
    is_read = Column(Boolean, default=False)
    is_done = Column(Boolean, default=False)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)

    # AI enrichment fields
    priority_score = Column(Float, default=0.0)
    priority_label = Column(String(20), default="fyi")
    sentiment = Column(String(20), default="neutral")
    ai_context_note = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    classification_reasoning = Column(Text, nullable=True)
    is_complaint = Column(Boolean, default=False)
    needs_careful_response = Column(Boolean, default=False)
    suggested_approach = Column(Text, nullable=True)
    suggested_actions = Column(JSON, default=list)

    # Draft
    draft_reply = Column(Text, nullable=True)

    # Timestamps
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    # Unique constraint: no duplicate messages per user per platform
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "platform_message_id", name="uq_user_platform_msg"),
        Index("idx_messages_platform", "user_id", "platform"),
        Index("idx_messages_thread", "thread_id"),
    )

    # Relationships
    user = relationship("User", back_populates="messages")

    def __repr__(self):
        return f"<Message {self.platform}:{self.platform_message_id}>"

    def to_message_state(self) -> dict:
        """Convert ORM model to a dict compatible with MessageState."""
        from backend.agents.state import MessageState, SenderContext, AIEnrichment, Platform
        return MessageState(
            id=str(self.id),
            user_id=str(self.user_id),
            platform=self.platform,
            platform_message_id=self.platform_message_id,
            thread_id=self.thread_id or "",
            sender=SenderContext(
                id=self.sender_id,
                name=self.sender_name or "",
                email=self.sender_email,
            ),
            content_text=self.content_text or "",
            timestamp=self.timestamp.isoformat() if self.timestamp else "",
            is_read=self.is_read or False,
            is_done=self.is_done or False,
            snoozed_until=self.snoozed_until.isoformat() if self.snoozed_until else None,
            ai_enrichment=AIEnrichment(
                priority_score=self.priority_score or 0.0,
                priority_label=self.priority_label or "fyi",
                sentiment=self.sentiment or "neutral",
                summary=self.summary or "",
                context_note=self.ai_context_note or "",
                suggested_actions=self.suggested_actions or [],
                is_complaint=self.is_complaint or False,
                needs_careful_response=self.needs_careful_response or False,
                suggested_approach=self.suggested_approach or "",
                classification_reasoning=self.classification_reasoning or "",
            ),
            draft_reply=self.draft_reply,
            created_at=self.created_at.isoformat() if self.created_at else None,
        ).model_dump()


class Contact(Base):
    """Cross-platform contact relationship graph."""
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    contact_identifier = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False)
    display_name = Column(String(255), nullable=True)
    relationship = Column(String(50), default="stranger")
    is_vip = Column(Boolean, default=False)
    reply_rate = Column(Float, default=0.0)
    message_count = Column(Integer, default=0)
    last_interaction = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "platform", "contact_identifier", name="uq_user_platform_contact"),
        Index("idx_contacts_user", "user_id"),
        Index("idx_contacts_vip", "user_id", "is_vip"),
    )

    # Relationships
    user = relationship("User", back_populates="contacts")

    def __repr__(self):
        return f"<Contact {self.display_name} on {self.platform}>"


class SyncState(Base):
    """Tracks the last sync timestamp per user per platform."""
    __tablename__ = "sync_states"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_history_id = Column(String(255), nullable=True)  # Gmail uses history IDs
    status = Column(String(20), default="idle")  # idle | syncing | error
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_user_platform_sync"),
    )
