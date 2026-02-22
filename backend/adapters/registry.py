"""
Platform adapter registry — factory pattern for getting the right adapter.
"""
from typing import Optional

from backend.adapters.base import PlatformAdapter
from backend.adapters.gmail import GmailAdapter
from backend.adapters.slack import SlackAdapter
from backend.adapters.telegram import TelegramAdapter
from backend.adapters.discord import DiscordAdapter

# Singleton instances
_adapters: dict[str, PlatformAdapter] = {}


def get_adapter(platform: str) -> Optional[PlatformAdapter]:
    """Get the adapter instance for a given platform."""
    if platform not in _adapters:
        adapter_map = {
            "gmail": GmailAdapter,
            "slack": SlackAdapter,
            "telegram": TelegramAdapter,
            "discord": DiscordAdapter,
        }
        adapter_cls = adapter_map.get(platform)
        if adapter_cls is None:
            return None
        _adapters[platform] = adapter_cls()

    return _adapters[platform]


def get_supported_platforms() -> list[str]:
    """Return list of supported platform names."""
    return ["gmail", "slack", "telegram", "discord"]
