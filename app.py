import os
import time
import uuid

import streamlit as st
from dotenv import load_dotenv

from datetime import date

from calorie_calculator import calculate_daily_target
from chat_memory import load_memory_context, save_session_memory
from diet_agent import run_agent
from meal_planner import generate_weekly_plan, load_meal_plan
from monitoring import load_all_traces, save_trace, update_feedback
from shopping_list import generate_shopping_list
from tracking import (
    STATUS_EATEN, STATUS_SKIPPED,
    get_meal_log_for_date, get_weight_logs, get_weekly_adherence,
    get_latest_weight, is_on_track, log_meal, log_weight,
    get_skip_patterns,
)
from user_profile import (
    ACTIVITY_LEVELS,
    CUISINE_OPTIONS,
    DAYS_OF_WEEK,
    PROFILE_PATH,
    create_profile,
    is_onboarding_complete,
    load_profile,
    profile_exists,
    profile_to_context,
    update_profile,
    verify_password,
)

load_dotenv()

# On Streamlit Cloud, secrets are exposed via st.secrets -- push them into env
# so all modules that use os.getenv() pick them up automatically.
for _key in ("OPENAI_API_KEY", "USDA_API_KEY", "GOOGLE_MAPS_API_KEY"):
    if _key not in os.environ:
        try:
            os.environ[_key] = st.secrets[_key]
        except (KeyError, FileNotFoundError):
            pass

st.set_page_config(page_title="AI Diet Coach", page_icon="🥗", layout="wide")

