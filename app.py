import time
import uuid

import streamlit as st
from dotenv import load_dotenv

from diet_agent import run_agent
from monitoring import load_all_traces, save_trace, update_feedback
from user_profile import (
    ACTIVITY_LEVELS,
    CUISINE_OPTIONS,
    DAYS_OF_WEEK,
    create_profile,
    is_onboarding_complete,
    load_profile,
    profile_exists,
    profile_to_context,
    update_profile,
    verify_password,
)

load_dotenv()

st.set_page_config(page_title="AI Diet Coach", page_icon="🥗", layout="wide")

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_feedback" not in st.session_state:
    st.session_state.pending_feedback = {}
if "show_profile_editor" not in st.session_state:
    st.session_state.show_profile_editor = False


# ---------------------------------------------------------------------------
# Auth screens
# ---------------------------------------------------------------------------

def show_registration():
    st.title("AI Diet Coach")
    st.subheader("Create your account")
    st.caption("No account found. Set up your profile to get started.")

    with st.form("register_form"):
        username = st.text_input("Choose a username")
        password = st.text_input("Choose a password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", use_container_width=True, type="primary")

    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif len(password) < 6:
            st.error("Password must be at least 6 characters.")
        else:
            create_profile(username, password)
            st.session_state.logged_in = True
            st.rerun()


def show_login():
    st.title("AI Diet Coach")
    st.subheader("Welcome back!")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True, type="primary")

    if submitted:
        profile = load_profile()
        if (
            profile
            and profile.get("username") == username
            and verify_password(password, profile["password_hash"], profile["password_salt"])
        ):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Incorrect username or password.")


# ---------------------------------------------------------------------------
# Onboarding wizard
# ---------------------------------------------------------------------------

def show_onboarding():
    st.title("Let's set up your profile")
    st.caption("This helps the coach personalise every recommendation for you.")

    profile = load_profile() or {}

    with st.form("onboarding_form"):
        st.subheader("Your weight goal")
        col1, col2 = st.columns(2)
        current_weight = col1.number_input(
            "Current weight (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("current_weight_kg") or 70.0), step=0.5,
        )
        target_weight = col2.number_input(
            "Target weight (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("target_weight_kg") or 65.0), step=0.5,
        )
        deadline = st.date_input("Goal deadline", value=None)

        st.subheader("Diet preferences")
        restrictions_input = st.text_input(
            "Dietary restrictions / allergies",
            value=", ".join(profile.get("dietary_restrictions", [])),
            placeholder="e.g. no pork, lactose intolerant, nut allergy",
        )
        cuisines = st.multiselect(
            "Preferred cuisines",
            options=CUISINE_OPTIONS,
            default=profile.get("preferred_cuisines", []),
        )

        st.subheader("Your schedule")
        busy_days = st.multiselect(
            "Which days are you usually busy? (less time to cook)",
            options=DAYS_OF_WEEK,
            default=profile.get("busy_days", []),
        )

        st.subheader("Location & activity")
        location = st.text_input(
            "Your city or area",
            value=profile.get("location", ""),
            placeholder="e.g. Bangkok, Thailand",
        )
        activity = st.selectbox(
            "Activity level",
            options=[""] + ACTIVITY_LEVELS,
            index=(ACTIVITY_LEVELS.index(profile["activity_level"]) + 1)
            if profile.get("activity_level") in ACTIVITY_LEVELS else 0,
        )

        submitted = st.form_submit_button("Save and start coaching", use_container_width=True, type="primary")

    if submitted:
        restrictions = [r.strip() for r in restrictions_input.split(",") if r.strip()]
        update_profile({
            "current_weight_kg": current_weight,
            "target_weight_kg": target_weight,
            "deadline": str(deadline) if deadline else None,
            "dietary_restrictions": restrictions,
            "preferred_cuisines": cuisines,
            "busy_days": busy_days,
            "location": location,
            "activity_level": activity,
            "onboarding_complete": True,
        })
        st.success("Profile saved!")
        st.rerun()


# ---------------------------------------------------------------------------
# Profile editor (inline in sidebar)
# ---------------------------------------------------------------------------

def show_profile_editor():
    profile = load_profile() or {}
    st.sidebar.subheader("Edit Profile")

    with st.sidebar.form("profile_editor"):
        col1, col2 = st.columns(2)
        current_weight = col1.number_input(
            "Current (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("current_weight_kg") or 70.0), step=0.5,
        )
        target_weight = col2.number_input(
            "Target (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("target_weight_kg") or 65.0), step=0.5,
        )
        deadline = st.date_input("Deadline", value=None)

        restrictions_input = st.text_input(
            "Restrictions / allergies",
            value=", ".join(profile.get("dietary_restrictions", [])),
        )
        cuisines = st.multiselect(
            "Preferred cuisines",
            options=CUISINE_OPTIONS,
            default=profile.get("preferred_cuisines", []),
        )
        busy_days = st.multiselect(
            "Busy days",
            options=DAYS_OF_WEEK,
            default=profile.get("busy_days", []),
        )
        location = st.text_input("City / area", value=profile.get("location", ""))
        activity = st.selectbox(
            "Activity level",
            options=[""] + ACTIVITY_LEVELS,
            index=(ACTIVITY_LEVELS.index(profile["activity_level"]) + 1)
            if profile.get("activity_level") in ACTIVITY_LEVELS else 0,
        )

        save = st.form_submit_button("Save changes", use_container_width=True, type="primary")
        cancel = st.form_submit_button("Cancel", use_container_width=True)

    if save:
        restrictions = [r.strip() for r in restrictions_input.split(",") if r.strip()]
        update_profile({
            "current_weight_kg": current_weight,
            "target_weight_kg": target_weight,
            "deadline": str(deadline) if deadline else profile.get("deadline"),
            "dietary_restrictions": restrictions,
            "preferred_cuisines": cuisines,
            "busy_days": busy_days,
            "location": location,
            "activity_level": activity,
            "onboarding_complete": True,
        })
        st.session_state.show_profile_editor = False
        st.sidebar.success("Profile updated!")
        st.rerun()

    if cancel:
        st.session_state.show_profile_editor = False
        st.rerun()


