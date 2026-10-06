"""
In-memory repository for notifications.
Maintains history of dispatched alerts for testing, status checks, and audit lookups.
"""

from collections import deque
from threading import Lock
from typing import Any, Dict, List, Optional
from src.config import settings
from src.schemas import NotifyResponse


class NotificationRepository:
    """Thread-safe in-memory store for dispatched notifications."""

    def __init__(self, max_size: int = settings.MAX_HISTORY_ENTRIES) -> None:
        self._max_size = max_size
        self._items: deque[NotifyResponse] = deque(maxlen=max_size)
        self._lock = Lock()

    def add(self, item: NotifyResponse) -> None:
        """Stores a dispatched notification in the history buffer."""
        with self._lock:
            self._items.append(item)

    def get_by_id(self, notification_id: str) -> Optional[NotifyResponse]:
        """Finds a notification by its unique ID."""
        with self._lock:
            for item in reversed(self._items):
                if item.notification_id == notification_id:
                    return item
        return None

    def list_all(
        self,
        case_id: Optional[str] = None,
        recipient: Optional[str] = None,
        notification_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[NotifyResponse]:
        """Queries notifications with optional filters, sorted newest first."""
        with self._lock:
            results: List[NotifyResponse] = []
            for item in reversed(self._items):
                if case_id and item.case_id != case_id:
                    continue
                if recipient and item.recipient != recipient:
                    continue
                if notification_type and item.notification_type.value != notification_type:
                    continue
                results.append(item)
                if len(results) >= limit:
                    break
            return results

    def get_stats(self) -> Dict[str, Any]:
        """Aggregates telemetry on dispatches."""
        with self._lock:
            total = len(self._items)
            by_type: Dict[str, int] = {}
            by_channel: Dict[str, int] = {}

            for item in self._items:
                t = item.notification_type.value
                by_type[t] = by_type.get(t, 0) + 1
                c = item.channel.value
                by_channel[c] = by_channel.get(c, 0) + 1

            return {
                "total_dispatched": total,
                "stats_by_type": by_type,
                "stats_by_channel": by_channel,
            }

    def clear(self) -> None:
        """Clears buffer (used during tests)."""
        with self._lock:
            self._items.clear()


repository = NotificationRepository()
