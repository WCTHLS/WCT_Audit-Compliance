"""
Provider Registry for the WCT Notification Service.
Manages registered providers and resolves dispatchers dynamically.
"""

from typing import Dict, List, Optional
from src.config import settings
from src.providers.base import BaseNotificationProvider
from src.providers.console import ConsoleNotificationProvider
from src.schemas import NotificationChannel


class ProviderRegistry:
    """Manages active notification providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, BaseNotificationProvider] = {}
        # Register default console provider
        console = ConsoleNotificationProvider()
        self.register(console)

    def register(self, provider: BaseNotificationProvider) -> None:
        """Register a notification provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> Optional[BaseNotificationProvider]:
        """Retrieve provider by name."""
        return self._providers.get(name)

    def get_default_provider(self, channel: Optional[NotificationChannel] = None) -> BaseNotificationProvider:
        """
        Returns appropriate provider for the given channel or system default.
        In POC mode, console logger handles all channels.
        """
        # When specific providers are implemented later (e.g. 'smtp-email', 'twilio-sms'),
        # channel routing will resolve here.
        return self._providers.get("console-logger") or list(self._providers.values())[0]

    def list_active(self) -> List[str]:
        """List names of all currently registered providers."""
        return list(self._providers.keys())


registry = ProviderRegistry()
