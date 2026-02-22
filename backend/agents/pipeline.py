"""
Agent Pipeline Orchestrator — runs the full AI enrichment pipeline.

Pipeline flow (from Architecture doc Section 2.2):

  New Message
      |
      v
  Reader Agent (normalize - done by adapters)
      |
      +--- asyncio.gather() (parallel) ---+
      |              |                     |
  Context Builder  Classifier         Sentiment
      |              |                     |
      +--- merge enrichments on state -----+
      |
      v
  Priority Ranker (deterministic, weighted scoring)
      |
      v
  Save to DB + push via WebSocket
      |
      v  (on user click)
  Draft Reply Agent (claude-sonnet)
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.state import MessageState
from backend.agents.context_builder import build_context
from backend.agents.classifier import classify_message
from backend.agents.sentiment import detect_sentiment
from backend.agents.priority_ranker import compute_priority
from backend.models.database import Message, Contact
from backend.core.vector_store import embed_message

logger = logging.getLogger(__name__)


async def run_pipeline(
    state: MessageState,
    db: AsyncSession,
    ws_manager=None,
) -> MessageState:
    """
    Run the full agent pipeline for a single message.

    Steps:
      1. Fetch sender history from DB for context
      2. Run Context Builder, Classifier, Sentiment in parallel
      3. Run Priority Ranker (needs outputs from step 2)
      4. Persist to database
      5. Embed in vector store
      6. Push to WebSocket clients
    """
    try:
        # --- Step 0: Gather sender history ---
        interaction_history, reply_count, total_messages = await _get_sender_stats(
            db, state.user_id, state.sender.id, state.platform
        )

        # --- Step 1: Run enrichment agents in parallel ---
        # Context Builder needs history; Classifier & Sentiment are independent
        results = await asyncio.gather(
            build_context(
                state,
                interaction_history=interaction_history,
                reply_count=reply_count,
                total_messages=total_messages,
            ),
            classify_message(state),
            detect_sentiment(state),
            return_exceptions=True,
        )

        # Handle individual agent failures gracefully
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_names = ["context_builder", "classifier", "sentiment"]
                logger.error(f"Agent {agent_names[i]} failed: {result}")

        # The state object is mutated in place by each agent, so it's
        # already enriched regardless of which completed successfully.

        # --- Step 2: Get thread activity for priority ranker ---
        thread_msg_count, thread_recent = await _get_thread_activity(
            db, state.user_id, state.thread_id
        )

        # --- Step 3: Run Priority Ranker (deterministic, needs all enrichments) ---
        state = await compute_priority(
            state,
            thread_message_count=thread_msg_count,
            thread_recent_replies=thread_recent,
        )

        # --- Step 4: Persist to database ---
        await _upsert_message(db, state)

        # --- Step 5: Update contact record ---
        await _upsert_contact(db, state)

        # --- Step 6: Embed in vector store (fire-and-forget) ---
        asyncio.create_task(_safe_embed(state))

        # --- Step 7: Push to WebSocket clients ---
        if ws_manager:
            await ws_manager.push_to_user(
                state.user_id,
                "new_message",
                state.model_dump(),
            )

        logger.info(
            f"Pipeline complete for message {state.id}: "
            f"priority={state.ai_enrichment.priority_score:.2f} "
            f"label={state.ai_enrichment.priority_label} "
            f"sentiment={state.ai_enrichment.sentiment}"
        )

    except Exception as e:
        logger.error(f"Pipeline failed for message {state.id}: {e}", exc_info=True)
        # Still try to save the message even if enrichment partially failed
        try:
            await _upsert_message(db, state)
        except Exception as save_err:
            logger.error(f"Failed to save message {state.id}: {save_err}")

    return state


async def run_pipeline_batch(
    states: list[MessageState],
    db: AsyncSession,
    ws_manager=None,
    max_concurrent: int = 5,
) -> list[MessageState]:
    """
    Process multiple messages through the pipeline with concurrency control.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_one(state: MessageState) -> MessageState:
        async with semaphore:
            return await run_pipeline(state, db, ws_manager)

    results = await asyncio.gather(
        *(process_one(s) for s in states),
        return_exceptions=True,
    )

    processed = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Batch pipeline failed for message {states[i].id}: {result}")
            processed.append(states[i])
        else:
            processed.append(result)

    return processed


# --- Internal helpers ---

async def _get_sender_stats(
    db: AsyncSession,
    user_id: str,
    sender_id: str,
    platform: str,
) -> tuple[list[str], int, int]:
    """Fetch sender interaction history from database."""
    try:
        # Get recent messages from this sender
        result = await db.execute(
            select(Message.content_text, Message.is_read)
            .where(
                Message.user_id == user_id,
                Message.sender_id == sender_id,
                Message.platform == platform,
            )
            .order_by(Message.timestamp.desc())
            .limit(20)
        )
        rows = result.all()

        history = [row[0] for row in rows if row[0]]
        total = len(rows)
        replied = sum(1 for row in rows if row[1])  # is_read as proxy for replied

        return history, replied, total
    except Exception as e:
        logger.warning(f"Failed to get sender stats: {e}")
        return [], 0, 0


