"""
Temporal Activity: notify_auditor_activity.
Activity stub for Notification Service (email, SMS, webhooks, SLA breach alerts).
"""

from temporalio import activity

from activities.params import NotificationResult


@activity.defn(name="notify_auditor_activity")
async def notify_auditor_activity(
    recipient: str,
    notification_type: str,
    case_id: str,
    message: str,
) -> NotificationResult:
    """
    Sends notification to an auditor or supervisor (e.g. SLA breach alert or new case assignment).
    """
    activity.logger.info(
        f"Sending notification '{notification_type}' for case_id='{case_id}' to recipient='{recipient}'..."
    )

    # In Week 5, this calls notification-svc
    activity.logger.info(f"Notification delivered successfully to '{recipient}'.")

    return NotificationResult(
        recipient=recipient,
        notification_type=notification_type,
        case_id=case_id,
        sent=True,
    )
