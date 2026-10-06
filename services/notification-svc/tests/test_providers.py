"""
Unit tests for notification provider abstractions, registry, and in-memory repository.
"""

import pytest
from src.providers.console import ConsoleNotificationProvider
from src.providers.registry import ProviderRegistry
from src.repository import NotificationRepository
from src.schemas import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
    NotifyRequest,
    NotifyResponse,
)


def test_console_provider_dispatch():
    """Validates that ConsoleNotificationProvider produces properly structured responses."""
    import asyncio
    provider = ConsoleNotificationProvider()
    assert provider.name == "console-logger"

    request = NotifyRequest(
        recipient="provider.billing@clinic.org",
        notification_type=NotificationType.DOCUMENT_REQUEST_INITIAL,
        channel=NotificationChannel.CONSOLE,
        priority=NotificationPriority.NORMAL,
        subject="Records Request",
        message="Please provide records for review.",
        case_id="CASE-2026-003",
        metadata={"claim_id": "CLM-2026-3317"},
    )

    response = asyncio.run(provider.send(request))
    assert isinstance(response, NotifyResponse)
    assert response.status == NotificationStatus.DELIVERED
    assert response.notification_id.startswith("NOTIF-")
    assert response.provider == "console-logger"
    assert response.case_id == "CASE-2026-003"


def test_provider_registry():
    """Validates registry provider resolution."""
    registry = ProviderRegistry()
    assert "console-logger" in registry.list_active()
    assert registry.get("console-logger") is not None
    assert registry.get_default_provider() is not None


def test_repository_ring_buffer_and_stats():
    """Validates repository retention limit, query filters, and telemetry metrics."""
    repo = NotificationRepository(max_size=3)

    for i in range(5):
        repo.add(
            NotifyResponse(
                notification_id=f"NOTIF-{i}",
                status=NotificationStatus.DELIVERED,
                recipient=f"user{i}@wct.com",
                channel=NotificationChannel.EMAIL,
                notification_type=NotificationType.SLA_BREACH_WARNING,
                case_id=f"CASE-{i}",
                subject="Alert",
                dispatched_at="2026-10-06T10:00:00Z",
                provider="console-logger",
                details="Delivered",
            )
        )

    # Max size is 3, so only the last 3 items should remain
    all_items = repo.list_all()
    assert len(all_items) == 3
    assert [item.notification_id for item in all_items] == ["NOTIF-4", "NOTIF-3", "NOTIF-2"]

    # Telemetry stats
    stats = repo.get_stats()
    assert stats["total_dispatched"] == 3
    assert stats["stats_by_type"]["SLA_BREACH_WARNING"] == 3
    assert stats["stats_by_channel"]["EMAIL"] == 3
