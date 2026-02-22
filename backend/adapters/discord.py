"""
Discord Adapter — connects via Discord Bot API + Gateway WebSocket.

From Integration Spec Section 1.5:
  - Bot Permissions: Read Messages, Send Messages, Read Message History
  - OAuth Scopes: bot, identify, messages.read
  - API Base URL: https://discord.com/api/v10
  - Realtime: Discord Gateway (persistent WebSocket)
  - Events: MESSAGE_CREATE, DIRECT_MESSAGE_CREATE
  - Rate Limit: 50 req/sec global, 5 req/sec per route
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Callable, Awaitable
from uuid import uuid4

import httpx
import websockets

from backend.adapters.base import PlatformAdapter
from backend.agents.state import MessageState, SenderContext, Platform
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"


class DiscordAdapter(PlatformAdapter):
    """Discord platform adapter using Discord API + Gateway."""

    def _get_headers(self, credentials: dict) -> dict:
        bot_token = credentials.get("bot_token", settings.DISCORD_BOT_TOKEN)
        return {"Authorization": f"Bot {bot_token}"}

    async def fetch_new_messages(
        self,
        user_id: str,
        since: datetime,
        credentials: dict,
    ) -> list[dict]:
        """Fetch recent DM messages from Discord."""
        try:
            headers = self._get_headers(credentials)
            messages = []

            async with httpx.AsyncClient(timeout=30) as client:
                # Get DM channels
                dm_response = await client.get(
                    f"{DISCORD_API_BASE}/users/@me/channels",
                    headers=headers,
                )

                if dm_response.status_code != 200:
                    logger.error(f"Discord DM channels fetch failed: {dm_response.status_code}")
                    return []

                channels = dm_response.json()

                for channel in channels:
                    try:
                        # Fetch messages from each DM channel
                        msg_response = await client.get(
                            f"{DISCORD_API_BASE}/channels/{channel['id']}/messages",
                            headers=headers,
                            params={"limit": 50},
                        )

                        if msg_response.status_code == 200:
                            for msg in msg_response.json():
                                # Filter by timestamp
                                msg_time = datetime.fromisoformat(
                                    msg["timestamp"].replace("Z", "+00:00")
                                )
                                if msg_time >= since:
                                    msg["channel_id"] = channel["id"]
                                    msg["channel_type"] = channel.get("type", 1)
                                    messages.append(msg)
                    except Exception as e:
                        logger.warning(f"Failed to fetch Discord channel {channel['id']}: {e}")
                        continue

            logger.info(f"Fetched {len(messages)} Discord messages for user {user_id}")
            return messages

        except Exception as e:
            logger.error(f"Discord fetch failed for user {user_id}: {e}")
            return []

    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert raw Discord message to MessageState."""
        author = raw_message.get("author", {})

        return MessageState(
            id=str(uuid4()),
            user_id=user_id,
            platform=Platform.DISCORD,
            platform_message_id=raw_message.get("id", ""),
            thread_id=raw_message.get("channel_id", ""),
            sender=SenderContext(
                id=author.get("id", ""),
                name=author.get("global_name") or author.get("username", "Unknown"),
                username=author.get("username"),
            ),
            content_text=raw_message.get("content", ""),
            timestamp=raw_message.get("timestamp", datetime.utcnow().isoformat()),
        )

    async def send_message(
        self,
        thread_id: str,
        text: str,
        credentials: dict,
        **kwargs,
    ) -> dict:
        """Send a message to a Discord channel."""
        try:
            headers = self._get_headers(credentials)
            channel_id = kwargs.get("channel_id", thread_id)

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                    headers=headers,
                    json={"content": text},
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Sent Discord message to channel {channel_id}")
                    return {"success": True, "platform_message_id": data.get("id")}
                else:
                    error = response.json().get("message", "Unknown error")
                    return {"success": False, "error": error}

        except Exception as e:
            logger.error(f"Discord send failed: {e}")
            return {"success": False, "error": str(e)}

    async def setup_webhook(
        self,
        user_id: str,
        webhook_url: str,
        credentials: dict,
    ) -> Optional[str]:
        """
        Discord uses Gateway WebSocket for realtime events, not HTTP webhooks.
        This starts the gateway listener as a background task.
        """
        logger.info(
            f"Discord uses Gateway WebSocket. "
            f"Use DiscordGateway.connect() for realtime events."
        )
        return f"discord-gateway-{user_id}"

    async def refresh_credentials(self, credentials: dict) -> Optional[dict]:
        """Refresh Discord OAuth token."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DISCORD_API_BASE}/oauth2/token",
                    data={
                        "client_id": settings.DISCORD_CLIENT_ID,
                        "client_secret": settings.DISCORD_CLIENT_SECRET,
                        "grant_type": "refresh_token",
                        "refresh_token": credentials.get("refresh_token"),
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "access_token": data["access_token"],
                        "refresh_token": data.get("refresh_token", credentials.get("refresh_token")),
                    }
        except Exception as e:
            logger.error(f"Discord token refresh failed: {e}")
        return None


class DiscordGateway:
    """
    Persistent WebSocket connection to Discord Gateway.
    Receives realtime MESSAGE_CREATE events.
    """

    def __init__(self):
        self._ws = None
        self._heartbeat_task = None
        self._running = False

    async def connect(
        self,
        bot_token: str,
        on_message: Callable[[dict], Awaitable[None]],
    ):
        """Connect to Discord Gateway and listen for messages."""
        self._running = True

        while self._running:
            try:
                async with websockets.connect(DISCORD_GATEWAY_URL) as ws:
                    self._ws = ws

                    # Receive Hello
                    hello = json.loads(await ws.recv())
                    heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000

                    # Identify
                    await ws.send(json.dumps({
                        "op": 2,
                        "d": {
                            "token": bot_token,
                            "intents": 4608,  # GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES
                            "properties": {
                                "os": "linux",
                                "browser": "unifyinbox",
                                "device": "unifyinbox",
                            },
                        },
                    }))

                    # Start heartbeat
                    self._heartbeat_task = asyncio.create_task(
                        self._heartbeat(ws, heartbeat_interval)
                    )

                    # Listen for events
                    async for raw in ws:
                        event = json.loads(raw)
                        if event.get("t") == "MESSAGE_CREATE":
                            await on_message(event["d"])

            except websockets.ConnectionClosed:
                logger.warning("Discord Gateway connection closed, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Discord Gateway error: {e}")
                await asyncio.sleep(10)

    async def disconnect(self):
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._ws:
            await self._ws.close()

    async def _heartbeat(self, ws, interval: float):
        """Send periodic heartbeat to keep connection alive."""
        while self._running:
            try:
                await asyncio.sleep(interval)
                await ws.send(json.dumps({"op": 1, "d": None}))
            except Exception:
                break
