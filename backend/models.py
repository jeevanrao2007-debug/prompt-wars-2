from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """User information used for election-readiness evaluation."""

    age: int = Field(..., ge=0, le=120)
    state: str = Field(..., min_length=2, max_length=80)
    registered: bool
    verified: bool


class ChatMessage(BaseModel):
    """A compact conversation history message."""

    role: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    """Incoming chat payload containing the user profile, message, and session context."""

    user: UserProfile
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=160)
    history: list[ChatMessage] = Field(default_factory=list, max_length=10)


class EvaluateResponse(BaseModel):
    """Response model for evaluation requests."""

    stage: str
    readiness_score: int = Field(..., ge=0, le=100)
    checklist: list[str]
    next_steps: list[str]
    links: list[str]
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Response model for chat requests."""

    response: str
    stage: str
    session_id: str | None = None
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)


class SessionSummaryResponse(BaseModel):
    """Response model for session summary requests."""

    session_id: str
    source: str
    user_profile: dict = Field(default_factory=dict)
    created_at: str | None = None
    interactions_count: int = Field(default=0, ge=0)
    interactions: list[dict] = Field(default_factory=list)
    note: str | None = None
