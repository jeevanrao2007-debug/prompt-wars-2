def get_guidance() -> dict[str, list[str]]:
    """Return voter verification and correction guidance."""
    return {
        "checklist": [
            "Search your name in the electoral roll.",
            "Keep your EPIC number ready if already issued.",
            "Confirm that your name, age, and address are correct.",
            "Start a correction request if any detail is wrong or missing.",
        ],
        "next_steps": [
            "Check voter status on electoralsearch.eci.gov.in.",
            "Use your EPIC number or personal details to search your record.",
            "If details are incorrect, use the voter portal to request an update or correction.",
        ],
        "links": [
            "https://electoralsearch.eci.gov.in",
            "https://voters.eci.gov.in",
            "https://eci.gov.in",
        ],
    }
