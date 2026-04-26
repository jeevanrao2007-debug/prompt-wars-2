const API_BASE_URL = window.APP_CONFIG?.API_BASE_URL;

if (!API_BASE_URL) {
    console.error("API_BASE_URL missing. config.js not loaded.");
}

const INDIAN_STATES = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
];

const state = {
    stage: "Not evaluated",
    sessionId: null,
    history: [],
};

const elements = {
    profileForm: document.getElementById("profileForm"),
    age: document.getElementById("age"),
    state: document.getElementById("state"),
    registered: document.getElementById("registered"),
    verified: document.getElementById("verified"),
    stageText: document.getElementById("stageText"),
    scoreText: document.getElementById("scoreText"),
    stageBadge: document.getElementById("stageBadge"),
    checklist: document.getElementById("checklist"),
    progressBar: document.getElementById("progressBar"),
    progressTrack: document.querySelector(".progress-track"),
    scoreActionHint: document.getElementById("scoreActionHint"),
    chatForm: document.getElementById("chatForm"),
    chatInput: document.getElementById("chatInput"),
    chatMessages: document.getElementById("chatMessages"),
    typingIndicator: document.getElementById("typingIndicator"),
    suggestions: document.getElementById("suggestions"),
    sessionSummary: document.getElementById("sessionSummary"),
    summaryMeta: document.getElementById("summaryMeta"),
    summaryInteractions: document.getElementById("summaryInteractions"),
    timeline: document.getElementById("timeline"),
    mapFrame: document.getElementById("mapFrame"),
    locateBtn: document.getElementById("locateBtn"),
    appStatus: document.getElementById("appStatus"),
};

function init() {
    populateStates();
    bindEvents();
    Maps.updateForState(elements.mapFrame, elements.state.value);
    updateReadinessHint(getUserProfile());
    renderSuggestions([]);
    renderSessionSummary(null);
}

function populateStates() {
    elements.state.innerHTML = INDIAN_STATES.map((name) => {
        const selected = name === "Delhi" ? "selected" : "";
        return `<option value="${name}" ${selected}>${name}</option>`;
    }).join("");
}

function bindEvents() {
    elements.profileForm.addEventListener("submit", handleEvaluate);
    elements.chatForm.addEventListener("submit", handleChatSubmit);
    elements.state.addEventListener("change", () => Maps.updateForState(elements.mapFrame, elements.state.value));
    elements.locateBtn.addEventListener("click", handleLocate);

    elements.timeline.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-query]");
        if (button) {
            sendChatMessage(button.dataset.query);
        }
    });

    elements.suggestions.addEventListener("click", (event) => {
        const button = event.target.closest("button");
        if (button) {
            sendChatMessage(button.textContent.trim());
        }
    });
}

function getUserProfile() {
    return {
        age: Number(elements.age.value || 0),
        state: elements.state.value,
        registered: elements.registered.value === "true",
        verified: elements.verified.value === "true",
    };
}

async function postJson(path, payload) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
    }

    return response.json();
}

async function handleEvaluate(event) {
    event.preventDefault();

    try {
        const data = await postJson("/api/evaluate", getUserProfile());
        state.stage = data.stage || "Not evaluated";
        state.sessionId = data.session_id || state.sessionId;
        updateEvaluation(data);
        await refreshSessionSummary();
        setStatus("Readiness evaluation updated.");
    } catch (error) {
        const message = "Unable to evaluate right now. Please make sure the backend is running.";
        addMessage("bot", message);
        setStatus(message);
    }
}

function updateEvaluation(data) {
    const score = Number(data.readiness_score || 0);
    const clampedScore = Math.max(0, Math.min(score, 100));
    elements.stageText.textContent = formatStage(data.stage);
    elements.scoreText.textContent = `${clampedScore}%`;
    setStageVisual(data.stage);
    elements.progressBar.style.width = `${clampedScore}%`;
    elements.progressTrack.setAttribute("aria-valuenow", String(clampedScore));
    document.documentElement.style.setProperty("--score", `${clampedScore}%`);
    updateReadinessHint(getUserProfile());
    renderChecklist(data.checklist || []);
}

function updateReadinessHint(profile) {
    if (!elements.scoreActionHint) {
        return;
    }

    if (!profile || Number(profile.age) < 18) {
        elements.scoreActionHint.textContent = "Turn 18 to unlock +30 eligibility points.";
        return;
    }

    if (!profile.registered) {
        elements.scoreActionHint.textContent = "Complete Form 6 voter registration to gain +30 points.";
        return;
    }

    if (!profile.verified) {
        elements.scoreActionHint.textContent = "Verify your voter details or EPIC to gain +40 points.";
        return;
    }

    elements.scoreActionHint.textContent = "You are at 100%. Keep your ID ready to stay fully election-ready.";
}

