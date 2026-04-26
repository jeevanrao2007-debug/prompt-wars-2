from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_evaluate_returns_stable_response(monkeypatch):
    """The evaluate endpoint returns readiness data and keeps Firebase optional."""
    monkeypatch.setattr(main, "create_session", lambda data: "session-123")

    response = client.post(
        "/api/evaluate",
        json={
            "age": 19,
            "state": "Delhi",
            "registered": False,
            "verified": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "registration"
    assert body["readiness_score"] == 30
    assert body["session_id"] == "session-123"
    assert body["links"]
    assert body["checklist"] == ["[OK] Eligible", "[NO] Registered", "[NO] Verified"]


def test_fallback__chat_still_returns_response_when_gemini_is_unavailable(monkeypatch):
    """Fallback: chat still returns a safe answer and follow-up chips when Gemini is unavailable."""
    monkeypatch.setattr(main, "create_session", lambda data: None)
    monkeypatch.setattr(main, "log_interaction", lambda session_id, data: None)
    monkeypatch.setattr(main, "generate_response_bundle", lambda context: {"response": "", "follow_up_questions": []})

    response = client.post(
        "/api/chat",
        json={
            "user": {
                "age": 22,
                "state": "Delhi",
                "registered": True,
                "verified": True,
            },
            "message": "What should I carry on voting day?",
            "history": [{"role": "user", "message": "Hello"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "ready_to_vote"
    assert "Carry your EPIC" in body["response"]
    assert len(body["follow_up_questions"]) == 3
    assert body["session_id"] is None


def test_fallback__evaluate_still_returns_payload_when_firebase_is_unavailable(monkeypatch):
    """Fallback: evaluate returns stage and score even when Firebase cannot create a session."""
    monkeypatch.setattr(main, "create_session", lambda data: None)

    response = client.post(
        "/api/evaluate",
        json={
            "age": 20,
            "state": "Delhi",
            "registered": False,
            "verified": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "registration"
    assert body["readiness_score"] == 30
    assert body["session_id"] is None


def test_fallback__session_summary_returns_unavailable_payload_when_firebase_is_down(monkeypatch):
    """Fallback: session summary endpoint responds safely when Firebase data is unavailable."""
    monkeypatch.setattr(
        main,
        "get_session_summary",
        lambda session_id: {
            "session_id": session_id,
            "source": "unavailable",
            "user_profile": {},
            "created_at": None,
            "interactions_count": 0,
            "interactions": [],
            "note": "Firebase is unavailable.",
        },
    )

    response = client.get("/api/session/demo-session/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "demo-session"
    assert body["source"] == "unavailable"
    assert body["interactions_count"] == 0


def test_chat_rejects_blank_message():
    """Blank chat messages are rejected before service calls."""
    response = client.post(
        "/api/chat",
        json={
            "user": {
                "age": 22,
                "state": "Delhi",
                "registered": True,
                "verified": True,
            },
            "message": "   ",
        },
    )

    assert response.status_code in {400, 422}


def test_healthz_is_minimal_and_reliable():
    """Health checks return a minimal success payload."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