st.markdown("""
<style>
/* ── Global ── */
[data-testid="stAppViewContainer"] { font-family: 'Inter', sans-serif; }

/* ── Auth pages: center narrow card ── */
.auth-card {
    max-width: 440px;
    margin: 60px auto 0;
    padding: 2.5rem 2rem;
    border-radius: 16px;
    background: #1a1a2e;
    border: 1px solid #2d2d4e;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.auth-logo { font-size: 3rem; text-align: center; margin-bottom: 0.25rem; }
.auth-title {
    text-align: center; font-size: 1.8rem; font-weight: 700;
    background: linear-gradient(135deg, #4ade80, #22d3ee);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.25rem;
}
.auth-sub { text-align: center; color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }

/* ── Sidebar ── */
[data-testid="stSidebar"] { background: #0f172a; border-right: 1px solid #1e293b; }
.sidebar-logo { font-size: 1.5rem; font-weight: 700;
    background: linear-gradient(135deg, #4ade80, #22d3ee);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.sidebar-username { color: #94a3b8; font-size: 0.8rem; margin-top: -4px; }
.goal-card {
    background: linear-gradient(135deg, #1e3a5f, #0f2027);
    border-radius: 12px; padding: 14px 16px; margin: 12px 0;
    border: 1px solid #2d4a6f;
}
.goal-label { color: #94a3b8; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }
.goal-value { color: #e2e8f0; font-size: 1.4rem; font-weight: 700; line-height: 1.2; }
.goal-sub { color: #64748b; font-size: 0.75rem; margin-top: 4px; }
.progress-label { color: #94a3b8; font-size: 0.75rem; margin-bottom: 4px; }

/* ── Meal Plan cards ── */
.meal-card {
    background: #1e293b;
    border-radius: 12px;
    padding: 16px;
    border: 1px solid #334155;
    height: 100%;
    transition: border-color 0.2s;
}
.meal-card:hover { border-color: #4ade80; }
.meal-badge {
    display: inline-block; font-size: 0.7rem; font-weight: 600;
    padding: 2px 10px; border-radius: 20px; margin-bottom: 8px;
    text-transform: uppercase; letter-spacing: 0.06em;
}
.badge-breakfast { background: #fef3c7; color: #92400e; }
.badge-lunch     { background: #d1fae5; color: #065f46; }
.badge-dinner    { background: #ede9fe; color: #4c1d95; }
.meal-name { font-size: 0.95rem; font-weight: 600; color: #f1f5f9; margin-bottom: 4px; }
.meal-meta { color: #64748b; font-size: 0.78rem; margin-bottom: 6px; }
.meal-why  { color: #94a3b8; font-size: 0.8rem; line-height: 1.4; }
.meal-macros {
    margin-top: 10px; padding-top: 10px; border-top: 1px solid #334155;
    color: #4ade80; font-size: 0.75rem; font-weight: 600;
}
.dining-out {
    background: linear-gradient(135deg, #1e3a5f, #172554);
    border: 1px solid #3b82f6; border-radius: 10px;
    padding: 14px; text-align: center;
}
.dining-out-icon { font-size: 1.8rem; }
.dining-out-label { color: #93c5fd; font-weight: 600; margin-top: 4px; font-size: 0.9rem; }
.dining-out-why   { color: #64748b; font-size: 0.78rem; margin-top: 4px; }

/* ── Day expander header ── */
.day-header { font-size: 1.05rem; font-weight: 600; color: #f1f5f9; }
.busy-tag {
    display: inline-block; background: #7c3aed22; color: #a78bfa;
    font-size: 0.7rem; font-weight: 600; padding: 1px 8px;
    border-radius: 20px; margin-left: 8px; border: 1px solid #7c3aed44;
}

/* ── Nutrition totals bar ── */
.nutrition-bar {
    display: flex; gap: 12px; margin-top: 14px; padding: 12px 16px;
    background: #0f172a; border-radius: 10px; border: 1px solid #1e293b;
    flex-wrap: wrap;
}
.nutr-item { flex: 1; min-width: 60px; text-align: center; }
.nutr-value { font-size: 1rem; font-weight: 700; color: #4ade80; }
.nutr-label { font-size: 0.68rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }

/* ── Chat ── */
.chat-welcome {
    text-align: center; padding: 60px 20px 20px;
    color: #475569;
}
.chat-welcome-icon { font-size: 3rem; }
.chat-welcome-title { font-size: 1.2rem; font-weight: 600; color: #94a3b8; margin-top: 12px; }
.chat-welcome-sub { font-size: 0.85rem; color: #475569; margin-top: 6px; }

/* ── Misc ── */
[data-testid="stMetric"] { background: #1e293b; border-radius: 10px; padding: 10px 14px; }
</style>
""", unsafe_allow_html=True)

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
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div class="auth-card">
            <div class="auth-logo">🥗</div>
            <div class="auth-title">AI Diet Coach</div>
            <div class="auth-sub">Your personal weight-loss companion powered by AI</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        with st.form("register_form"):
            username = st.text_input("Username", placeholder="Choose a username")
            password = st.text_input("Password", type="password", placeholder="At least 6 characters")
            confirm  = st.text_input("Confirm password", type="password", placeholder="Repeat your password")
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
    import os
    profile = load_profile()
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(f"""
        <div class="auth-card">
            <div class="auth-logo">🥗</div>
            <div class="auth-title">Welcome back!</div>
            <div class="auth-sub">Account: <strong>{profile.get('username') if profile else ''}</strong></div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Your username")
            password = st.text_input("Password", type="password", placeholder="Your password")
            submitted = st.form_submit_button("Log in", use_container_width=True, type="primary")

        if submitted:
            if (
                profile
                and profile.get("username") == username
                and verify_password(password, profile["password_hash"], profile["password_salt"])
            ):
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Incorrect username or password.")

        st.markdown("")
        st.caption("Forgot your password or want to start fresh?")
        if st.button("Reset account", use_container_width=True):
            try:
                os.remove(PROFILE_PATH)
            except FileNotFoundError:
                pass
            st.rerun()


# ---------------------------------------------------------------------------
# Onboarding wizard
# ---------------------------------------------------------------------------

def show_onboarding():
    st.title("Let's set up your profile")
    st.caption("This helps the coach personalise every recommendation for you.")

    profile = load_profile() or {}

    with st.form("onboarding_form"):
        st.subheader("Your body stats")
        col1, col2, col3 = st.columns(3)
        current_weight = col1.number_input(
            "Current weight (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("current_weight_kg") or 70.0), step=0.5,
        )
        target_weight = col2.number_input(
            "Target weight (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("target_weight_kg") or 65.0), step=0.5,
        )
        height_cm = col3.number_input(
            "Height (cm)", min_value=100, max_value=250,
            value=int(profile.get("height_cm") or 165), step=1,
        )
        col4, col5 = st.columns(2)
        age = col4.number_input(
            "Age", min_value=10, max_value=100,
            value=int(profile.get("age") or 25), step=1,
        )
        gender = col5.selectbox(
            "Gender", ["Female", "Male"],
            index=0 if profile.get("gender", "Female") == "Female" else 1,
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
        calorie_data = {}
        if height_cm and age and activity:
            calorie_data = calculate_daily_target(
                weight_kg=current_weight, target_weight_kg=target_weight,
                height_cm=float(height_cm), age=int(age),
                gender=gender, activity_level=activity,
            )
        update_profile({
            "current_weight_kg": current_weight,
            "target_weight_kg": target_weight,
            "height_cm": height_cm,
            "age": age,
            "gender": gender,
            "deadline": str(deadline) if deadline else None,
            "dietary_restrictions": restrictions,
            "preferred_cuisines": cuisines,
            "busy_days": busy_days,
            "location": location,
            "activity_level": activity,
            "daily_calorie_target": calorie_data.get("daily_target"),
            "daily_protein_g": calorie_data.get("protein_g"),
            "daily_carbs_g": calorie_data.get("carbs_g"),
            "daily_fat_g": calorie_data.get("fat_g"),
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
        current_weight = st.sidebar.number_input(
            "Current weight (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("current_weight_kg") or 70.0), step=0.5,
        )
        target_weight = st.sidebar.number_input(
            "Target weight (kg)", min_value=30.0, max_value=300.0,
            value=float(profile.get("target_weight_kg") or 65.0), step=0.5,
        )
        restrictions_input = st.sidebar.text_input(
            "Restrictions / allergies",
            value=", ".join(profile.get("dietary_restrictions", [])),
        )
        cuisines = st.sidebar.multiselect(
            "Preferred cuisines",
            options=CUISINE_OPTIONS,
            default=profile.get("preferred_cuisines", []),
        )
        busy_days = st.sidebar.multiselect(
            "Busy days",
            options=DAYS_OF_WEEK,
            default=profile.get("busy_days", []),
        )
        location = st.sidebar.text_input("City / area", value=profile.get("location", ""))
        save = st.form_submit_button("Save changes", use_container_width=True, type="primary")
        cancel = st.form_submit_button("Cancel", use_container_width=True)

    if save:
        restrictions = [r.strip() for r in restrictions_input.split(",") if r.strip()]
        update_profile({
            "current_weight_kg": current_weight,
            "target_weight_kg": target_weight,
            "deadline": profile.get("deadline"),
            "dietary_restrictions": restrictions,
            "preferred_cuisines": cuisines,
            "busy_days": busy_days,
            "location": location,
            "onboarding_complete": True,
        })
        st.session_state.show_profile_editor = False
        st.rerun()

    if cancel:
        st.session_state.show_profile_editor = False
        st.rerun()


# ---------------------------------------------------------------------------
# Recipe detail renderer (used in Meal Plan tab)
# ---------------------------------------------------------------------------

def render_recipe_details(name: str):
    from diet_agent import get_recipe_details
    recipe = get_recipe_details(name)
    if "error" in recipe:
        st.caption(f"Recipe details not found for '{name}'.")
        return

    ingredients = recipe.get("ingredients", "")
    if isinstance(ingredients, list):
        ingredients = ", ".join(ingredients)

    instructions = recipe.get("instructions", "")
    area = recipe.get("area", "")
    cook_time = recipe.get("cooking_time_minutes")

    if area or cook_time:
        meta = " · ".join(filter(None, [area, f"{cook_time} min" if cook_time else None]))
        st.caption(meta)

    if ingredients:
        st.markdown("**Ingredients**")
        for ing in ingredients.split(","):
            ing = ing.strip()
            if ing:
                st.markdown(f"- {ing}")

    if instructions:
        st.markdown("**Instructions**")
        steps = [s.strip() for s in instructions.replace("\r\n", "\n").split("\n") if s.strip()]
        for i, step in enumerate(steps, 1):
            st.markdown(f"{i}. {step}")


# ---------------------------------------------------------------------------
# Routing  (if/else avoids stale sidebar from st.stop)
# ---------------------------------------------------------------------------

if not st.session_state.logged_in:
    if not profile_exists():
        show_registration()
    else:
        show_login()

elif not is_onboarding_complete():
    show_onboarding()

else:
    profile = load_profile() or {}
    profile_context = profile_to_context(profile)

    # -----------------------------------------------------------------------
    # Sidebar
    # -----------------------------------------------------------------------
    with st.sidebar:
        st.markdown(f"""
        <div style="padding: 8px 0 4px;">
            <div class="sidebar-logo">🥗 AI Diet Coach</div>
            <div class="sidebar-username">Logged in as {profile.get('username', '')}</div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        cw = profile.get("current_weight_kg")
        tw = profile.get("target_weight_kg")
        dl = profile.get("deadline")
        if cw and tw:
            lost = round(cw - tw, 1)
            progress = max(0.0, min(1.0, 1 - (cw - tw) / cw)) if cw > tw else 1.0
            cal_target = profile.get("daily_calorie_target")
            cal_line = f"<div class='goal-sub'>🔥 {cal_target} kcal/day target</div>" if cal_target else ""
            st.markdown(f"""
            <div class="goal-card">
                <div class="goal-label">Weight Goal</div>
                <div class="goal-value">{cw} kg <span style="color:#64748b;font-size:1rem;">→</span> {tw} kg</div>
                <div class="goal-sub">{"Lose " + str(lost) + " kg" if lost > 0 else "Goal reached!"}{(" · by " + dl) if dl else ""}</div>
                {cal_line}
            </div>
            """, unsafe_allow_html=True)
            st.progress(progress, text=f"{round(progress*100)}% to goal")

        # Latest weight + check-in
        latest_w = get_latest_weight()
        if latest_w:
            st.caption(f"Last logged weight: **{latest_w} kg**")

        with st.expander("Log today's weight", expanded=False):
            new_w = st.number_input("Weight (kg)", min_value=30.0, max_value=300.0,
                                    value=float(latest_w or cw or 70.0), step=0.1,
                                    key="sidebar_weight_input")
            if st.button("Save weight", use_container_width=True, key="save_weight_btn"):
                log_weight(new_w)
                update_profile({"current_weight_kg": new_w})
                st.success(f"Logged {new_w} kg!")
                st.rerun()

        # Weekly adherence
        adh = get_weekly_adherence()
        if adh["logged"] > 0:
            color = "#4ade80" if adh["adherence_pct"] >= 70 else "#f87171"
            st.markdown(f"""
            <div style="background:#1e293b;border-radius:10px;padding:10px 14px;margin:8px 0;">
                <div style="color:#94a3b8;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;">This week</div>
                <div style="color:{color};font-size:1.3rem;font-weight:700;">{adh['adherence_pct']}% on track</div>
                <div style="color:#64748b;font-size:0.75rem;">{adh['eaten']} eaten · {adh['skipped']} skipped · {adh['not_logged']} not logged</div>
            </div>
            """, unsafe_allow_html=True)

        cuisines = profile.get("preferred_cuisines", [])
        if cuisines:
            st.caption(f"**Cuisines:** {', '.join(cuisines)}")
        restrictions = profile.get("dietary_restrictions", [])
        if restrictions:
            st.caption(f"**Restrictions:** {', '.join(restrictions)}")

        st.divider()

        col_edit, col_new = st.columns(2)
        if col_edit.button("Edit profile", use_container_width=True):
            st.session_state.show_profile_editor = not st.session_state.show_profile_editor
            st.rerun()
        if col_new.button("New chat", use_container_width=True):
            save_session_memory(st.session_state.messages, st.session_state.session_id)
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.pending_feedback = {}
            st.rerun()

        if st.button("Log out", use_container_width=True):
            save_session_memory(st.session_state.messages, st.session_state.session_id)
            st.session_state.logged_in = False
            st.session_state.messages = []
            st.rerun()

        st.divider()

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

    # -----------------------------------------------------------------------
    # Main tabs
    # -----------------------------------------------------------------------
    st.title("AI Diet Coach")
    tab_chat, tab_plan, tab_progress = st.tabs(["Chat", "Weekly Meal Plan", "Progress"])

    with tab_chat:
        if not st.session_state.messages:
            st.markdown(f"""
            <div class="chat-welcome">
                <div class="chat-welcome-icon">💬</div>
                <div class="chat-welcome-title">Hi {profile.get('username','there')}! How can I help you today?</div>
                <div class="chat-welcome-sub">
                    Try: "What should I eat for dinner?" · "Show me quick Korean recipes" · "Plan my week"
                </div>
            </div>
            """, unsafe_allow_html=True)

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
                    memory_context = load_memory_context()
                    full_context = "\n\n".join(filter(None, [profile_context, memory_context]))
                    result = run_agent(user_input, user_profile_context=full_context)
                    duration = time.time() - t0

                if result.tool_calls:
                    with tool_log.expander("Tools called", expanded=False):
                        for tc in result.tool_calls:
                            st.code(f"{tc.name}({tc.arguments})", language="python")

                answer_ph.markdown(result.answer)

                # Set notice if replan was called so Meal Plan tab highlights the change
                if any(tc.name == "replan" for tc in result.tool_calls):
                    day_replanned = next(
                        (tc.arguments.get("day", "") for tc in result.tool_calls if tc.name == "replan"), ""
                    )
                    st.session_state["replan_notice"] = f"Meal plan updated! {day_replanned} has been replanned."

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

    with tab_plan:
        st.subheader("Your Weekly Meal Plan")

        if st.button("Generate new plan", type="primary"):
            with st.spinner("Building your personalised meal plan..."):
                try:
                    generate_weekly_plan(profile)
                    st.success("Meal plan ready!")
                except Exception as e:
                    st.error(f"Failed to generate plan: {e}")

        plan = load_meal_plan()

        if not plan:
            st.info("No meal plan yet. Click **Generate new plan** to create your personalised 7-day plan.")
        else:
            st.caption(f"Week of {plan.get('week_start', '?')}  |  Last updated {plan.get('generated_at', '?')}")
            if st.session_state.get("replan_notice"):
                st.success(st.session_state.pop("replan_notice"))

            # Shopping list
            with st.expander("🛒 Shopping List", expanded=False):
                if st.button("Generate shopping list", key="gen_shopping"):
                    with st.spinner("Building your shopping list..."):
                        try:
                            st.session_state["shopping_list"] = generate_shopping_list(plan)
                        except Exception as e:
                            st.error(f"Could not generate list: {e}")

                shop = st.session_state.get("shopping_list", {})
                if shop:
                    cols = st.columns(2)
                    items = list(shop.items())
                    for i, (cat, ingredients) in enumerate(items):
                        with cols[i % 2]:
                            st.markdown(f"**{cat}**")
                            for ing in ingredients:
                                st.checkbox(ing, key=f"shop_{cat}_{ing}")
                else:
                    st.caption("Click 'Generate shopping list' to create a list from your meal plan.")

            st.divider()

            busy_days_set = set(profile.get("busy_days", []))

            today_name = date.today().strftime("%A")
            today_log = get_meal_log_for_date()

            for day_plan in plan.get("days", []):
                day = day_plan["day"]
                is_busy = day_plan.get("is_busy", day in busy_days_set)
                is_today = (day == today_name)
                busy_label = " 🔴 Busy" if is_busy else ""
                today_label = " 📅 Today" if is_today else ""
                expander_label = f"{day}{today_label}{busy_label}"

                with st.expander(expander_label, expanded=is_today):
                    b = day_plan["breakfast"]
                    l = day_plan["lunch"]
                    d = day_plan["dinner"]
                    # For today, load actual logs; for other days use date-matched log
                    if is_today:
                        day_log = today_log
                    else:
                        day_log = {}

                    def meal_card_html(badge_class, badge_label, meal):
                        if meal.get("name") == "Dining Out":
                            return f"""
                            <div class="meal-card">
                                <span class="meal-badge {badge_class}">{badge_label}</span>
                                <div class="dining-out">
                                    <div class="dining-out-icon">🍽️</div>
                                    <div class="dining-out-label">Dining Out</div>
                                    <div class="dining-out-why">{meal.get('why','')}</div>
                                </div>
                                <div class="meal-macros">~{meal.get('estimated_calories',0)} kcal</div>
                            </div>"""
                        time_str = f"{meal.get('cooking_time_minutes','?')} min"
                        macros = ""
                        if meal.get("estimated_calories"):
                            macros = f"{meal['estimated_calories']} kcal &nbsp;·&nbsp; P {meal['estimated_protein_g']}g &nbsp;·&nbsp; C {meal['estimated_carbs_g']}g &nbsp;·&nbsp; F {meal['estimated_fat_g']}g"
                        return f"""
                        <div class="meal-card">
                            <span class="meal-badge {badge_class}">{badge_label}</span>
                            <div class="meal-name">{meal.get('name','')}</div>
                            <div class="meal-meta">{meal.get('category','')} &nbsp;·&nbsp; {time_str}</div>
                            <div class="meal-why">{meal.get('why','')}</div>
                            {f'<div class="meal-macros">{macros}</div>' if macros else ''}
                        </div>"""

                    col1, col2, col3 = st.columns(3)

                    def render_meal_col(col, meal, meal_type, badge_class, badge_label, day, day_log):
                        with col:
                            log_entry = day_log.get(meal_type, {})
                            status = log_entry.get("status", "")

                            # Status border overlay on card
                            card_style = ""
                            if status == STATUS_EATEN:
                                card_style = "border-color:#4ade80!important;"
                            elif status == STATUS_SKIPPED:
                                card_style = "border-color:#f87171!important;opacity:0.7;"

                            html = meal_card_html(badge_class, badge_label, meal)
                            if card_style:
                                html = html.replace('class="meal-card"', f'class="meal-card" style="{card_style}"')
                            st.markdown(html, unsafe_allow_html=True)

                            # Tracking buttons (only for today, for non-dining-out meals)
                            if is_today and meal.get("name") != "Dining Out":
                                t1, t2 = st.columns(2)
                                eaten_type = t1.button(
                                    "✓ Ate this" if status != STATUS_EATEN else "✓ Eaten",
                                    key=f"eat_{day}_{meal_type}",
                                    use_container_width=True,
                                    type="primary" if status != STATUS_EATEN else "secondary",
                                )
                                skip_type = t2.button(
                                    "✗ Skipped" if status != STATUS_SKIPPED else "✗ Skipped",
                                    key=f"skip_{day}_{meal_type}",
                                    use_container_width=True,
                                )
                                if eaten_type:
                                    log_meal(day, meal_type, meal["name"], STATUS_EATEN)
                                    st.rerun()
                                if skip_type:
                                    log_meal(day, meal_type, meal["name"], STATUS_SKIPPED)
                                    st.rerun()

                            if status == STATUS_EATEN:
                                st.caption("✅ Eaten")
                            elif status == STATUS_SKIPPED:
                                st.caption("❌ Skipped")

                            if meal.get("name") != "Dining Out":
                                with st.expander("View recipe", expanded=False):
                                    render_recipe_details(meal["name"])

                    render_meal_col(col1, b, "breakfast", "badge-breakfast", "Breakfast", day, day_log)
                    render_meal_col(col2, l, "lunch",     "badge-lunch",     "Lunch",     day, day_log)
                    render_meal_col(col3, d, "dinner",    "badge-dinner",    "Dinner",    day, day_log)

                    if day_plan.get("total_calories"):
                        st.markdown(f"""
                        <div class="nutrition-bar">
                            <div class="nutr-item"><div class="nutr-value">{day_plan['total_calories']}</div><div class="nutr-label">kcal</div></div>
                            <div class="nutr-item"><div class="nutr-value">{day_plan['total_protein_g']}g</div><div class="nutr-label">Protein</div></div>
                            <div class="nutr-item"><div class="nutr-value">{day_plan['total_carbs_g']}g</div><div class="nutr-label">Carbs</div></div>
                            <div class="nutr-item"><div class="nutr-value">{day_plan['total_fat_g']}g</div><div class="nutr-label">Fat</div></div>
                        </div>
                        """, unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Tab: Progress
    # -----------------------------------------------------------------------
    with tab_progress:
        st.subheader("Your Progress")

        track_status = is_on_track(profile)
        adh = track_status["adherence"]

        # On-track banner
        if track_status["on_track"]:
            st.success("You're on track! Keep it up.")
        else:
            for issue in track_status["issues"]:
                st.warning(f"Off track: {issue}")
            if st.button("Adjust my meal plan", type="primary"):
                with st.spinner("Adjusting your plan..."):
                    try:
                        patterns = get_skip_patterns()
                        skips = patterns["skips_by_meal_type"]
                        most_skipped = max(skips, key=skips.get)
                        from meal_planner import replan_day
                        today_day = date.today().strftime("%A")
                        replan_day(today_day, f"user is off track, simplify {most_skipped}", profile)
                        st.session_state["replan_notice"] = f"Plan adjusted based on your tracking data."
                        st.success("Plan adjusted! Check the Weekly Meal Plan tab.")
                    except Exception as e:
                        st.error(f"Could not adjust: {e}")

        st.divider()

        # Weight trend
        st.markdown("#### Weight Trend")
        weight_logs = get_weight_logs()
        if len(weight_logs) < 2:
            st.info("Log your weight at least twice to see your trend. Use the sidebar to log today's weight.")
        else:
            import pandas as pd
            wdf = pd.DataFrame(weight_logs).set_index("date")
            tw = profile.get("target_weight_kg")
            if tw:
                wdf["target"] = tw
            st.line_chart(wdf, height=220)
            first_w = weight_logs[0]["weight_kg"]
            latest_w = weight_logs[-1]["weight_kg"]
            delta = round(latest_w - first_w, 1)
            arrow = "down" if delta < 0 else "up"
            c1, c2, c3 = st.columns(3)
            c1.metric("Starting weight", f"{first_w} kg")
            c2.metric("Current weight", f"{latest_w} kg", delta=f"{delta} kg",
                      delta_color="inverse")
            c3.metric("Target weight", f"{tw} kg" if tw else "Not set")

        st.divider()

        # Weekly adherence
        st.markdown("#### This Week's Meals")
        if adh["logged"] == 0:
            st.info("No meals logged yet this week. Mark meals as eaten or skipped in the Weekly Meal Plan tab.")
        else:
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Eaten",      adh["eaten"])
            a2.metric("Skipped",    adh["skipped"])
            a3.metric("Not logged", adh["not_logged"])
            a4.metric("On track",   f"{adh['adherence_pct']}%")
            st.progress(adh["adherence_pct"] / 100,
                        text=f"{adh['adherence_pct']}% of logged meals eaten")

        # Skip patterns
        patterns = get_skip_patterns()
        skips = patterns["skips_by_meal_type"]
        if any(v > 0 for v in skips.values()):
            st.divider()
            st.markdown("#### What You Often Skip")
            for meal_type, count in skips.items():
                eaten = patterns["eaten_by_meal_type"].get(meal_type, 0)
                total = count + eaten
                if total > 0:
                    pct = round(eaten / total * 100)
                    bar_color = "#4ade80" if pct >= 60 else "#f87171"
                    st.markdown(f"""
                    <div style="margin-bottom:10px;">
                        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                            <span style="color:#e2e8f0;font-size:0.85rem;text-transform:capitalize;">{meal_type}</span>
                            <span style="color:#94a3b8;font-size:0.8rem;">{eaten}/{total} eaten</span>
                        </div>
                        <div style="background:#1e293b;border-radius:6px;height:8px;overflow:hidden;">
                            <div style="background:{bar_color};width:{pct}%;height:100%;border-radius:6px;"></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
