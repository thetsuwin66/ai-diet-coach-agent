import time
import uuid

import streamlit as st
from dotenv import load_dotenv

from diet_agent import run_agent
from monitoring import load_all_traces, print_summary, save_trace, update_feedback

load_dotenv()

st.set_page_config(page_title="AI Diet Coach", page_icon="🥗", layout="wide")

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []   # {role, content, trace_id, tool_calls}
if "pending_feedback" not in st.session_state:
    st.session_state.pending_feedback = {}   # trace_id -> submitted bool

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("AI Diet Coach")
    st.caption("Powered by 201 recipes from TheMealDB")
    st.divider()

    if st.button("New conversation", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.pending_feedback = {}
        st.rerun()

    st.divider()
    st.subheader("Session stats")
    traces = load_all_traces()
    session_traces = [t for t in traces if t["session_id"] == st.session_state.session_id]
    st.metric("Turns this session", len(session_traces))
    if session_traces:
        total_tokens = sum(t["input_tokens"] + t["output_tokens"] for t in session_traces)
        st.metric("Tokens used", f"{total_tokens:,}")
        avg_s = sum(t["duration_seconds"] for t in session_traces) / len(session_traces)
        st.metric("Avg response time", f"{avg_s:.1f}s")

    st.divider()
    st.subheader("All-time stats")
    st.metric("Total sessions logged", len(traces))
    if traces:
        rated = [t for t in traces if t["feedback"] is not None]
        ups = sum(1 for t in rated if t["feedback"] == 1)
        downs = sum(1 for t in rated if t["feedback"] == -1)
        st.metric("Feedback", f"{ups} thumbs up / {downs} thumbs down")

# ---------------------------------------------------------------------------
# Render existing messages
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

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
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
            result = run_agent(user_input)
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
