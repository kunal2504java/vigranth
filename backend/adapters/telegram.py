"""
Telegram Adapter — Client API via Telethon (MTProto).

Reads ALL messages: DMs, groups, channels — authenticates as the user,
not as a bot. Uses StringSession so the session is stored as a string
in the DB (platform_credentials.refresh_token) with no filesystem state.

Auth flow:
  1. POST /api/v1/platforms/telegram/start  → sends OTP to user's phone
  2. POST /api/v1/platforms/telegram/verify  → verifies OTP, stores session
  3. Sync task fetches messages via client.get_messages()
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from telethon import TelegramClient
from telethon.sessions import StringSession

from backend.adapters.base import PlatformAdapter
from backend.agents.state import MessageState, SenderContext, Platform
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _make_client(session_str: str = "") -> TelegramClient:
    """Create a Telethon client with the app's API credentials."""
    return TelegramClient(
        StringSession(session_str),
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )


class TelegramAdapter(PlatformAdapter):
    """Telegram platform adapter using Telethon Client API (MTProto)."""

    # ── Auth flow (called from API endpoints) ────────────────────

    @staticmethod
    async def send_code(phone: str) -> dict:
        """
        Step 1: Send OTP code to the user's phone number.
        Returns phone_code_hash and a temporary session string needed for step 2.
        """
        client = _make_client()
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            session_str = client.session.save()
            return {
                "phone_code_hash": result.phone_code_hash,
                "session": session_str,  # temporary, needed for verify step
            }
        finally:
            await client.disconnect()

    @staticmethod
    async def verify_code(
        phone: str,
        code: str,
        phone_code_hash: str,
        session_str: str,
        password: str = "",
    ) -> dict:
        """
        Step 2: Verify the OTP code and complete authentication.
        Returns the persistent session string to store in DB.
        """
        client = _make_client(session_str)
        await client.connect()
        try:
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except Exception as e:
                # 2FA password required
                if "password" in str(e).lower() or "two" in str(e).lower():
                    if not password:
                        return {"error": "2fa_required", "message": "Two-factor authentication password required"}
                    await client.sign_in(password=password)
                else:
                    raise

            me = await client.get_me()
            final_session = client.session.save()

            return {
                "session": final_session,
                "user_id": str(me.id),
                "username": me.username or "",
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            }
        finally:
            await client.disconnect()

    # ── Message fetching ─────────────────────────────────────────

    async def fetch_new_messages(
        self,
        user_id: str,
        since: datetime,
        credentials: dict,
    ) -> list[dict]:
        """
        Fetch messages from ALL dialogs (DMs, groups, channels) since the given time.
        credentials["session"] is the Telethon StringSession string.
        """
        session_str = credentials.get("session", "")
        if not session_str:
            logger.warning(f"No Telethon session for user {user_id}")
            return []

        client = _make_client(session_str)
        await client.connect()

        if not await client.is_user_authorized():
            logger.error(f"Telethon session expired for user {user_id}")
            return []

        try:
            messages = []
            # Get recent dialogs (last 30 chats with activity)
            async for dialog in client.iter_dialogs(limit=30):
                try:
                    # Fetch messages in this chat since last sync
                    async for msg in client.iter_messages(
                        dialog.entity,
                        offset_date=since,
                        reverse=True,
                        limit=20,
                    ):
                        if msg.date and msg.date >= since and msg.text:
                            sender = await msg.get_sender()
                            sender_name = ""
                            sender_id = ""
                            sender_username = ""

                            if sender:
                                sender_id = str(sender.id)
                                sender_username = getattr(sender, "username", "") or ""
                                first = getattr(sender, "first_name", "") or ""
                                last = getattr(sender, "last_name", "") or ""
                                title = getattr(sender, "title", "") or ""
                                sender_name = f"{first} {last}".strip() or title or sender_username

                            messages.append({
                                "message_id": msg.id,
                                "chat_id": dialog.id,
                                "chat_title": dialog.title or dialog.name or "DM",
                                "chat_type": _chat_type(dialog),
                                "sender_id": sender_id,
                                "sender_name": sender_name,
                                "sender_username": sender_username,
                                "text": msg.text,
                                "date": msg.date.timestamp(),
                                "reply_to": msg.reply_to_msg_id if msg.reply_to else None,
                                "is_outgoing": msg.out,
                            })
                except Exception as e:
                    logger.debug(f"Skipping dialog {dialog.id}: {e}")
                    continue

            # Filter out outgoing messages (we sent them, don't need to triage)
            incoming = [m for m in messages if not m.get("is_outgoing")]
            logger.info(f"Fetched {len(incoming)} incoming Telegram messages for user {user_id}")
            return incoming

        except Exception as e:
            logger.error(f"Telegram fetch failed for user {user_id}: {e}")
            return []
        finally:
            await client.disconnect()

    # ── Normalization ────────────────────────────────────────────

    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert raw Telethon message dict to MessageState."""
        ts = datetime.fromtimestamp(raw_message["date"], tz=timezone.utc)

        return MessageState(
            id=str(uuid4()),
            user_id=user_id,
            platform=Platform.TELEGRAM,
            platform_message_id=str(raw_message["message_id"]),
            thread_id=str(raw_message["chat_id"]),
            sender=SenderContext(
                id=raw_message.get("sender_id", ""),
                name=raw_message.get("sender_name", "Unknown"),
                username=raw_message.get("sender_username"),
            ),
            content_text=raw_message.get("text", ""),
            timestamp=ts.isoformat(),
        )

    # ── Webhook (not used for Client API — sync via polling) ───

    async def setup_webhook(self, user_id: str, webhook_url: str, credentials: dict):
        """Not applicable for Telethon Client API. Messages are polled."""
        return None

    # ── Sending ──────────────────────────────────────────────────

    async def send_message(
        self,
        thread_id: str,
        text: str,
        credentials: dict,
        **kwargs,
    ) -> dict:
        """Send a message to a chat via the user's Telegram account."""
        session_str = credentials.get("session", "")
        if not session_str:
            return {"success": False, "error": "No session"}

        client = _make_client(session_str)
        await client.connect()

        try:
            entity = await client.get_entity(int(thread_id))
            reply_to = kwargs.get("reply_to_message_id")
            msg = await client.send_message(entity, text, reply_to=reply_to)
            logger.info(f"Sent message to Telegram chat {thread_id}")
            return {"success": True, "platform_message_id": str(msg.id)}
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            await client.disconnect()


def _chat_type(dialog) -> str:
    """Determine the chat type from a Telethon dialog."""
    from telethon.tl.types import User, Chat, Channel
    entity = dialog.entity
    if isinstance(entity, User):
        return "private"
    elif isinstance(entity, Chat):
        return "group"
    elif isinstance(entity, Channel):
        return "channel" if entity.broadcast else "supergroup"
    return "unknown"
