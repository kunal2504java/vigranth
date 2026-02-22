"""
Telegram Adapter — connects via Telegram Bot API.

From Integration Spec Section 1.4:
  - API Base URL: https://api.telegram.org/bot{token}/
  - Realtime: setWebhook (prod) or getUpdates long polling (dev)
  - Rate Limit: 30 msg/sec to different chats, 20 msg/min to same chat
  - Auth: Bot Token from BotFather
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

import httpx

from backend.adapters.base import PlatformAdapter
from backend.agents.state import MessageState, SenderContext, Platform
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TelegramAdapter(PlatformAdapter):
    """Telegram platform adapter using Telegram Bot API."""

    def _api_url(self, method: str, bot_token: Optional[str] = None) -> str:
        token = bot_token or settings.TELEGRAM_BOT_TOKEN
        return f"https://api.telegram.org/bot{token}/{method}"

    async def fetch_new_messages(
        self,
        user_id: str,
        since: datetime,
        credentials: dict,
    ) -> list[dict]:
        """
        Fetch new messages via getUpdates (long polling).
        In production, webhooks are preferred — this is for dev/fallback.
        """
        try:
            bot_token = credentials.get("bot_token", settings.TELEGRAM_BOT_TOKEN)
            offset = credentials.get("last_update_id", 0)

            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.get(
                    self._api_url("getUpdates", bot_token),
                    params={
                        "offset": offset + 1 if offset else 0,
                        "timeout": 30,
                        "allowed_updates": '["message","edited_message"]',
                    },
                )
                data = response.json()

                if not data.get("ok"):
                    logger.error(f"Telegram getUpdates failed: {data.get('description')}")
                    return []

                messages = []
                for update in data.get("result", []):
                    msg = update.get("message") or update.get("edited_message")
                    if msg and msg.get("date", 0) >= int(since.timestamp()):
                        msg["_update_id"] = update["update_id"]
                        messages.append(msg)

                logger.info(f"Fetched {len(messages)} Telegram messages for user {user_id}")
                return messages

        except Exception as e:
            logger.error(f"Telegram fetch failed for user {user_id}: {e}")
            return []

    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert raw Telegram message to MessageState."""
        from_user = raw_message.get("from", {})
        chat = raw_message.get("chat", {})

        sender_name = " ".join(
            filter(None, [from_user.get("first_name"), from_user.get("last_name")])
        ) or from_user.get("username", "Unknown")

        return MessageState(
            id=str(uuid4()),
            user_id=user_id,
            platform=Platform.TELEGRAM,
            platform_message_id=str(raw_message.get("message_id", "")),
            thread_id=str(chat.get("id", "")),
            sender=SenderContext(
                id=str(from_user.get("id", "")),
                name=sender_name,
                username=from_user.get("username"),
            ),
            content_text=raw_message.get("text", ""),
            timestamp=datetime.utcfromtimestamp(
                raw_message.get("date", 0)
            ).isoformat(),
        )

    async def send_message(
        self,
        thread_id: str,
        text: str,
        credentials: dict,
        **kwargs,
    ) -> dict:
        """Send a message via Telegram Bot API."""
        try:
            bot_token = credentials.get("bot_token", settings.TELEGRAM_BOT_TOKEN)
            chat_id = kwargs.get("chat_id", thread_id)
            reply_to = kwargs.get("reply_to_message_id")

            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            if reply_to:
                payload["reply_to_message_id"] = reply_to

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._api_url("sendMessage", bot_token),
                    json=payload,
                )
                data = response.json()

                if data.get("ok"):
                    msg_id = data["result"]["message_id"]
                    logger.info(f"Sent Telegram message to chat {chat_id}")
                    return {"success": True, "platform_message_id": str(msg_id)}
                else:
                    return {"success": False, "error": data.get("description", "Unknown error")}

        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return {"success": False, "error": str(e)}

    async def setup_webhook(
        self,
        user_id: str,
        webhook_url: str,
        credentials: dict,
    ) -> Optional[str]:
        """Register a Telegram webhook for realtime messages."""
        try:
            bot_token = credentials.get("bot_token", settings.TELEGRAM_BOT_TOKEN)
            full_url = f"{webhook_url}/webhooks/telegram/{user_id}"

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._api_url("setWebhook", bot_token),
                    json={
                        "url": full_url,
                        "allowed_updates": ["message", "edited_message"],
                        "drop_pending_updates": True,
                    },
                )
                data = response.json()

                if data.get("ok"):
                    logger.info(f"Telegram webhook set for user {user_id}")
                    return f"telegram-webhook-{user_id}"
                else:
                    logger.error(f"Telegram webhook setup failed: {data.get('description')}")
                    return None

        except Exception as e:
            logger.error(f"Telegram webhook setup error: {e}")
            return None
