"""
Celery background tasks for platform synchronization.

From Architecture doc Section 6.3:
  - sync-all-platforms: every 2 minutes — poll all connected platforms
  - check-snoozed: every 1 minute — unsnooze expired messages
  - decay-scores: every 1 hour — recalculate priority for time decay

These tasks run in the Celery worker process and use synchronous
DB access (since Celery doesn't support async natively).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.core.celery_app import celery
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _run_async(coro):
    """Helper to run async code in a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new loop if the current one is running
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# --- Main sync tasks ---

@celery.task(name="backend.tasks.sync.sync_all_users", bind=True, max_retries=3)
def sync_all_users(self):
    """
    Periodic task: sync messages for all users across all connected platforms.
    Runs every 2 minutes via Celery Beat.
    """
    _run_async(_async_sync_all_users())


async def _async_sync_all_users():
    """Async implementation of sync_all_users."""
    from sqlalchemy import select
    from backend.core.database import get_db_context
    from backend.models.database import PlatformCredential, SyncState
    from backend.core.security import decrypt_token
    from backend.adapters.registry import get_adapter
    from backend.agents.pipeline import run_pipeline_batch

    async with get_db_context() as db:
        # Get all connected platform credentials
        result = await db.execute(select(PlatformCredential))
        credentials = result.scalars().all()

        logger.info(f"Starting sync for {len(credentials)} platform connections")

        for cred in credentials:
            try:
                adapter = get_adapter(cred.platform)
                if not adapter:
                    continue

                # Get last sync time
                sync_result = await db.execute(
                    select(SyncState).where(
                        SyncState.user_id == cred.user_id,
                        SyncState.platform == cred.platform,
                    )
                )
                sync_state = sync_result.scalar_one_or_none()

                since = datetime.now(timezone.utc) - timedelta(hours=24)
                if sync_state and sync_state.last_sync_at:
                    since = sync_state.last_sync_at

                # Update sync status
                if sync_state:
                    sync_state.status = "syncing"
                else:
                    sync_state = SyncState(
                        user_id=cred.user_id,
                        platform=cred.platform,
                        status="syncing",
                    )
                    db.add(sync_state)
                await db.flush()

                # Decrypt credentials
                decrypted_creds = {
                    "access_token": decrypt_token(cred.access_token),
                }
                if cred.refresh_token:
                    decrypted_creds["refresh_token"] = decrypt_token(cred.refresh_token)

                # Fetch new messages
                raw_messages = await adapter.fetch_new_messages(
                    user_id=str(cred.user_id),
                    since=since,
                    credentials=decrypted_creds,
                )

                if raw_messages:
                    # Normalize messages
                    states = [
                        adapter.normalize(raw, str(cred.user_id))
                        for raw in raw_messages
                    ]

                    # Run through AI pipeline
                    await run_pipeline_batch(states, db, max_concurrent=3)

                    logger.info(
                        f"Synced {len(states)} messages from {cred.platform} "
                        f"for user {cred.user_id}"
                    )

                # Update sync state
                sync_state.last_sync_at = datetime.now(timezone.utc)
                sync_state.status = "idle"
                sync_state.error_message = None
                await db.flush()

            except Exception as e:
                logger.error(
                    f"Sync failed for {cred.platform} user {cred.user_id}: {e}"
                )
                if sync_state:
                    sync_state.status = "error"
                    sync_state.error_message = str(e)[:500]
                    await db.flush()


@celery.task(name="backend.tasks.sync.sync_platform_for_user", bind=True, max_retries=3)
def sync_platform_for_user(self, user_email: str = "", platform: str = "", history_id: str = ""):
    """
    Sync a specific platform for a specific user.
    Triggered by webhook events (e.g., Gmail push notification).
    """
    _run_async(_async_sync_user_platform(user_email, platform, history_id))


async def _async_sync_user_platform(user_email: str, platform: str, history_id: str):
    """Async implementation of single-user platform sync."""
    from sqlalchemy import select
    from backend.core.database import get_db_context
    from backend.models.database import User, PlatformCredential
    from backend.core.security import decrypt_token
    from backend.adapters.registry import get_adapter
    from backend.agents.pipeline import run_pipeline_batch

    async with get_db_context() as db:
        # Find user by email
        result = await db.execute(select(User).where(User.email == user_email))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(f"No user found for email {user_email}")
            return

        # Get credentials
        cred_result = await db.execute(
            select(PlatformCredential).where(
                PlatformCredential.user_id == user.id,
                PlatformCredential.platform == platform,
            )
        )
        cred = cred_result.scalar_one_or_none()
        if not cred:
            return

        adapter = get_adapter(platform)
        if not adapter:
            return

        decrypted_creds = {
            "access_token": decrypt_token(cred.access_token),
        }
        if cred.refresh_token:
            decrypted_creds["refresh_token"] = decrypt_token(cred.refresh_token)

        since = datetime.now(timezone.utc) - timedelta(minutes=10)
        raw_messages = await adapter.fetch_new_messages(
            user_id=str(user.id),
            since=since,
            credentials=decrypted_creds,
        )

        if raw_messages:
            states = [adapter.normalize(raw, str(user.id)) for raw in raw_messages]
            await run_pipeline_batch(states, db, max_concurrent=3)


