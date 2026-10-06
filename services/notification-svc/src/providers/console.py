"""
Console and Logging Notification Provider.
Default provider for POC environment: formats alerts cleanly, logs structured JSON,
and simulates instantaneous reliable delivery.
"""

from datetime import datetime, timezone
import json
import logging
import uuid
from src.providers.base import BaseNotificationProvider
from src.schemas import (
    NotificationPriority,
    NotificationStatus,
    NotifyRequest,
    NotifyResponse,
)

logger = logging.getLogger("notification_svc.console")


class ConsoleNotificationProvider(BaseNotificationProvider):
    """
    Simulates alert dispatch by outputting formatted notifications to logs/console.
    Swappable for real SMTP/SMS/Webhook providers without interface change.
    """

    @property
    def name(self) -> str:
        return "console-logger"

    async def send(self, request: NotifyRequest) -> NotifyResponse:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        notif_id = f"NOTIF-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # Visual indicator based on priority (ASCII safe for all terminal encodings)
        prio_icon = {
            NotificationPriority.LOW: "[INFO/LOW]",
            NotificationPriority.NORMAL: "[NOTICE/NORMAL]",
            NotificationPriority.HIGH: "[WARNING/HIGH]",
            NotificationPriority.URGENT: "[ALERT/URGENT]",
        }.get(request.priority, "[NOTICE]")

        banner = (
            f"\n{'='*70}\n"
            f"{prio_icon} NOTIFICATION DISPATCHED: {request.notification_type.value}\n"
            f"{'='*70}\n"
            f"ID        : {notif_id}\n"
            f"Case ID   : {request.case_id or 'N/A'}\n"
            f"Recipient : {request.recipient}\n"
            f"Channel   : {request.channel.value}\n"
            f"Priority  : {request.priority.value}\n"
            f"Subject   : {request.subject}\n"
            f"Message   : {request.message}\n"
            f"Metadata  : {json.dumps(request.metadata, indent=2) if request.metadata else '{}'}\n"
            f"Dispatched: {now_iso}\n"
            f"{'='*70}"
        )

        # Print to stdout/console for local developer visibility
        print(banner, flush=True)

        # Structured log for observability / log collectors
        logger.info(
            "Notification dispatched: id=%s type=%s recipient=%s case_id=%s priority=%s channel=%s",
            notif_id,
            request.notification_type.value,
            request.recipient,
            request.case_id,
            request.priority.value,
            request.channel.value,
            extra={
                "notification_id": notif_id,
                "notification_type": request.notification_type.value,
                "recipient": request.recipient,
                "case_id": request.case_id,
                "channel": request.channel.value,
                "priority": request.priority.value,
                "metadata": request.metadata,
            },
        )

        return NotifyResponse(
            notification_id=notif_id,
            status=NotificationStatus.DELIVERED,
            recipient=request.recipient,
            channel=request.channel,
            notification_type=request.notification_type,
            case_id=request.case_id,
            subject=request.subject,
            dispatched_at=now_iso,
            provider=self.name,
            details=f"Alert dispatched via {self.name} simulation.",
            metadata=request.metadata,
        )
