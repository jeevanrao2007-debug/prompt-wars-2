from services.firebase_service import create_session, log_interaction
from services.gemini_service import _build_response_prompt, generate_response, generate_response_bundle


def test_firebase_gracefully_handles_missing_credentials(monkeypatch):
    """Firebase functions return gracefully when credentials are absent."""
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)

    assert create_session({"user_profile": {"age": 20}}) is None
    assert log_interaction("session-1", {"message": "hello"}) is None


def test_gemini_fallback_is_conversational(monkeypatch):
    """Gemini fallback remains useful without an API key."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    bundle = generate_response_bundle(
        {
            "stage": "ready_to_vote",
            "next_steps": ["Carry valid ID", "Reach during polling hours"],
            "links": ["https://voters.eci.gov.in"],
        }
    )

    response = generate_response(
        {
            "stage": "ready_to_vote",
            "next_steps": ["Carry valid ID", "Reach during polling hours"],
            "links": ["https://voters.eci.gov.in"],
        }
    )

    assert "You are fully ready to vote" in response
    assert "- Carry valid ID" in response
    assert len(bundle["follow_up_questions"]) in {2, 3}


def test_gemini_prompt_includes_personalization_context():
    """Gemini prompt construction includes profile, stage, links, and history."""
    prompt = _build_response_prompt(
        message="How do I verify my voter details?",
        stage="verification",
        intent="VERIFY",
        context={
            "user_profile": {
                "age": 21,
                "state": "Delhi",
                "registered": True,
                "verified": False,
            },
            "readiness_score": 60,
            "decision_checklist": ["[OK] Eligible", "[OK] Registered", "[NO] Verified"],
            "checklist": ["Search your name in the electoral roll."],
            "next_steps": ["Check voter status on electoralsearch.eci.gov.in."],
            "links": ["https://electoralsearch.eci.gov.in"],
        },
        history="user: I registered last month",
    )

    assert "Age: 21" in prompt
    assert "State/UT: Delhi" in prompt
    assert "Current stage: verification" in prompt
    assert "Detected intent: VERIFY" in prompt
    assert "[NO] Verified" in prompt
    assert "https://electoralsearch.eci.gov.in" in prompt
    assert "user: I registered last month" in prompt
