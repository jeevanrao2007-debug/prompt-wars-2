import os
import json
import re
from typing import Any

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover
    genai = None
    types = None


MODEL_NAME = "gemini-1.5-flash"
TEMPERATURE = 0.3
INTENT_LABELS = {"ELIGIBILITY", "REGISTER", "VERIFY", "VOTE", "GENERAL"}
UNRELATED_RESPONSE = "Please contact ECI helpline 1950 for assistance."
MAX_FOLLOW_UP_QUESTIONS = 3
_client = None


def _get_client() -> Any | None:
    """Create and cache a Gemini client from the configured environment variable.

    Returns:
        Any | None: Initialized Gemini client or None if unavailable.
    """
    global _client

    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return None

    try:
        _client = genai.Client(api_key=api_key)
        return _client
    except Exception:
        return None


def _extract_text(response: Any) -> str:
    """Extract text safely from a Gemini response object.

    Args:
        response (Any): Gemini response object.

    Returns:
        str: Normalized response text.
    """
    text = getattr(response, "text", "")
    return text.strip() if isinstance(text, str) else ""


def _format_history(history: Any) -> str:
    """Format recent conversation history into a readable prompt block.

    Args:
        history (Any): Raw conversation history items.

    Returns:
        str: Prompt-friendly history block.
    """
    if not isinstance(history, list):
        return "No prior conversation."

    formatted_messages = []
    for item in history[-10:]:
        if isinstance(item, dict):
            role = item.get("role", "user")
            content = item.get("message") or item.get("content") or ""
            formatted_messages.append(f"{role}: {content}")
        else:
            formatted_messages.append(str(item))

    return "\n".join(formatted_messages) if formatted_messages else "No prior conversation."


def _normalize_items(items: Any) -> list[str]:
    """Normalize prompt list values into readable strings.

    Args:
        items (Any): Raw list-like values.

    Returns:
        list[str]: Cleaned list of strings.
    """
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _deduplicate_strings(items: list[str]) -> list[str]:
    """Return values in insertion order without duplicates (case-insensitive).

    Args:
        items (list[str]): Input strings.

    Returns:
        list[str]: Deduplicated strings in insertion order.
    """
    unique_items = []
    seen = set()

    for item in items:
        normalized_key = item.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        unique_items.append(item)

    return unique_items


def _format_items(items: Any, empty_message: str) -> str:
    """Format list-like values as bullet lines for prompt context.

    Args:
        items (Any): Raw list-like values.
        empty_message (str): Fallback message when list is empty.

    Returns:
        str: Bullet-formatted list or fallback message.
    """
    normalized_items = _normalize_items(items)
    return "\n".join(f"- {item}" for item in normalized_items) or f"- {empty_message}"


def _build_user_profile_summary(context: Any) -> str:
    """Build a concise user profile summary for personalized Gemini responses.

    Args:
        context (Any): Request context containing user profile fields.

    Returns:
        str: Multi-line summary of user details.
    """
    if not isinstance(context, dict):
        return "No user profile provided."

    user_profile = context.get("user_profile")
    if not isinstance(user_profile, dict):
        user_profile = {}

    age = user_profile.get("age", "unknown")
    state = context.get("state") or user_profile.get("state") or "unknown"
    registered = user_profile.get("registered", "unknown")
    verified = user_profile.get("verified", "unknown")
    readiness_score = context.get("readiness_score", "unknown")

    return (
        f"Age: {age}\n"
        f"State/UT: {state}\n"
        f"Registered: {registered}\n"
        f"Verified: {verified}\n"
        f"Readiness score: {readiness_score}"
    )


def _get_intent_guidance(intent: str) -> str:
    """Return response guidance tailored to the detected intent.

    Args:
        intent (str): Detected intent label.

    Returns:
        str: Guidance for response generation.
    """
    guidance_by_intent = {
        "ELIGIBILITY": (
            "Explain eligibility calmly and clearly. Mention age, citizenship, and readiness without overcomplicating it."
        ),
        "REGISTER": (
            "Guide the user through Form 6, document preparation, and the official voter portal."
        ),
        "VERIFY": (
            "Focus on voter status lookup, EPIC usage, electoral roll verification, and correction/update options."
        ),
        "VOTE": (
            "Focus on polling booth lookup, identity document readiness, polling hours, and the voting-day process."
        ),
        "GENERAL": (
            "Answer related Indian election process questions directly, and connect back to the user's current stage when useful."
        ),
    }
    return guidance_by_intent.get(intent, guidance_by_intent["GENERAL"])


