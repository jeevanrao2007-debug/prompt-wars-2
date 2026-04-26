from types import SimpleNamespace

from decision_engine import determine_stage


def test_determine_stage_ineligible():
    """A user under 18 is marked ineligible."""
    result = determine_stage(SimpleNamespace(age=17, registered=False, verified=False))

    assert result["stage"] == "ineligible"
    assert result["readiness_score"] == 0
    assert result["checklist"] == ["[NO] Eligible", "[NO] Registered", "[NO] Verified"]


def test_determine_stage_registration():
    """An eligible unregistered user is sent to registration."""
    result = determine_stage(SimpleNamespace(age=18, registered=False, verified=False))

    assert result["stage"] == "registration"
    assert result["readiness_score"] == 30


def test_determine_stage_verification():
    """A registered but unverified user is sent to verification."""
    result = determine_stage(SimpleNamespace(age=25, registered=True, verified=False))

    assert result["stage"] == "verification"
    assert result["readiness_score"] == 60


def test_determine_stage_ready_to_vote():
    """A registered and verified eligible user is ready to vote."""
    result = determine_stage(SimpleNamespace(age=25, registered=True, verified=True))

    assert result["stage"] == "ready_to_vote"
    assert result["readiness_score"] == 100
