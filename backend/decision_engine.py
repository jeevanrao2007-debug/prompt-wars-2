from typing import Any


def determine_stage(user_profile: Any) -> dict[str, Any]:
    """Evaluate voter readiness and determine the election stage.

    Args:
        user_profile (Any): User profile containing age, registration, and verification status.

    Returns:
        dict[str, Any]: Stage classification, readiness score, and checklist.
    """
    # Extract profile attributes
    age = user_profile.age
    registered = user_profile.registered
    verified = user_profile.verified

    # Deterministic rules: explicit legal milestones, no probabilistic inputs.
    # Stage meaning: ineligible=under 18, registration=not registered,
    # verification=registered but unverified, ready_to_vote=all milestones met.
    if age < 18:
        stage = "ineligible"
    elif not registered:
        stage = "registration"
    elif not verified:
        stage = "verification"
    else:
        stage = "ready_to_vote"

    # Calculate readiness score based on milestone completion
    readiness_score = 0
    if age >= 18:
        readiness_score += 30
    if registered:
        readiness_score += 30
    if verified:
        readiness_score += 40

    # Build readiness checklist for UI display
    checklist = [
        "[OK] Eligible" if age >= 18 else "[NO] Eligible",
        "[OK] Registered" if registered else "[NO] Registered",
        "[OK] Verified" if verified else "[NO] Verified",
    ]

    # Map stages to specific recommended next steps
    next_steps_map = {
        "ineligible": ["Wait until you turn 18", "Prepare documents"],
        "registration": ["Fill Form 6 on voters.eci.gov.in"],
        "verification": ["Check status on electoralsearch.eci.gov.in"],
        "ready_to_vote": ["Visit polling booth", "Carry valid ID"],
    }

    return {
        "stage": stage,
        "readiness_score": readiness_score,
        "checklist": checklist,
        "next_steps": next_steps_map[stage],
    }
