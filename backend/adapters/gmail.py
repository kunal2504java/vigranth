"""
Gmail Adapter — connects to Gmail API via OAuth2.

From Integration Spec Section 1.2:
  - OAuth Endpoint: https://accounts.google.com/o/oauth2/auth
  - Token Endpoint: https://oauth2.googleapis.com/token
  - Scopes: gmail.readonly, gmail.send, gmail.modify
  - Realtime: Gmail Push Notifications (Pub/Sub)
  - Rate Limit: 250 quota units/user/sec
"""
import base64
import logging
import re
from datetime import datetime
from email.mime.text import MIMEText
from typing import Optional
from uuid import uuid4

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from backend.adapters.base import PlatformAdapter
from backend.agents.state import MessageState, SenderContext, Platform
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailAdapter(PlatformAdapter):
    """Gmail platform adapter using Google Gmail API."""

    def _build_service(self, credentials: dict):
        """Build Gmail API service from stored credentials."""
        creds = Credentials(
            token=credentials.get("access_token"),
            refresh_token=credentials.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GMAIL_CLIENT_ID,
            client_secret=settings.GMAIL_CLIENT_SECRET,
        )

        # Refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())

        return build("gmail", "v1", credentials=creds), creds

    async def fetch_new_messages(
        self,
        user_id: str,
        since: datetime,
        credentials: dict,
    ) -> list[dict]:
        """Fetch inbox messages since the given timestamp."""
        try:
            service, _ = self._build_service(credentials)
            query = f"after:{int(since.timestamp())} in:inbox"

            results = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=50)
                .execute()
            )

            messages = []
            for ref in results.get("messages", []):
                try:
                    msg = (
                        service.users()
                        .messages()
                        .get(userId="me", id=ref["id"], format="full")
                        .execute()
                    )
                    messages.append(msg)
                except Exception as e:
                    logger.warning(f"Failed to fetch Gmail message {ref['id']}: {e}")
                    continue

            logger.info(f"Fetched {len(messages)} Gmail messages for user {user_id}")
            return messages

        except Exception as e:
            logger.error(f"Gmail fetch failed for user {user_id}: {e}")
            return []

    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert raw Gmail API response to MessageState."""
        headers = {
            h["name"].lower(): h["value"]
            for h in raw_message.get("payload", {}).get("headers", [])
        }

        from_header = headers.get("from", "")
        sender_name = self._parse_name(from_header)
        sender_email = self._parse_email(from_header)

        body = self._extract_body(raw_message.get("payload", {}))

        return MessageState(
            id=str(uuid4()),
            user_id=user_id,
            platform=Platform.GMAIL,
            platform_message_id=raw_message.get("id", ""),
            thread_id=raw_message.get("threadId", ""),
            sender=SenderContext(
                id=sender_email or from_header,
                name=sender_name,
                email=sender_email,
            ),
            content_text=body,
            timestamp=headers.get("date", datetime.utcnow().isoformat()),
        )

    async def send_message(
        self,
        thread_id: str,
        text: str,
        credentials: dict,
        **kwargs,
    ) -> dict:
        """Send a reply through Gmail API."""
        try:
            service, _ = self._build_service(credentials)
            to_email = kwargs.get("to_email", "")
            subject = kwargs.get("subject", "Re: ")

            message = MIMEText(text)
            message["to"] = to_email
            message["subject"] = subject

            raw_message = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode("utf-8")

            result = (
                service.users()
                .messages()
                .send(
                    userId="me",
                    body={
                        "raw": raw_message,
                        "threadId": thread_id,
                    },
                )
                .execute()
            )

            logger.info(f"Sent Gmail message in thread {thread_id}")
            return {"success": True, "platform_message_id": result.get("id")}

        except Exception as e:
            logger.error(f"Gmail send failed: {e}")
            return {"success": False, "error": str(e)}

    async def setup_webhook(
        self,
        user_id: str,
        webhook_url: str,
        credentials: dict,
    ) -> Optional[str]:
        """Set up Gmail push notifications via Pub/Sub."""
        try:
            service, _ = self._build_service(credentials)
            result = (
                service.users()
                .watch(
                    userId="me",
                    body={
                        "labelIds": ["INBOX"],
                        "topicName": f"projects/unifyinbox/topics/gmail-{user_id}",
                    },
                )
                .execute()
            )
            history_id = result.get("historyId")
            logger.info(f"Gmail push setup for user {user_id}, historyId={history_id}")
            return history_id
        except Exception as e:
            logger.error(f"Gmail webhook setup failed: {e}")
            return None

    async def refresh_credentials(self, credentials: dict) -> Optional[dict]:
        """Refresh Gmail OAuth token."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": settings.GMAIL_CLIENT_ID,
                        "client_secret": settings.GMAIL_CLIENT_SECRET,
                        "refresh_token": credentials.get("refresh_token"),
                        "grant_type": "refresh_token",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "access_token": data["access_token"],
                        "refresh_token": credentials.get("refresh_token"),
                        "expires_in": data.get("expires_in", 3600),
                    }
        except Exception as e:
            logger.error(f"Gmail token refresh failed: {e}")
        return None

    # --- Helpers ---

    @staticmethod
    def _parse_name(from_header: str) -> str:
        """Extract display name from 'Name <email>' format."""
        match = re.match(r'"?([^"<]*)"?\s*<', from_header)
        if match:
            return match.group(1).strip()
        return from_header.split("@")[0] if "@" in from_header else from_header

    @staticmethod
    def _parse_email(from_header: str) -> Optional[str]:
        """Extract email from 'Name <email>' format."""
        match = re.search(r"<([^>]+)>", from_header)
        if match:
            return match.group(1)
        if "@" in from_header:
            return from_header.strip()
        return None

    @staticmethod
    def _extract_body(payload: dict) -> str:
        """Extract plain text body from Gmail message payload."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        # Check parts
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            # Nested multipart
            if part.get("parts"):
                for subpart in part["parts"]:
                    if subpart.get("mimeType") == "text/plain" and subpart.get("body", {}).get("data"):
                        return base64.urlsafe_b64decode(
                            subpart["body"]["data"]
                        ).decode("utf-8", errors="replace")

        # Fallback: try snippet
        return payload.get("snippet", "(no content)")
