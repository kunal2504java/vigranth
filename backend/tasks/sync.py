"""
Celery background tasks for platform synchronization.

Tasks:
  - sync-all-platforms: every 2 minutes — poll all connected platforms
  - check-snoozed: every 1 minute — unsnooze expired messages

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
    """
    Run async code in a sync Celery task.

    Creates a fresh event loop each time AND disposes the SQLAlchemy
    engine pool afterward, so connections don't leak across loops.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        # Dispose the engine pool to prevent "attached to a different loop"
        # errors on subsequent Celery task invocations.
        try:
            from backend.core.database import engine
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        loop.close()


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
                # Telegram Client API uses Telethon session string
                if cred.platform == "telegram":
                    decrypted_creds["session"] = decrypted_creds["access_token"]

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

                    # Filter out messages that already exist (avoid duplicate key errors)
                    from backend.models.database import Message
                    platform_val = cred.platform
                    existing_ids_result = await db.execute(
                        select(Message.platform_message_id).where(
                            Message.user_id == cred.user_id,
                            Message.platform == platform_val,
                            Message.platform_message_id.in_(
                                [s.platform_message_id for s in states]
                            ),
                        )
                    )
                    existing_ids = {row[0] for row in existing_ids_result.all()}
                    new_states = [
                        s for s in states
                        if s.platform_message_id not in existing_ids
                    ]

                    if new_states:
                        # Process messages sequentially to avoid session
                        # conflicts from concurrent flushes on a shared session.
                        from backend.agents.pipeline import run_pipeline
                        for state in new_states:
                            try:
                                await run_pipeline(state, db)
                            except Exception as msg_err:
                                logger.warning(
                                    f"Pipeline failed for {state.platform_message_id}: {msg_err}"
                                )
                                await db.rollback()
                                # Re-enter transaction for next message
                                continue

                    logger.info(
                        f"Synced {cred.platform} for user {cred.user_id}: "
                        f"{len(new_states)} new, {len(existing_ids)} skipped"
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
            from backend.agents.pipeline import run_pipeline
            states = [adapter.normalize(raw, str(user.id)) for raw in raw_messages]
            for state in states:
                await run_pipeline(state, db)


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


