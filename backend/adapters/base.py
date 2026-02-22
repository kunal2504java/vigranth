"""
Abstract base class for all platform adapters.

Every platform adapter must implement:
  - fetch_new_messages(): Pull raw messages from platform API
  - normalize(): Convert platform-specific message to MessageState
  - send_message(): Send a reply through the platform API
  - setup_webhook(): Register webhook for realtime delivery

From Architecture doc Section 3.1.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from backend.agents.state import MessageState


class PlatformAdapter(ABC):
    """Base interface for platform integrations."""

    @abstractmethod
    async def fetch_new_messages(
        self,
        user_id: str,
        since: datetime,
        credentials: dict,
    ) -> list[dict]:
        """Fetch raw messages from platform API since the given timestamp."""
        pass

    @abstractmethod
    def normalize(self, raw_message: dict, user_id: str) -> MessageState:
        """Convert a platform-specific raw message dict into a unified MessageState."""
        pass

    @abstractmethod
    async def send_message(
        self,
        thread_id: str,
        text: str,
        credentials: dict,
        **kwargs,
    ) -> dict:
        """
        Send a reply through the platform's API.
        Returns dict with 'success' bool and optionally 'platform_message_id'.
        """
        pass

    @abstractmethod
    async def setup_webhook(
        self,
        user_id: str,
        webhook_url: str,
        credentials: dict,
    ) -> Optional[str]:
        """
        Register a webhook for realtime message delivery.
        Returns the webhook ID or None on failure.
        """
        pass

    async def refresh_credentials(self, credentials: dict) -> Optional[dict]:
        """
        Refresh expired OAuth tokens. Override per platform.
        Returns new credentials dict or None if refresh failed.
        """
        return None

    def get_platform_name(self) -> str:
        """Return the platform identifier string."""
        return self.__class__.__name__.replace("Adapter", "").lower()
