import logging
import os
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from decision_engine import determine_stage
from models import ChatRequest, ChatResponse, EvaluateResponse, SessionSummaryResponse, UserProfile
from modules import eligibility, registration, verification, voting
from services.firebase_service import create_session, get_session_summary, log_interaction
from services.gemini_service import generate_response_bundle

# Configure structured logging for Cloud Run observability
# Using a standard format that Cloud Logging can parse as structured data
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("matdata-sahayak")

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,"
    "http://localhost:5173,"
    "http://localhost:5500,"
    "http://127.0.0.1:3000,"
    "http://127.0.0.1:5173,"
    "http://127.0.0.1:5500"
)
CLOUD_RUN_CORS_ORIGIN_REGEX = r"^https://.*\.run\.app$"
MAX_HISTORY_ITEMS = 10


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to apply security headers to every response.

    Selective CSP is used to allow Swagger UI (/docs and /openapi) to function correctly
    while maintaining a strict policy for all other API routes. Swagger UI requires
    unsafe-inline and unsafe-eval for some of its assets and dynamic execution.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Attach security-related headers to the response based on the request path.

        Args:
            request (Request): Incoming request object.
            call_next (Callable): Next middleware or route handler.

        Returns:
            Response: Response with attached security headers.
        """
        response = await call_next(request)
        path = request.url.path

        # Common headers across all routes
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if path.startswith(("/docs", "/openapi", "/health")):
            # RELAXED headers for Swagger UI and health checks
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self' https:; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
                "style-src 'self' 'unsafe-inline' https:; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https:;"
            )
        else:
            # STRICT headers for standard API routes
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            # Ensure strictly self-hosted resources for core API routes
            response.headers["Content-Security-Policy"] = "default-src 'self';"

        return response


def _get_cors_origins() -> list[str]:
    """
    Return configured CORS origins for local demo or deployment.

    Returns:
        list[str]: List of allowed origin strings.
    """
    configured_origins = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


def _get_cors_origin_regex() -> str:
    """
    Return CORS origin regex with localhost and optional Cloud Run support.

    Returns:
        str: Regex pattern for CORS validation.
    """
    return os.getenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        rf"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|{CLOUD_RUN_CORS_ORIGIN_REGEX}",
    )


app = FastAPI(title="Matdata Sahayak - Election Process Education Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_origin_regex=_get_cors_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(SecurityHeadersMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    """
    Simple health endpoint for Cloud Run startup and health checks.

    Returns:
        dict[str, str]: Service status.
    """
    return {"status": "ok"}


def _model_to_dict(model: Any) -> dict[str, Any]:
    """
    Convert a Pydantic model to a dictionary across Pydantic versions.

    Args:
        model (Any): Pydantic model instance.

    Returns:
        dict[str, Any]: Dictionary representation of the model.
    """
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _get_guidance_for_stage(stage: str) -> dict[str, list[str]]:
    """
    Return module guidance for the current election stage.

    Args:
        stage (str): Current voter stage.

    Returns:
        dict[str, list[str]]: Guidance data including next steps and links.
    """
    guidance_by_stage = {
        "ineligible": eligibility.get_guidance,
        "registration": registration.get_guidance,
        "verification": verification.get_guidance,
        "ready_to_vote": voting.get_guidance,
    }
    return guidance_by_stage.get(stage, eligibility.get_guidance)()


def _fallback_chat_response(guidance: dict[str, list[str]]) -> str:
    """
    Create a simple fallback response from module next steps.

    Args:
        guidance (dict[str, list[str]]): Guidance data.

    Returns:
        str: Fallback message for the user.
    """
    next_steps = guidance.get("next_steps", [])
    if not next_steps:
        return "Please follow the official Election Commission of India guidance."
    return "\n".join(f"- {step}" for step in next_steps)


def _history_to_dicts(history: Sequence[Any]) -> list[dict[str, Any]]:
    """
    Normalize bounded chat history into dictionaries for Gemini context.

    Args:
        history (Sequence[Any]): Raw history items.

    Returns:
        list[dict[str, Any]]: List of dictionary-formatted history items.
    """
    # Limits payload size and improves performance
    # Ensures Gemini context remains focused and token efficient
    history_window = list(history)[-MAX_HISTORY_ITEMS:]
    return [_model_to_dict(item) for item in history_window]


def _default_follow_up_questions(stage: str) -> list[str]:
    """
    Return stable follow-up prompts when Gemini suggestions are unavailable.

    Args:
        stage (str): Current voter stage.

    Returns:
        list[str]: Default follow-up questions.
    """
    by_stage = {
        "ineligible": [
            "What can I prepare before I turn 18?",
            "Which documents should I keep ready for registration?",
            "Where can I check official eligibility rules?",
        ],
        "registration": [
            "How do I complete Form 6 online?",
            "What documents are needed for registration?",
            "How can I track my registration status?",
        ],
        "verification": [
            "How do I verify my name in the voter list?",
            "What should I do if my details are wrong?",
            "How can I use EPIC to check status?",
        ],
        "ready_to_vote": [
            "What should I carry on voting day?",
            "How do I find my polling booth?",
            "What are polling hours in my area?",
        ],
    }
    return by_stage.get(stage, by_stage["registration"])


def _normalize_follow_up_questions(items: Any, stage: str) -> list[str]:
    """
    Sanitize follow-up suggestions for the chat response payload.

    Args:
        items (Any): Raw suggestions from Gemini.
        stage (str): Current voter stage.

    Returns:
        list[str]: Cleaned list of unique follow-up questions.
    """
    if not isinstance(items, list):
        return _default_follow_up_questions(stage)

    normalized = []
    seen = set()

    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= 3:
            break

    if len(normalized) < 2:
        fallback = _default_follow_up_questions(stage)
        for item in fallback:
            if item.casefold() not in seen:
                normalized.append(item)
                seen.add(item.casefold())
            if len(normalized) >= 3:
                break

    return normalized


@app.post("/api/evaluate", response_model=EvaluateResponse)
async def evaluate_user(user: UserProfile) -> EvaluateResponse:
    """
    Evaluate a user profile, create a session, and return readiness details.

    Args:
        user (UserProfile): User-provided profile data.

    Returns:
        EvaluateResponse: Calculated stage, score, and next steps.
    """
    # Structured log for incoming request
    logger.info({
        "event": "evaluate_request",
        "endpoint": "/api/evaluate",
        "method": "POST"
    })

    decision = determine_stage(user)

    # Structured log for decision engine output
    logger.info({
        "event": "decision_output",
        "stage": decision["stage"],
        "score": decision["readiness_score"]
    })

    guidance = _get_guidance_for_stage(decision["stage"])
    session_id = create_session({"user_profile": _model_to_dict(user)})

    return EvaluateResponse(
        stage=decision["stage"],
        readiness_score=decision["readiness_score"],
        checklist=decision["checklist"],
        next_steps=guidance.get("next_steps", decision["next_steps"]),
        links=guidance.get("links", []),
        session_id=session_id,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Generate election guidance and log the interaction when Firebase is available.

    Args:
        request (ChatRequest): Incoming chat request with history and user profile.

    Returns:
        ChatResponse: AI-generated response and follow-up suggestions.
    """
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Structured log for incoming chat request
    logger.info({
        "event": "chat_request",
        "endpoint": "/api/chat",
        "method": "POST",
        "message_preview": message[:100]
    })

    decision = determine_stage(request.user)
    guidance = _get_guidance_for_stage(decision["stage"])
    session_id = request.session_id.strip() if request.session_id else None

    if not session_id:
        session_id = create_session({"user_profile": _model_to_dict(request.user)})

    context = {
        "message": message,
        "stage": decision["stage"],
        "readiness_score": decision["readiness_score"],
        "decision_checklist": decision["checklist"],
        "user_profile": _model_to_dict(request.user),
        "state": request.user.state,
        "session_id": session_id,
        "checklist": guidance.get("checklist", []),
        "next_steps": guidance.get("next_steps", []),
        "links": guidance.get("links", []),
        "history": _history_to_dicts(request.history),
    }

    response_bundle = generate_response_bundle(context)
    response_text = str(response_bundle.get("response", "")).strip() or _fallback_chat_response(guidance)
    follow_up_questions = _normalize_follow_up_questions(
        response_bundle.get("follow_up_questions", []),
        decision["stage"],
    )

    # Structured log for chat response
    logger.info({
        "event": "chat_response",
        "stage": decision["stage"],
        "response_preview": response_text[:100]
    })

    if session_id:
        try:
            log_interaction(
                session_id,
                {
                    "message": message,
                    "response": response_text,
                    "stage": decision["stage"],
                    "follow_up_questions": follow_up_questions,
                },
            )
        except Exception:
            pass

    return ChatResponse(
        response=response_text,
        stage=decision["stage"],
        session_id=session_id,
        follow_up_questions=follow_up_questions,
    )


@app.get("/api/session/{session_id}/summary", response_model=SessionSummaryResponse)
async def session_summary(session_id: str) -> SessionSummaryResponse:
    """
    Return a Firebase-backed session summary for demo visibility.

    Args:
        session_id (str): The unique session ID.

    Returns:
        SessionSummaryResponse: Full session details from Firestore.
    """
    summary = get_session_summary(session_id)
    return SessionSummaryResponse(**summary)