# ---------------------------------------------------------------------------
# Route: not logged in
# ---------------------------------------------------------------------------

if not st.session_state.logged_in:
    if not profile_exists():
        show_registration()
    else:
        show_login()
    st.stop()

# ---------------------------------------------------------------------------
# Route: logged in but onboarding not done
# ---------------------------------------------------------------------------

if not is_onboarding_complete():
    show_onboarding()
    st.stop()

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

profile = load_profile() or {}
profile_context = profile_to_context(profile)

# Sidebar
with st.sidebar:
    st.title("AI Diet Coach")
    st.caption(f"Logged in as **{profile.get('username', '')}**")
    st.divider()

    # Profile summary
    cw = profile.get("current_weight_kg")
    tw = profile.get("target_weight_kg")
    dl = profile.get("deadline")
    if cw and tw:
        st.metric("Current weight", f"{cw} kg")
        st.metric("Target weight", f"{tw} kg")
        if dl:
            st.caption(f"Deadline: {dl}")

    cuisines = profile.get("preferred_cuisines", [])
    if cuisines:
        st.caption(f"Cuisines: {', '.join(cuisines)}")

    restrictions = profile.get("dietary_restrictions", [])
    if restrictions:
        st.caption(f"Restrictions: {', '.join(restrictions)}")

    st.divider()

    col_edit, col_new = st.columns(2)
    if col_edit.button("Edit profile", use_container_width=True):
        st.session_state.show_profile_editor = not st.session_state.show_profile_editor
        st.rerun()
    if col_new.button("New chat", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.pending_feedback = {}
        st.rerun()

    if st.button("Log out", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.messages = []
        st.rerun()

    st.divider()

    # Profile editor
    if st.session_state.show_profile_editor:
        show_profile_editor()
    else:
        st.subheader("Session stats")
        traces = load_all_traces()
        session_traces = [t for t in traces if t["session_id"] == st.session_state.session_id]
        st.metric("Turns this session", len(session_traces))
        if session_traces:
            total_tokens = sum(t["input_tokens"] + t["output_tokens"] for t in session_traces)
            st.metric("Tokens used", f"{total_tokens:,}")
            avg_s = sum(t["duration_seconds"] for t in session_traces) / len(session_traces)
            st.metric("Avg response time", f"{avg_s:.1f}s")

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

st.title("AI Diet Coach")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            with st.expander("Tools called", expanded=False):
                for tc in msg["tool_calls"]:
                    st.code(f"{tc['name']}({tc['arguments']})", language="python")
        st.markdown(msg["content"])

        if msg["role"] == "assistant" and msg.get("trace_id"):
            trace_id = msg["trace_id"]
            if not st.session_state.pending_feedback.get(trace_id):
                col1, col2, col3 = st.columns([1, 1, 8])
                if col1.button("👍", key=f"up_{trace_id}"):
                    update_feedback(trace_id, 1)
                    st.session_state.pending_feedback[trace_id] = True
                    st.rerun()
                if col2.button("👎", key=f"down_{trace_id}"):
                    update_feedback(trace_id, -1)
                    st.session_state.pending_feedback[trace_id] = True
                    st.rerun()
            else:
                st.caption("Feedback recorded. Thanks!")

user_input = st.chat_input("Ask your diet coach...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        tool_log = st.empty()
        answer_ph = st.empty()

        with st.spinner("Thinking..."):
            t0 = time.time()
            result = run_agent(user_input, user_profile_context=profile_context)
            duration = time.time() - t0

        if result.tool_calls:
            with tool_log.expander("Tools called", expanded=False):
                for tc in result.tool_calls:
                    st.code(f"{tc.name}({tc.arguments})", language="python")

        answer_ph.markdown(result.answer)

        trace_id = save_trace(
            question=user_input,
            result=result,
            duration_seconds=duration,
            session_id=st.session_state.session_id,
        )

        col1, col2, col3 = st.columns([1, 1, 8])
        if col1.button("👍", key=f"up_{trace_id}"):
            update_feedback(trace_id, 1)
            st.session_state.pending_feedback[trace_id] = True
        if col2.button("👎", key=f"down_{trace_id}"):
            update_feedback(trace_id, -1)
            st.session_state.pending_feedback[trace_id] = True

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.answer,
        "trace_id": trace_id,
        "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in result.tool_calls],
    })

    st.rerun()
