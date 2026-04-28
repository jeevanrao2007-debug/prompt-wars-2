def get_guidance() -> dict[str, list[str]]:
    """Return voter registration guidance for the Form 6 process.

    Returns:
        dict[str, list[str]]: Guidance with checklist, next steps, and links.
    """
    return {
        "checklist": [
            "Open the new voter registration section on the ECI voter portal.",
            "Fill Form 6 with personal, family, and address details.",
            "Upload age proof, address proof, and a recent photo.",
            "Review the application carefully before submitting.",
        ],
        "next_steps": [
            "Visit voters.eci.gov.in and choose the new voter registration option.",
            "Complete Form 6 with your name, date of birth, gender, and address.",
            "Upload age proof, address proof, and photo in the required format.",
            "Submit the form and keep the reference number for tracking.",
        ],
        "links": [
            "https://voters.eci.gov.in",
            "https://eci.gov.in",
        ],
    }
