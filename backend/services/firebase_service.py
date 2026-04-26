import os
from datetime import datetime, timezone
from threading import Lock
from typing import Any

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:  # pragma: no cover
    firebase_admin = None
    credentials = None
    firestore = None


FIREBASE_CREDENTIALS_ENV = "FIREBASE_CREDENTIALS_PATH"
SESSIONS_COLLECTION = "sessions"
INTERACTIONS_COLLECTION = "interactions"

_db_client = None
_init_error = None
_init_lock = Lock()


def _get_firestore_client() -> Any | None:
    """Initialize and return a shared Firestore client from environment configuration."""
    global _db_client, _init_error

    if _db_client is not None:
        return _db_client

    with _init_lock:
        if _db_client is not None:
            return _db_client

        if firebase_admin is None or credentials is None or firestore is None:
            _init_error = "Firebase Admin SDK is not installed."
            return None

        credential_path = os.getenv(FIREBASE_CREDENTIALS_ENV, "").strip()

        try:
            if not firebase_admin._apps:
                if credential_path:
                    if not os.path.isfile(credential_path):
                        _init_error = f"{FIREBASE_CREDENTIALS_ENV} does not point to a readable file."
                        return None

                    app_credentials = credentials.Certificate(credential_path)
                    firebase_admin.initialize_app(app_credentials)
                else:
                    firebase_admin.initialize_app()

            _db_client = firestore.client()
            _init_error = None
            return _db_client
        except Exception as exc:
            _init_error = f"Firestore initialization failed: {exc.__class__.__name__}"
            return None


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _as_dict(value: Any) -> dict[str, Any]:
    """Return value if it is a dictionary, otherwise return an empty dictionary."""
    return value if isinstance(value, dict) else {}


def _as_string(value: Any) -> str:
    """Return value as a safe string for Firestore writes."""
    if value is None:
        return ""
    return str(value)


def _normalize_user_profile(data: Any) -> dict[str, Any]:
    """Build a valid user profile payload for a session document."""
    payload = _as_dict(data)
    user_profile = _as_dict(payload.get("user_profile") or payload.get("user"))

    return {
        "age": user_profile.get("age"),
        "state": _as_string(user_profile.get("state")),
        "registered": bool(user_profile.get("registered", False)),
        "verified": bool(user_profile.get("verified", False)),
    }


def _normalize_interaction(data: Any) -> dict[str, Any]:
    """Build a valid interaction payload for an interaction document."""
    payload = _as_dict(data)

    return {
        "message": _as_string(payload.get("message")),
        "response": _as_string(payload.get("response")),
        "stage": _as_string(payload.get("stage")),
        "timestamp": _utc_now(),
    }


def _to_iso_timestamp(value: Any) -> str | None:
    """Normalize datetime-like values to ISO strings for API responses."""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    return None


def _build_summary_base(session_id: Any) -> dict[str, Any]:
    """Return the shared shape used by the session summary endpoint."""
    return {
        "session_id": _as_string(session_id),
        "source": "unavailable",
        "user_profile": {},
        "created_at": None,
        "interactions_count": 0,
        "interactions": [],
        "note": "Firebase is unavailable.",
    }


def create_session(data: Any) -> str | None:
    """Create a Firestore session document and return its session ID."""
    db = _get_firestore_client()
    if db is None:
        return None

    session_payload = {
        "user_profile": _normalize_user_profile(data),
        "created_at": _utc_now(),
    }

    try:
        document_ref = db.collection(SESSIONS_COLLECTION).document()
        document_ref.set(session_payload)
        return document_ref.id
    except Exception as exc:
        return None


def log_interaction(session_id: Any, data: Any) -> str | None:
    """Add an interaction document under the given Firestore session."""
    db = _get_firestore_client()
    safe_session_id = _as_string(session_id).strip()

    if db is None:
        return None

    if not safe_session_id:
        return None

    interaction_payload = _normalize_interaction(data)

    try:
        document_ref = (
            db.collection(SESSIONS_COLLECTION)
            .document(safe_session_id)
            .collection(INTERACTIONS_COLLECTION)
            .document()
        )
        document_ref.set(interaction_payload)
        return document_ref.id
    except Exception as exc:
        return None


def get_session_summary(session_id: Any) -> dict[str, Any]:
    """Return a session summary from Firestore with graceful service fallbacks."""
    safe_session_id = _as_string(session_id).strip()
    summary = _build_summary_base(safe_session_id)

    if not safe_session_id:
        summary["source"] = "invalid"
        summary["note"] = "Session ID is required."
        return summary

    db = _get_firestore_client()
    if db is None:
        if _init_error:
            summary["note"] = _init_error
        return summary

    try:
        session_ref = db.collection(SESSIONS_COLLECTION).document(safe_session_id)
        session_snapshot = session_ref.get()
    except Exception as exc:
        summary["source"] = "error"
        summary["note"] = f"Session lookup failed: {exc.__class__.__name__}"
        return summary

    if not getattr(session_snapshot, "exists", False):
        summary["source"] = "not_found"
        summary["note"] = "Session was not found in Firebase."
        return summary

    session_payload = _as_dict(session_snapshot.to_dict())

    interactions = []
    try:
        interaction_stream = (
            session_ref.collection(INTERACTIONS_COLLECTION)
            .order_by("timestamp")
            .stream()
        )
    except Exception:
        interaction_stream = session_ref.collection(INTERACTIONS_COLLECTION).stream()

    for index, document in enumerate(interaction_stream):
        if index >= 25:
            break
        payload = _as_dict(document.to_dict())
        interactions.append(
            {
                "message": _as_string(payload.get("message")),
                "response": _as_string(payload.get("response")),
                "stage": _as_string(payload.get("stage")),
                "timestamp": _to_iso_timestamp(payload.get("timestamp")),
            }
        )

    summary.update(
        {
            "source": "firebase",
            "user_profile": _as_dict(session_payload.get("user_profile")),
            "created_at": _to_iso_timestamp(session_payload.get("created_at")),
            "interactions_count": len(interactions),
            "interactions": interactions,
            "note": "Session summary loaded from Firebase.",
        }
    )
    return summary
