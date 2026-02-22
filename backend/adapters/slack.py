"""
Slack Adapter — connects to Slack Web API via OAuth2.

From Integration Spec Section 1.3:
  - OAuth Endpoint: https://slack.com/oauth/v2/authorize
  - Scopes: channels:history, im:history, chat:write, users:read
  - Realtime: Slack Events API (webhooks)
  - Rate Limits: Tier 1: 1/sec, Tier 2: 20/min, Tier 3: 50/min
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

SLACK_API_BASE = "https://slack.com/api"


class SlackAdapter(PlatformAdapter):
    """Slack platform adapter using Slack Web API."""

    def _get_headers(self, credentials: dict) -> dict:
        return {"Authorization": f"Bearer {credentials.get('access_token', '')}"}

    async def fetch_new_messages(
        self,
        user_id: str,
        since: datetime,
        credentials: dict,
    ) -> list[dict]:
        """Fetch new DMs and channel messages from Slack."""
        try:
            headers = self._get_headers(credentials)
            messages = []

            async with httpx.AsyncClient(timeout=30) as client:
                # Get DM conversations
                conv_response = await client.get(
                    f"{SLACK_API_BASE}/conversations.list",
                    headers=headers,
                    params={"types": "im,mpim", "limit": 100},
                )
                conv_data = conv_response.json()

                if not conv_data.get("ok"):
                    logger.error(f"Slack conversations.list failed: {conv_data.get('error')}")
                    return []

                for channel in conv_data.get("channels", []):
                    try:
                        history_response = await client.get(
                            f"{SLACK_API_BASE}/conversations.history",
                            headers=headers,
                            params={
                                "channel": channel["id"],
                                "oldest": str(since.timestamp()),
                                "limit": 50,
                            },
                        )
                        history_data = history_response.json()

                        if history_data.get("ok"):
                            for msg in history_data.get("messages", []):
                                msg["channel_id"] = channel["id"]
                                msg["channel_name"] = channel.get("name", "DM")
                                messages.append(msg)
                    except Exception as e:
                        logger.warning(f"Failed to fetch Slack channel {channel['id']}: {e}")
                        continue

            logger.info(f"Fetched {len(messages)} Slack messages for user {user_id}")
            return messages

        except Exception as e:
            logger.error(f"Slack fetch failed for user {user_id}: {e}")
            return []

    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert raw Slack message to MessageState."""
        sender_id = raw_message.get("user", "unknown")

        return MessageState(
            id=str(uuid4()),
            user_id=user_id,
            platform=Platform.SLACK,
            platform_message_id=raw_message.get("ts", ""),
            thread_id=raw_message.get("thread_ts", raw_message.get("ts", "")),
            sender=SenderContext(
                id=sender_id,
                name=raw_message.get("username", sender_id),
                username=raw_message.get("username"),
            ),
            content_text=raw_message.get("text", ""),
            timestamp=self._ts_to_iso(raw_message.get("ts", "")),
        )

    async def send_message(
        self,
        thread_id: str,
        text: str,
        credentials: dict,
        **kwargs,
    ) -> dict:
        """Send a message via Slack chat.postMessage."""
        try:
            channel = kwargs.get("channel_id", "")
            headers = self._get_headers(credentials)

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{SLACK_API_BASE}/chat.postMessage",
                    headers=headers,
                    json={
                        "channel": channel,
                        "text": text,
                        "thread_ts": thread_id,
                    },
                )
                data = response.json()

                if data.get("ok"):
                    logger.info(f"Sent Slack message in thread {thread_id}")
                    return {"success": True, "platform_message_id": data.get("ts")}
                else:
                    return {"success": False, "error": data.get("error", "Unknown error")}

        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return {"success": False, "error": str(e)}

    async def setup_webhook(
        self,
        user_id: str,
        webhook_url: str,
        credentials: dict,
    ) -> Optional[str]:
        """
        Slack Events API webhooks are configured at the app level,
        not per-user. Return a confirmation ID.
        """
        # Webhooks are configured via Slack App dashboard
        # The Events API URL is set at the application level
        logger.info(f"Slack webhook setup is app-level. User {user_id} connected.")
        return f"slack-events-{user_id}"

    async def resolve_user_name(self, user_id_slack: str, credentials: dict) -> str:
        """Resolve a Slack user ID to a display name."""
        try:
            headers = self._get_headers(credentials)
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{SLACK_API_BASE}/users.info",
                    headers=headers,
                    params={"user": user_id_slack},
                )
                data = response.json()
                if data.get("ok"):
                    user = data["user"]
                    return user.get("real_name") or user.get("name", user_id_slack)
        except Exception as e:
            logger.warning(f"Failed to resolve Slack user {user_id_slack}: {e}")
        return user_id_slack

    async def refresh_credentials(self, credentials: dict) -> Optional[dict]:
        """Refresh Slack OAuth token (Slack tokens don't expire by default, but V2 can rotate)."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/oauth.v2.access",
                    data={
                        "client_id": settings.SLACK_CLIENT_ID,
                        "client_secret": settings.SLACK_CLIENT_SECRET,
                        "grant_type": "refresh_token",
                        "refresh_token": credentials.get("refresh_token"),
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        return {
                            "access_token": data["access_token"],
                            "refresh_token": data.get("refresh_token", credentials.get("refresh_token")),
                        }
        except Exception as e:
            logger.error(f"Slack token refresh failed: {e}")
        return None

    @staticmethod
    def _ts_to_iso(ts: str) -> str:
        """Convert Slack timestamp (epoch.sequence) to ISO format."""
        try:
            epoch = float(ts.split(".")[0]) if "." in ts else float(ts)
            return datetime.utcfromtimestamp(epoch).isoformat()
        except (ValueError, TypeError):
            return datetime.utcnow().isoformat()
