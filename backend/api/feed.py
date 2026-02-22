"""
Feed API — message feed, thread view, and message updates.

Endpoints (from Architecture doc Section 5.2):
  GET   /api/v1/feed                         — ranked priority feed
  GET   /api/v1/thread/{platform}/{thread_id} — full thread with summary
  PATCH /api/v1/message/{message_id}          — update message state
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import get_current_user_id
from backend.core.redis import cache
from backend.agents.state import MessageState, MessageUpdateRequest, FeedResponse, SenderContext, AIEnrichment
from backend.agents.summarizer import summarize_thread
from backend.models.database import Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feed"])


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    platform: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the ranked priority feed for the current user.
    Supports filtering by platform and priority label.
    Uses Redis cache (30s TTL) when no filters are applied.
    """
    # Try cache for unfiltered feed
    cache_key = None
    if not platform and not priority and offset == 0:
        cache_key = f"feed:{user_id}"
        cached = await cache.get_feed(user_id)
        if cached:
            return FeedResponse(
                messages=cached[:limit],
                total=len(cached),
                has_more=len(cached) > limit,
            )

    # Build query
    query = select(Message).where(
        Message.user_id == user_id,
        Message.is_done == False,
        Message.snoozed_until == None,
    )

    if platform:
        query = query.where(Message.platform == platform)

    if priority:
        query = query.where(Message.priority_label == priority)

    # Count total
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch sorted by priority_score DESC, then timestamp DESC
    query = query.order_by(
        Message.priority_score.desc(),
        Message.timestamp.desc(),
    ).offset(offset).limit(limit)

    result = await db.execute(query)
    rows = result.scalars().all()

    messages = [_row_to_message_state(row) for row in rows]

    # Cache unfiltered results
    if cache_key and messages:
        await cache.set_feed(user_id, [m.model_dump() for m in messages])

    return FeedResponse(
        messages=messages,
        total=total,
        has_more=(offset + limit) < total,
    )


@router.get("/thread/{platform}/{thread_id}")
async def get_thread(
    platform: str,
    thread_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get full thread messages with AI summary for long threads.
    Threads with >5 messages get an auto-generated summary.
    """
    # Check cache
    cached = await cache.get_thread(platform, thread_id)
    if cached:
        return cached

    # Fetch thread messages
    result = await db.execute(
        select(Message)
        .where(
            Message.user_id == user_id,
            Message.platform == platform,
            Message.thread_id == thread_id,
        )
        .order_by(Message.timestamp.asc())
    )
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = [_row_to_message_state(row) for row in rows]

    # Generate summary for long threads (>5 messages)
    summary = None
    if len(messages) > 5:
        participants = list(set(m.sender.name for m in messages))
        msg_texts = [f"{m.sender.name}: {m.content_text}" for m in messages]
        summary = await summarize_thread(platform, participants, msg_texts)

    response = {
        "messages": [m.model_dump() for m in messages],
        "summary": summary,
        "message_count": len(messages),
    }

    # Cache the result
    await cache.set_thread(platform, thread_id, response)

    return response


@router.patch("/message/{message_id}")
async def update_message(
    message_id: str,
    payload: MessageUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update message state: mark read, mark done, or snooze."""
    result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.user_id == user_id,
        )
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if payload.is_read is not None:
        message.is_read = payload.is_read

    if payload.is_done is not None:
        message.is_done = payload.is_done

    if payload.snoozed_until is not None:
        try:
            snooze_time = datetime.fromisoformat(payload.snoozed_until)
            if snooze_time.tzinfo is None:
                snooze_time = snooze_time.replace(tzinfo=timezone.utc)
            message.snoozed_until = snooze_time
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid snoozed_until format")

    await db.flush()

    # Invalidate feed cache
    await cache.invalidate_feed(user_id)

    return {"success": True}


# --- Helpers ---

def _row_to_message_state(row: Message) -> MessageState:
    """Convert a Message ORM row to a MessageState Pydantic model."""
    return MessageState(
        id=str(row.id),
        user_id=str(row.user_id),
        platform=row.platform,
        platform_message_id=row.platform_message_id,
        thread_id=row.thread_id or "",
        sender=SenderContext(
            id=row.sender_id,
            name=row.sender_name or "",
            email=row.sender_email,
        ),
        content_text=row.content_text or "",
        timestamp=row.timestamp.isoformat() if row.timestamp else "",
        is_read=row.is_read or False,
        is_done=row.is_done or False,
        snoozed_until=row.snoozed_until.isoformat() if row.snoozed_until else None,
        ai_enrichment=AIEnrichment(
            priority_score=row.priority_score or 0.0,
            priority_label=row.priority_label or "fyi",
            sentiment=row.sentiment or "neutral",
            summary=row.summary or "",
            context_note=row.ai_context_note or "",
            suggested_actions=row.suggested_actions or [],
            is_complaint=row.is_complaint or False,
            needs_careful_response=row.needs_careful_response or False,
            suggested_approach=row.suggested_approach or "",
            classification_reasoning=row.classification_reasoning or "",
        ),
        draft_reply=row.draft_reply,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )
