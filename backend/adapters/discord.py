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
from datetime import datetime, timezone
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
        # The bot token is stored as access_token in platform_credentials.
        # Fall back to the env var for direct usage / testing.
        bot_token = credentials.get("access_token", settings.DISCORD_BOT_TOKEN)
        return {"Authorization": f"Bot {bot_token}"}

    async def fetch_new_messages(
        self,
        user_id: str,
        since: datetime,
        credentials: dict,
    ) -> list[dict]:
        """
        Fetch new messages from Discord via bot token:
          1. DMs the bot is party to
          2. Text channels in all guilds the bot has joined

        Uses the bot token (from env var or credentials["access_token"]).
        """
        try:
            headers = self._get_headers(credentials)
            messages = []
            since_ts = since.timestamp()

            async with httpx.AsyncClient(timeout=30) as client:

                # ── 1. DMs ────────────────────────────────────────────────
                dm_response = await client.get(
                    f"{DISCORD_API_BASE}/users/@me/channels",
                    headers=headers,
                )
                dm_channels = dm_response.json() if dm_response.status_code == 200 else []

                # ── 2. Guild text channels ────────────────────────────────
                guild_channels = []
                guilds_response = await client.get(
                    f"{DISCORD_API_BASE}/users/@me/guilds",
                    headers=headers,
                )
                if guilds_response.status_code == 200:
                    for guild in guilds_response.json():
                        ch_response = await client.get(
                            f"{DISCORD_API_BASE}/guilds/{guild['id']}/channels",
                            headers=headers,
                        )
                        if ch_response.status_code == 200:
                            # type 0 = GUILD_TEXT, type 5 = GUILD_ANNOUNCEMENT
                            text_channels = [
                                {**ch, "guild_name": guild.get("name", "")}
                                for ch in ch_response.json()
                                if ch.get("type") in (0, 5)
                            ]
                            guild_channels.extend(text_channels)

                # ── 3. Fetch messages from all channels ───────────────────
                all_channels = [
                    *[{**ch, "guild_name": "DM"} for ch in dm_channels],
                    *guild_channels,
                ]

                for channel in all_channels:
                    try:
                        msg_response = await client.get(
                            f"{DISCORD_API_BASE}/channels/{channel['id']}/messages",
                            headers=headers,
                            params={"limit": 50},
                        )
                        if msg_response.status_code != 200:
                            continue

                        for msg in msg_response.json():
                            msg_time = datetime.fromisoformat(
                                msg["timestamp"].replace("Z", "+00:00")
                            )
                            if msg_time.timestamp() < since_ts:
                                continue
                            # Skip bot messages
                            if msg.get("author", {}).get("bot"):
                                continue
                            msg["channel_id"] = channel["id"]
                            msg["channel_type"] = channel.get("type", 1)
                            msg["guild_name"] = channel.get("guild_name", "")
                            msg["channel_name"] = channel.get("name", "")
                            messages.append(msg)
                    except Exception as e:
                        logger.debug(f"Skipping Discord channel {channel['id']}: {e}")
                        continue

            logger.info(f"Fetched {len(messages)} Discord messages for user {user_id}")
            return messages

        except Exception as e:
            logger.error(f"Discord fetch failed for user {user_id}: {e}")
            return []

    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert raw Discord message to MessageState."""
        author = raw_message.get("author", {})
        guild_name = raw_message.get("guild_name", "")
        channel_name = raw_message.get("channel_name", "")

        # Build a readable subject: "ServerName #channel-name" or "DM"
        if guild_name and guild_name != "DM" and channel_name:
            subject = f"{guild_name} #{channel_name}"
        elif channel_name:
            subject = f"#{channel_name}"
        else:
            subject = "DM"

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
            # Prepend server/channel context to content so the AI pipeline
            # has full context about where the message came from
            content_text=f"[{subject}] {raw_message.get('content', '')}".strip(),
            timestamp=raw_message.get("timestamp", datetime.now(timezone.utc).isoformat()),
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
                            "intents": 37376,  # GUILDS(1) | GUILD_MESSAGES(512) | DIRECT_MESSAGES(4096) | MESSAGE_CONTENT(32768)
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