def _fallback_follow_up_questions(stage: str, intent: str) -> list[str]:
    """Return follow-up questions when Gemini output is unavailable or malformed.

    Args:
        stage (str): Current voter stage.
        intent (str): Detected intent label.

    Returns:
        list[str]: Suggested follow-up questions.
    """
    stage_questions = {
        "ineligible": [
            "What documents should I prepare before I turn 18?",
            "How early can I start collecting voter registration documents?",
            "Where can I check official voter eligibility rules?",
        ],
        "registration": [
            "How do I fill Form 6 step by step?",
            "Which documents are accepted for voter registration?",
            "How long does voter registration usually take?",
        ],
        "verification": [
            "How can I verify my name in the electoral roll?",
            "What should I do if my voter details are incorrect?",
            "How do I use my EPIC number to check status?",
        ],
        "ready_to_vote": [
            "What should I carry to the polling booth?",
            "How do I find my polling booth quickly?",
            "What are polling hours on election day?",
        ],
    }
    intent_questions = {
        "ELIGIBILITY": [
            "What are the age and citizenship requirements to vote?",
            "Can a first-time voter register online?",
            "Which official portal explains voter eligibility?",
        ],
        "REGISTER": [
            "How can I track my Form 6 application status?",
            "What common mistakes delay voter registration?",
            "Can I register if I recently moved to a new state?",
        ],
        "VERIFY": [
            "Where can I search my voter details online?",
            "How do I update errors in the electoral roll?",
            "What if my name is missing from the voter list?",
        ],
        "VOTE": [
            "What documents are valid at the polling booth?",
            "Can I vote if I do not have my EPIC card?",
            "How early should I reach the booth on voting day?",
        ],
    }

    combined_questions = []
    combined_questions.extend(stage_questions.get(stage, []))
    combined_questions.extend(intent_questions.get(intent, []))
    combined_questions.extend(
        [
            "How can I use the official ECI portal for my next step?",
            "What should I do after completing this current step?",
        ]
    )

    deduplicated = _deduplicate_strings(combined_questions)
    return deduplicated[:MAX_FOLLOW_UP_QUESTIONS]


