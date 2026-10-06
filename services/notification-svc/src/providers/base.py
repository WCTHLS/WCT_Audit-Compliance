"""
Abstract Base Provider for notification dispatch.
Enables pluggable backends (Console/Logging for POC, SMTP/SES for email, Twilio for SMS, Webhooks).
"""

from abc import ABC, abstractmethod
from src.schemas import NotifyRequest, NotifyResponse


class BaseNotificationProvider(ABC):
    """Abstract interface that all notification providers must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier name."""
        pass

    @abstractmethod
    async def send(self, request: NotifyRequest) -> NotifyResponse:
        """
        Dispatches a notification using this provider's delivery channel.
        Must return a NotifyResponse with dispatch status and timestamps.
        """
        pass
