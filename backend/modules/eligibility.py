def get_guidance() -> dict[str, list[str]]:
    """Return eligibility guidance aligned with Election Commission of India basics."""
    return {
        "checklist": [
            "Be 18 years or older on the qualifying date.",
            "Be an Indian citizen.",
            "Ordinarily reside at the address where you want to enroll.",
            "Keep basic identity, age, and address documents ready.",
        ],
        "next_steps": [
            "Check if you will be 18 on the qualifying date before applying.",
            "Confirm the constituency linked to your current residence.",
            "Prepare age proof, address proof, and a recent passport-size photo.",
        ],
        "links": [
            "https://voters.eci.gov.in",
            "https://eci.gov.in",
        ],
    }