function renderChecklist(items) {
    if (!items.length) {
        elements.checklist.innerHTML = "<li>No checklist available.</li>";
        return;
    }

    elements.checklist.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

async function handleChatSubmit(event) {
    event.preventDefault();
    const message = elements.chatInput.value.trim();
    if (!message) {
        return;
    }
    elements.chatInput.value = "";
    await sendChatMessage(message);
}

async function sendChatMessage(message) {
    addMessage("user", message);
    state.history.push({ role: "user", message });
    setTyping(true);

    const payload = {
        user: getUserProfile(),
        message,
        session_id: state.sessionId,
        history: state.history.slice(-10),
    };

    try {
        const data = await postJson("/api/chat", payload);
        const responseText = data.response || "No response received.";
        const followUps = Array.isArray(data.follow_up_questions) ? data.follow_up_questions : [];
        state.stage = data.stage || state.stage;
        state.sessionId = data.session_id || state.sessionId;
        setStageVisual(state.stage);
        addMessage("bot", responseText);
        renderSuggestions(followUps);
        state.history.push({ role: "assistant", message: responseText });
        await refreshSessionSummary();
        setStatus("Assistant response received.");
    } catch (error) {
        const fallback = "Unable to reach the assistant right now. Please try again after checking the backend server.";
        addMessage("bot", fallback);
        renderSuggestions([]);
        state.history.push({ role: "assistant", message: fallback });
        setStatus(fallback);
    } finally {
        setTyping(false);
    }
}

function getDefaultFollowUps() {
    return [
        "Am I eligible to vote?",
        "How do I apply with Form 6?",
        "How do I check my EPIC status?",
    ];
}

async function refreshSessionSummary() {
    if (!state.sessionId) {
        renderSessionSummary(null);
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/session/${encodeURIComponent(state.sessionId)}/summary`);
        if (!response.ok) {
            throw new Error(`Summary request failed with status ${response.status}`);
        }
        const data = await response.json();
        renderSessionSummary(data);
    } catch (error) {
        renderSessionSummary({
            session_id: state.sessionId,
            source: "error",
            note: "Could not load Firebase summary right now.",
            interactions_count: 0,
            interactions: [],
        });
    }
}

function renderSessionSummary(data) {
    if (!elements.summaryMeta || !elements.summaryInteractions) {
        return;
    }

    if (!data) {
        elements.summaryMeta.textContent = "No session yet. Evaluate profile to start a demo session.";
        elements.summaryInteractions.innerHTML = "<li>Interactions will appear here during the demo.</li>";
        return;
    }

    const source = String(data.source || "unknown");
    const sessionId = String(data.session_id || state.sessionId || "-");
    const count = Number(data.interactions_count || 0);
    const note = String(data.note || "");

    elements.summaryMeta.textContent = `Session ${sessionId} • source: ${source} • interactions: ${count}${note ? ` • ${note}` : ""}`;

    const interactions = Array.isArray(data.interactions) ? data.interactions.slice(-3).reverse() : [];
    if (!interactions.length) {
        elements.summaryInteractions.innerHTML = "<li>No logged interactions yet.</li>";
        return;
    }

    elements.summaryInteractions.innerHTML = interactions
        .map((entry) => {
            const stage = escapeHtml(entry.stage || "");
            const message = escapeHtml(entry.message || "");
            return `<li><strong>${stage || "stage"}</strong>: ${message || "(empty message)"}</li>`;
        })
        .join("");
}

function renderSuggestions(items) {
    const normalized = Array.isArray(items)
        ? items.map((item) => String(item).trim()).filter(Boolean).slice(0, 3)
        : [];

    const suggestions = normalized.length ? normalized : getDefaultFollowUps();
    elements.suggestions.innerHTML = suggestions
        .map((item) => `<button type="button">${escapeHtml(item)}</button>`)
        .join("");
}

function addMessage(type, text) {
    const message = document.createElement("div");
    message.className = `message ${type}`;
    
    if (type === "bot") {
        const label = document.createElement("span");
        label.className = "ai-label";
        label.textContent = "AI Guidance";
        message.appendChild(label);
    }

    const textNode = document.createTextNode(text);
    message.appendChild(textNode);
    
    elements.chatMessages.appendChild(message);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function setTyping(isTyping) {
    elements.typingIndicator.hidden = !isTyping;
    if (isTyping) {
        setStatus("Assistant is typing.");
    }
}

function setStatus(message) {
    elements.appStatus.textContent = message;
}

function setStageVisual(stage) {
    const normalizedStage = normalizeStage(stage);
    elements.stageBadge.textContent = formatStage(stage);
    elements.stageBadge.className = "stage-badge";

    if (normalizedStage) {
        elements.stageBadge.classList.add(`stage-${normalizedStage}`);
    }

    updateTimeline(normalizedStage);
}

function updateTimeline(stage) {
    const order = ["registration", "verification", "booth", "ready_to_vote", "results"];
    const activeStage = stage === "ineligible" ? "registration" : stage;
    const activeIndex = order.indexOf(activeStage);

    elements.timeline.querySelectorAll("button[data-step]").forEach((button) => {
        const step = button.dataset.step;
        const stepIndex = order.indexOf(step);
        button.classList.toggle("is-active", step === activeStage);
        button.classList.toggle("is-complete", activeIndex > -1 && stepIndex > -1 && stepIndex < activeIndex);
        if (step === activeStage) {
            button.setAttribute("aria-current", "step");
        } else {
            button.removeAttribute("aria-current");
        }
    });
}

function handleLocate() {
    if (!navigator.geolocation) {
        Maps.updateForState(elements.mapFrame, elements.state.value);
        setStatus("Geolocation is unavailable in this browser. Showing map by selected state.");
        return;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            Maps.updateForLocation(
                elements.mapFrame,
                position.coords.latitude,
                position.coords.longitude,
            );
            setStatus("Map updated using your current location.");
        },
        () => {
            Maps.updateForState(elements.mapFrame, elements.state.value);
            setStatus("Could not access your location. Showing map by selected state.");
        },
        {
            enableHighAccuracy: true,
            timeout: 8000,
            maximumAge: 60000,
        },
    );
}

function formatStage(stage) {
    if (!stage) {
        return "Not evaluated";
    }
    return String(stage).replaceAll("_", " ");
}

function normalizeStage(stage) {
    if (!stage) {
        return "";
    }
    return String(stage).toLowerCase().replaceAll(" ", "_");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

init();
