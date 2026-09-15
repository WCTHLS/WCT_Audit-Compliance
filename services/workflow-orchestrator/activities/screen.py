"""
Temporal Activity: screen_exclusions_activity.
Activity stub for Exclusion Screening Service (OIG LEIE, SAM.gov, state Medicaid).
"""

from temporalio import activity

from activities.params import ScreeningResult


@activity.defn(name="screen_exclusions_activity")
async def screen_exclusions_activity(
    doctor_npi: str,
    doctor_name: str,
    facility_npi: str = "",
) -> ScreeningResult:
    """
    Screens physician NPI and facility against the OIG List of Excluded Individuals/Entities (LEIE).
    """
    activity.logger.info(
        f"Screening doctor NPI '{doctor_npi}' ('{doctor_name}') against OIG LEIE exclusion database..."
    )

    # In Week 4, this calls POST /screen on exclusion-screening-svc
    # Default test provider is clear (not excluded)
    is_excluded = False
    details = f"Provider '{doctor_name}' (NPI: {doctor_npi}) has NO active exclusions on OIG LEIE."

    if doctor_npi == "9999999999":  # Simulated excluded test NPI
        is_excluded = True
        details = f"MATCH FOUND: Provider '{doctor_name}' is excluded under 1128(a)(1) - Conviction of program-related crimes."

    activity.logger.info(
        f"Exclusion screening completed for NPI '{doctor_npi}'. Result: is_excluded={is_excluded}"
    )

    return ScreeningResult(
        doctor_npi=doctor_npi,
        doctor_name=doctor_name,
        is_excluded=is_excluded,
        details=details,
    )