def _sanitize_follow_up_questions(items: Any, defaults: list[str]) -> list[str]:
    """Normalize follow-up questions and guarantee 2 to 3 usable suggestions.

    Args:
        items (Any): Raw follow-up questions.
        defaults (list[str]): Fallback questions to ensure coverage.

    Returns:
        list[str]: Cleaned follow-up questions.
    """
    normalized_items = _normalize_items(items)
    deduplicated = _deduplicate_strings(normalized_items)

    question_like = [
        value
        for value in deduplicated
        if value and len(value) <= 160 and value != UNRELATED_RESPONSE
    ]

    merged = question_like + [item for item in defaults if item not in question_like]
    merged = _deduplicate_strings(merged)

    if len(merged) < 2:
        merged.extend(
            [
                "What is my next official step in the election process?",
                "Which ECI link should I open first?",
            ]
        )
        merged = _deduplicate_strings(merged)

    return merged[:MAX_FOLLOW_UP_QUESTIONS]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract and parse the first JSON object from model output.

    Args:
        text (str): Raw model output text.

    Returns:
        dict[str, Any] | None: Parsed JSON object, if available.
    """
    if not isinstance(text, str):
        return None

    stripped_text = text.strip()
    if not stripped_text:
        return None

    if stripped_text.startswith("```"):
        stripped_text = re.sub(r"^```(?:json)?", "", stripped_text).strip()
        stripped_text = re.sub(r"```$", "", stripped_text).strip()

    try:
        parsed = json.loads(stripped_text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", stripped_text)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _fallback_response(context: Any) -> str:
    """Build a concise conversational fallback response.

    Args:
        context (Any): Request context with stage guidance.

    Returns:
        str: Fallback response text.
    """
    stage = context.get("stage", "general") if isinstance(context, dict) else "general"
    next_steps = context.get("next_steps", []) if isinstance(context, dict) else []
    links = context.get("links", []) if isinstance(context, dict) else []

    stage_messages = {
        "ineligible": "You are not eligible to vote yet, but you can start preparing now.",
        "registration": "You are eligible to vote, but you still need to complete voter registration.",
        "verification": "You are registered, so the next important step is to verify your voter details.",
        "ready_to_vote": "You are fully ready to vote. Here is what you should do on election day:",
    }
    intro = stage_messages.get(stage, "Here is the most useful election guidance for your next step.")
    steps = next_steps or ["Check the official Election Commission of India voter services portal."]
    steps_text = "\n".join(f"- {step}" for step in steps)

    if links:
        primary_link = links[0]
        return f"{intro}\n\n{steps_text}\n\nUse the official portal for the latest details: {primary_link}"

    return f"{intro}\n\n{steps_text}\n\nMake sure your details are correct before moving to the next step."


def _build_response_prompt(
    message: str,
    stage: str,
    intent: str,
    context: Any,
    history: str,
) -> str:
    """Build the Gemini response prompt with personalized election guidance context.

    Args:
        message (str): User message.
        stage (str): Current voter stage.
        intent (str): Detected intent label.
        context (Any): Request context with guidance data.
        history (str): Formatted conversation history.

    Returns:
        str: Prompt for the Gemini model.
    """
    if not isinstance(context, dict):
        context = {}

    user_profile_summary = _build_user_profile_summary(context)
    checklist_block = _format_items(context.get("checklist", []), "No stage checklist available.")
    decision_checklist_block = _format_items(
        context.get("decision_checklist", []),
        "No readiness checklist available.",
    )
    steps_block = _format_items(context.get("next_steps", []), "No next steps available.")
    links_block = _format_items(context.get("links", []), "No official links available.")
    intent_guidance = _get_intent_guidance(intent)

    return (
        "Use the following structured election guidance to create a personalized response.\n\n"
        f"Detected intent: {intent}\n"
        f"Intent guidance: {intent_guidance}\n"
        f"Current stage: {stage}\n\n"
        f"User profile:\n{user_profile_summary}\n\n"
        f"Readiness checklist:\n{decision_checklist_block}\n\n"
        f"Stage guidance checklist:\n{checklist_block}\n\n"
        f"Recommended next steps:\n{steps_block}\n\n"
        f"Official links:\n{links_block}\n\n"
        f"Conversation history:\n{history}\n\n"
        "Response instructions:\n"
        "- Return valid JSON only (no markdown, no code fences).\n"
        "- JSON schema: {\"response\": string, \"follow_up_questions\": [string, string, optional string]}.\n"
        "- follow_up_questions must contain 2 to 3 short, clickable next questions.\n"
        "- Start with one natural sentence that reflects the user's profile and question.\n"
        "- Give 2 to 5 clear, actionable steps.\n"
        "- Include an official link only when it helps the user's current question.\n"
        "- Add a short caution or reminder only if it is useful.\n"
        "- Stay grounded in the provided guidance and do not invent rules, deadlines, or documents.\n\n"
        f"User message:\n{message}"
    )


def detect_intent(message: str) -> str:
    """Classify intent locally so response generation stays a single Gemini call.

    Args:
        message (str): User message.

    Returns:
        str: Intent label.
    """
    if not isinstance(message, str) or not message.strip():
        return "GENERAL"

    normalized_message = message.casefold()

    keyword_groups = {
        "ELIGIBILITY": [
            "eligible",
            "eligibility",
            "citizen",
            "citizenship",
            "first time voter",
            "can i vote",
            "turn 18",
        ],
        "REGISTER": [
            "register",
            "registration",
            "form 6",
            "enroll",
            "enrol",
            "apply voter id",
            "new voter",
        ],
        "VERIFY": [
            "verify",
            "verification",
            "epic",
            "electoral roll",
            "voter list",
            "status",
            "correction",
            "update details",
        ],
        "VOTE": [
            "polling booth",
            "booth",
            "vote",
            "voting day",
            "polling day",
            "evm",
            "ballot",
            "what should i carry",
        ],
    }

    for label, keywords in keyword_groups.items():
        if any(keyword in normalized_message for keyword in keywords):
            return label

    return "GENERAL"


def generate_response_bundle(context: Any) -> dict[str, Any]:
    """Generate reply text and follow-up questions in one Gemini call.

    Args:
        context (Any): Request context with guidance and history.

    Returns:
        dict[str, Any]: Response text and follow-up questions.
    """
    stage = context.get("stage", "general") if isinstance(context, dict) else "general"
    message = str(context.get("message", "")).strip() if isinstance(context, dict) else ""
    intent = detect_intent(message)
    fallback_text = _fallback_response(context)
    fallback_questions = _fallback_follow_up_questions(stage, intent)

    client = _get_client()
    # Fall back to deterministic guidance when Gemini is unavailable.
    if client is None or not isinstance(context, dict):
        return {
            "response": fallback_text,
            "follow_up_questions": fallback_questions,
        }

    history = _format_history(context.get("history", []))

    system_instruction = (
        "You are Matdata Sahayak, a helpful assistant for Indian election process education. "
        "Answer questions about voter eligibility, registration, verification, voting, polling booths, "
        "official ECI portals, documents, EPIC, voter status, election-day preparation, and closely related civic voting topics in India. "
        f"Only if the user asks about a clearly unrelated topic, reply with exactly: {UNRELATED_RESPONSE} "
        "Personalize the answer using the user's age, state, registration status, verification status, readiness score, stage, and conversation history. "
        "Keep responses concise, friendly, authoritative, and grounded in the provided guidance. "
        "Avoid a rigid template feel and vary phrasing naturally based on the user's intent. "
        "Do not use raw headings like 'Checklist' or 'Next steps' unless the user asks for them. "
        "Output strictly valid JSON with response and follow_up_questions fields only."
    )
    prompt = _build_response_prompt(message, stage, intent, context, history)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=TEMPERATURE,
            ),
        )
        text = _extract_text(response)
        parsed = _extract_json_object(text)

        if parsed:
            response_text = str(parsed.get("response", "")).strip() or fallback_text
            questions = _sanitize_follow_up_questions(
                parsed.get("follow_up_questions", []),
                fallback_questions,
            )
            return {
                "response": response_text,
                "follow_up_questions": questions,
            }

        fallback_questions_from_text = _sanitize_follow_up_questions([], fallback_questions)
        return {
            "response": text or fallback_text,
            "follow_up_questions": fallback_questions_from_text,
        }
    except Exception:
        return {
            "response": fallback_text,
            "follow_up_questions": fallback_questions,
        }


def generate_response(context: Any) -> str:
    """Return a text-only response for legacy callers.

    Args:
        context (Any): Request context with guidance and history.

    Returns:
        str: Response text.
    """
    return generate_response_bundle(context).get("response", _fallback_response(context))
