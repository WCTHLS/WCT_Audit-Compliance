"""
Temporal Activity: send_follow_up_activity.
Activity stub for automated documentation follow-up reminders to healthcare providers (FR-AUD-03).
"""

from temporalio import activity

from activities.params import FollowUpResult


@activity.defn(name="send_follow_up_activity")
async def send_follow_up_activity(
    case_id: str,
    provider_npi: str,
    reminder_number: int = 1,
) -> FollowUpResult:
    """
    Sends automated follow-up reminder to provider for pending medical records.
    """
    activity.logger.info(
        f"Sending automated follow-up reminder #{reminder_number} for case_id='{case_id}' "
        f"to provider NPI '{provider_npi}'..."
    )

    # In Week 5, this calls notification-svc and logs read-receipts
    activity.logger.info(f"Follow-up reminder #{reminder_number} sent to provider '{provider_npi}'.")

    return FollowUpResult(
        case_id=case_id,
        provider_npi=provider_npi,
        reminder_number=reminder_number,
        sent=True,
    )
