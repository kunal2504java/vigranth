"""
AI Action API — draft replies, send messages, reclassify.

Endpoints (from Architecture doc Section 5.3):
  POST /api/v1/draft/{message_id}                — generate AI draft
  PUT  /api/v1/draft/{message_id}                — save edited draft
  POST /api/v1/send/{message_id}                 — send reply via platform
  POST /api/v1/message/{message_id}/reclassify   — user feedback on classification
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import get_current_user_id, decrypt_token
from backend.core.redis import cache
from backend.agents.state import (
    DraftResponse,
    SendRequest,
    SendResponse,
    ReclassifyRequest,
    MessageState,
    SenderContext,
    AIEnrichment,
)
from backend.agents.draft_reply import generate_draft
from backend.adapters.registry import get_adapter
from backend.models.database import Message, PlatformCredential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["actions"])


@router.post("/draft/{message_id}", response_model=DraftResponse)
async def create_draft(
    message_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate an AI draft reply for a message.
    Uses claude-sonnet with platform-specific tone profiles.
    Rate limited: 10 req/min for AI actions.
    """
    # Check rate limit
    allowed = await cache.check_rate_limit(user_id, "draft", limit=10, window=60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for AI actions")

    # Fetch message
    message = await _get_user_message(db, message_id, user_id)

    # Build MessageState for the draft agent
    state = _msg_to_state(message)

    # Fetch thread context for better drafts
    thread_context = await _get_thread_context(db, user_id, message.platform, message.thread_id)

    # Generate draft
    draft_text = await generate_draft(state, thread_context)

    # Save draft to DB
    message.draft_reply = draft_text
    await db.flush()

    platform = message.platform
    tone_map = {
        "gmail": "professional",
        "slack": "casual-professional",
        "telegram": "direct",
        "discord": "casual",
        "whatsapp": "warm-personal",
    }

    return DraftResponse(
        draft=draft_text,
        tone_used=tone_map.get(platform, "neutral"),
    )


@router.put("/draft/{message_id}")
async def save_draft(
    message_id: str,
    request: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Save an edited draft reply."""
    message = await _get_user_message(db, message_id, user_id)

    edited_draft = request.get("edited_draft", "")
    if not edited_draft:
        raise HTTPException(status_code=400, detail="edited_draft is required")

    message.draft_reply = edited_draft
    await db.flush()

    return {"success": True}


@router.post("/send/{message_id}", response_model=SendResponse)
async def send_reply(
    message_id: str,
    payload: SendRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a reply through the original platform's API.
    Fetches the user's encrypted OAuth credentials, decrypts them,
    and calls the appropriate platform adapter.
    """
    message = await _get_user_message(db, message_id, user_id)

    # Get platform credentials
    cred_result = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
            PlatformCredential.platform == message.platform,
        )
    )
    cred = cred_result.scalar_one_or_none()

    if not cred:
        raise HTTPException(
            status_code=400,
            detail=f"No {message.platform} credentials found. Reconnect the platform.",
        )

    # Decrypt credentials
    try:
        credentials = {
            "access_token": decrypt_token(cred.access_token),
        }
        if cred.refresh_token:
            credentials["refresh_token"] = decrypt_token(cred.refresh_token)
    except Exception as e:
        logger.error(f"Failed to decrypt credentials: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt platform credentials")

    # Get adapter and send
    adapter = get_adapter(message.platform)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {message.platform}")

    # Build kwargs based on platform
    send_kwargs = {}
    if message.platform == "gmail":
        send_kwargs["to_email"] = message.sender_email or message.sender_id
        send_kwargs["subject"] = f"Re: "
    elif message.platform == "slack":
        send_kwargs["channel_id"] = message.thread_id
    elif message.platform == "telegram":
        send_kwargs["chat_id"] = message.thread_id
        send_kwargs["reply_to_message_id"] = message.platform_message_id
    elif message.platform == "discord":
        send_kwargs["channel_id"] = message.thread_id

    result = await adapter.send_message(
        thread_id=message.thread_id or "",
        text=payload.text,
        credentials=credentials,
        **send_kwargs,
    )

    if result.get("success"):
        # Invalidate feed cache
        await cache.invalidate_feed(user_id)
        logger.info(f"Message sent via {message.platform} for user {user_id}")

    return SendResponse(
        success=result.get("success", False),
        platform_message_id=result.get("platform_message_id"),
        error=result.get("error"),
    )


@router.post("/message/{message_id}/reclassify")
async def reclassify_message(
    message_id: str,
    payload: ReclassifyRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    User feedback: correct the AI's classification.
    Updates the label and triggers a score recalculation.
    This feedback loop improves the model over time.
    """
    message = await _get_user_message(db, message_id, user_id)

    valid_labels = ["urgent", "action", "fyi", "social", "spam"]
    if payload.correct_label not in valid_labels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid label. Must be one of: {valid_labels}",
        )

    # Update label
    old_label = message.priority_label
    message.priority_label = payload.correct_label

    # Adjust score based on new label
    label_score_map = {
        "urgent": 0.90,
        "action": 0.70,
        "fyi": 0.45,
        "social": 0.25,
        "spam": 0.10,
    }
    message.priority_score = label_score_map.get(payload.correct_label, 0.45)
    message.classification_reasoning = (
        f"User corrected from '{old_label}' to '{payload.correct_label}'"
    )

    await db.flush()

    # Invalidate feed cache
    await cache.invalidate_feed(user_id)

    logger.info(
        f"User {user_id} reclassified message {message_id}: "
        f"{old_label} -> {payload.correct_label}"
    )

    return {"success": True}


# --- Internal helpers ---

async def _get_user_message(db: AsyncSession, message_id: str, user_id: str) -> Message:
    """Fetch a message ensuring it belongs to the user."""
    result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.user_id == user_id,
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


async def _get_thread_context(
    db: AsyncSession,
    user_id: str,
    platform: str,
    thread_id: str,
    limit: int = 5,
) -> list[str]:
    """Get recent thread messages for context."""
    result = await db.execute(
        select(Message.sender_name, Message.content_text)
        .where(
            Message.user_id == user_id,
            Message.platform == platform,
            Message.thread_id == thread_id,
        )
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    rows = result.all()
    return [f"{row[0]}: {row[1]}" for row in reversed(rows) if row[1]]


def _msg_to_state(msg: Message) -> MessageState:
    """Convert Message ORM to MessageState."""
    return MessageState(
        id=str(msg.id),
        user_id=str(msg.user_id),
        platform=msg.platform,
        platform_message_id=msg.platform_message_id,
        thread_id=msg.thread_id or "",
        sender=SenderContext(
            id=msg.sender_id,
            name=msg.sender_name or "",
            email=msg.sender_email,
        ),
        content_text=msg.content_text or "",
        timestamp=msg.timestamp.isoformat() if msg.timestamp else "",
        ai_enrichment=AIEnrichment(
            priority_score=msg.priority_score or 0.0,
            priority_label=msg.priority_label or "fyi",
            sentiment=msg.sentiment or "neutral",
            context_note=msg.ai_context_note or "",
            needs_careful_response=msg.needs_careful_response or False,
            suggested_approach=msg.suggested_approach or "",
        ),
    )