async def _get_thread_activity(
    db: AsyncSession,
    user_id: str,
    thread_id: str,
) -> tuple[int, int]:
    """Get thread message count and recent reply count."""
    try:
        result = await db.execute(
            select(func.count(Message.id))
            .where(
                Message.user_id == user_id,
                Message.thread_id == thread_id,
            )
        )
        total = result.scalar() or 1

        # Count messages in last 24 hours
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await db.execute(
            select(func.count(Message.id))
            .where(
                Message.user_id == user_id,
                Message.thread_id == thread_id,
                Message.timestamp >= cutoff,
            )
        )
        recent = result.scalar() or 0

        return total, recent
    except Exception as e:
        logger.warning(f"Failed to get thread activity: {e}")
        return 1, 0


async def _upsert_message(db: AsyncSession, state: MessageState) -> None:
    """Insert or update a message in the database."""
    # Check if message already exists
    result = await db.execute(
        select(Message).where(
            Message.user_id == state.user_id,
            Message.platform == (state.platform if isinstance(state.platform, str) else state.platform.value),
            Message.platform_message_id == state.platform_message_id,
        )
    )
    existing = result.scalar_one_or_none()

    platform_val = state.platform if isinstance(state.platform, str) else state.platform.value

    if existing:
        # Update AI enrichments
        existing.priority_score = state.ai_enrichment.priority_score
        existing.priority_label = state.ai_enrichment.priority_label
        existing.sentiment = state.ai_enrichment.sentiment
        existing.ai_context_note = state.ai_enrichment.context_note
        existing.summary = state.ai_enrichment.summary
        existing.classification_reasoning = state.ai_enrichment.classification_reasoning
        existing.is_complaint = state.ai_enrichment.is_complaint
        existing.needs_careful_response = state.ai_enrichment.needs_careful_response
        existing.suggested_approach = state.ai_enrichment.suggested_approach
        existing.suggested_actions = state.ai_enrichment.suggested_actions
        existing.processed_at = datetime.now(timezone.utc)
    else:
        msg = Message(
            id=state.id,
            user_id=state.user_id,
            platform=platform_val,
            platform_message_id=state.platform_message_id,
            thread_id=state.thread_id,
            sender_id=state.sender.id,
            sender_name=state.sender.name,
            sender_email=state.sender.email,
            content_text=state.content_text,
            timestamp=_parse_timestamp(state.timestamp),
            is_read=state.is_read,
            is_done=state.is_done,
            priority_score=state.ai_enrichment.priority_score,
            priority_label=state.ai_enrichment.priority_label,
            sentiment=state.ai_enrichment.sentiment,
            ai_context_note=state.ai_enrichment.context_note,
            summary=state.ai_enrichment.summary,
            classification_reasoning=state.ai_enrichment.classification_reasoning,
            is_complaint=state.ai_enrichment.is_complaint,
            needs_careful_response=state.ai_enrichment.needs_careful_response,
            suggested_approach=state.ai_enrichment.suggested_approach,
            suggested_actions=state.ai_enrichment.suggested_actions,
            draft_reply=state.draft_reply,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(msg)

    await db.flush()


async def _upsert_contact(db: AsyncSession, state: MessageState) -> None:
    """Update or create contact record."""
    try:
        platform_val = state.platform if isinstance(state.platform, str) else state.platform.value

        result = await db.execute(
            select(Contact).where(
                Contact.user_id == state.user_id,
                Contact.platform == platform_val,
                Contact.contact_identifier == state.sender.id,
            )
        )
        contact = result.scalar_one_or_none()

        if contact:
            contact.display_name = state.sender.name
            contact.relationship = state.sender.relationship
            contact.is_vip = state.sender.is_vip
            contact.reply_rate = state.sender.historical_reply_rate
            contact.message_count = (contact.message_count or 0) + 1
            contact.last_interaction = datetime.now(timezone.utc)
        else:
            contact = Contact(
                user_id=state.user_id,
                contact_identifier=state.sender.id,
                platform=platform_val,
                display_name=state.sender.name,
                relationship=state.sender.relationship,
                is_vip=state.sender.is_vip,
                reply_rate=state.sender.historical_reply_rate,
                message_count=1,
                last_interaction=datetime.now(timezone.utc),
            )
            db.add(contact)

        await db.flush()
    except Exception as e:
        logger.warning(f"Failed to upsert contact: {e}")


async def _safe_embed(state: MessageState) -> None:
    """Embed message in vector store, swallow errors."""
    try:
        platform_val = state.platform if isinstance(state.platform, str) else state.platform.value
        await embed_message(
            message_id=state.id,
            content=state.content_text,
            user_id=state.user_id,
            platform=platform_val,
            sender_id=state.sender.id,
            timestamp=state.timestamp,
        )
    except Exception as e:
        logger.warning(f"Failed to embed message {state.id}: {e}")


def _parse_timestamp(ts: str) -> datetime:
    """Parse a timestamp string to datetime."""
    try:
        if "T" in ts:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
