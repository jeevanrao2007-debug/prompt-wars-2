def get_guidance() -> dict[str, list[str]]:
    """Return voting-day guidance for an enrolled voter.

    Returns:
        dict[str, list[str]]: Guidance with checklist, next steps, and links.
    """
    return {
        "checklist": [
            "Check your polling booth details before election day.",
            "Carry a valid approved identity document.",
            "Reach the booth during polling hours.",
            "Follow polling staff instructions and cast your vote using the EVM.",
        ],
        "next_steps": [
            "Confirm your booth location through the electoral search or voter portal.",
            "Carry your EPIC or another valid ID accepted for voting.",
            "At the booth, verify your identity, mark attendance, and proceed to vote.",
        ],
        "links": [
            "https://electoralsearch.eci.gov.in",
            "https://voters.eci.gov.in",
            "https://eci.gov.in",
        ],
    }