@celery.task(name="backend.tasks.sync.process_webhook_message", bind=True)
def process_webhook_message(self, platform: str = "", raw_data: dict = None):
    """
    Process a single message received via webhook.
    Called by webhook endpoints for realtime message processing.
    """
    if not raw_data:
        return
    _run_async(_async_process_webhook(platform, raw_data))


async def _async_process_webhook(platform: str, raw_data: dict):
    """Async implementation of webhook message processing."""
    from sqlalchemy import select
    from backend.core.database import get_db_context
    from backend.models.database import PlatformCredential
    from backend.adapters.registry import get_adapter
    from backend.agents.pipeline import run_pipeline

    adapter = get_adapter(platform)
    if not adapter:
        return

    async with get_db_context() as db:
        # For Slack/Telegram, we need to find the user from the webhook data
        user_id = raw_data.get("user_id")

        if not user_id and platform == "slack":
            team_id = raw_data.get("team")
            if team_id:
                result = await db.execute(
                    select(PlatformCredential).where(
                        PlatformCredential.platform == "slack",
                        PlatformCredential.platform_user_id == team_id,
                    )
                )
                cred = result.scalar_one_or_none()
                if cred:
                    user_id = str(cred.user_id)

        if not user_id:
            logger.warning(f"Could not determine user for {platform} webhook")
            return

        state = adapter.normalize(raw_data, user_id)
        await run_pipeline(state, db)


# --- Periodic maintenance tasks ---

@celery.task(name="backend.tasks.sync.check_snoozed_messages")
def check_snoozed_messages():
    """
    Periodic task: check for snoozed messages that should resurface.
    Runs every 1 minute.
    """
    _run_async(_async_check_snoozed())


async def _async_check_snoozed():
    """Unsnooze messages whose snooze time has expired."""
    from sqlalchemy import select
    from backend.core.database import get_db_context
    from backend.models.database import Message
    from backend.core.pubsub import publish_to_user

    now = datetime.now(timezone.utc)

    async with get_db_context() as db:
        result = await db.execute(
            select(Message).where(
                Message.snoozed_until != None,
                Message.snoozed_until <= now,
                Message.is_done == False,
            )
        )
        expired = result.scalars().all()

        for msg in expired:
            msg.snoozed_until = None
            await db.flush()

            # Notify via Redis Pub/Sub -> relayed to WebSocket by FastAPI process
            await publish_to_user(
                str(msg.user_id),
                "new_message",
                {
                    "id": str(msg.id),
                    "platform": msg.platform,
                    "priority_score": msg.priority_score,
                    "priority_label": msg.priority_label,
                    "unsnooze": True,
                },
            )

        if expired:
            logger.info(f"Unsnoozed {len(expired)} messages")


@celery.task(name="backend.tasks.sync.recalculate_priority_scores")
def recalculate_priority_scores():
    """
    Periodic task: apply time decay to priority scores.
    Messages older than 24hrs gradually lose priority.
    Runs every 1 hour.
    """
    _run_async(_async_decay_scores())


async def _async_decay_scores():
    """Apply time decay to message priority scores."""
    from sqlalchemy import select
    from backend.core.database import get_db_context
    from backend.models.database import Message
    from backend.core.redis import cache

    now = datetime.now(timezone.utc)
    decay_threshold = now - timedelta(hours=24)

    async with get_db_context() as db:
        # Get messages older than 24hrs that aren't done
        result = await db.execute(
            select(Message).where(
                Message.is_done == False,
                Message.timestamp < decay_threshold,
                Message.priority_score > 0.1,
            )
        )
        messages = result.scalars().all()

        affected_users = set()
        for msg in messages:
            age_hours = (now - msg.timestamp).total_seconds() / 3600

            # Apply decay: reduce score by 5% per 12 hours past 24hrs
            decay_periods = (age_hours - 24) / 12
            decay_factor = max(0.3, 1.0 - (decay_periods * 0.05))

            new_score = round(msg.priority_score * decay_factor, 3)
            new_score = max(0.05, new_score)  # floor at 0.05

            if new_score != msg.priority_score:
                msg.priority_score = new_score
                affected_users.add(str(msg.user_id))

        await db.flush()

        # Invalidate feed caches for affected users
        for uid in affected_users:
            await cache.invalidate_feed(uid)

        if messages:
            logger.info(f"Decayed scores for {len(messages)} messages across {len(affected_users)} users")
