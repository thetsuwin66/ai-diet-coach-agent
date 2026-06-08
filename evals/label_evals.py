"""
Streamlit labeling tool for AI Diet Coach evaluation results.

Usage:
    streamlit run label_evals.py

Shows each agent response with its question and tool calls.
Lets you label good/bad and choose a failure category.
Saves labels to labels.csv so work is never lost.
"""

import csv
import json
from pathlib import Path

import streamlit as st

RESULTS_PATH = Path(__file__).parent / "eval_results.json"
LABELS_PATH = Path(__file__).parent / "labels.csv"

FAILURE_CATEGORIES = [
    "(none - good response)",
    "hallucination",
    "wrong_scope",
    "incomplete",
    "wrong_tool",
    "off_topic",
    "unsafe_advice",
    "other",
]


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_results() -> list[dict]:
    with open(RESULTS_PATH) as f:
        return json.load(f)


def load_labels() -> dict[str, dict]:
    """Returns a dict keyed by question."""
    if not LABELS_PATH.exists():
        return {}
    with open(LABELS_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["question"]: row for row in reader}


def save_label(question: str, label: str, failure_category: str, notes: str) -> None:
    labels = load_labels()
    labels[question] = {
        "question": question,
        "label": label,
        "failure_category": failure_category,
        "notes": notes,
    }
    with open(LABELS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["question", "label", "failure_category", "notes"])
        writer.writeheader()
        writer.writerows(labels.values())


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Diet Coach Labeling Tool", layout="wide")
st.title("AI Diet Coach - Response Labeling Tool")

results = load_results()
labels = load_labels()

# Sidebar stats
with st.sidebar:
    st.header("Progress")
    total = len(results)
    labeled = len(labels)
    good = sum(1 for l in labels.values() if l["label"] == "good")
    bad = sum(1 for l in labels.values() if l["label"] == "bad")
    st.metric("Total", total)
    st.metric("Labeled", labeled)
    st.metric("Good", good)
    st.metric("Bad", bad)
    st.progress(labeled / total if total else 0, text=f"{labeled}/{total} labeled")

    st.divider()
    st.subheader("Filter")
    filter_status = st.selectbox("Show", ["All", "Unlabeled", "Good", "Bad"])
    filter_category = st.selectbox(
        "Category",
        ["All"] + sorted({r["category"] for r in results}),
    )
    filter_type = st.selectbox(
        "Type",
        ["All"] + sorted({r["type"] for r in results}),
    )

    st.divider()
    if st.button("Download labels.csv", use_container_width=True):
        if LABELS_PATH.exists():
            st.download_button(
                "Click to download",
                LABELS_PATH.read_bytes(),
                file_name="labels.csv",
                mime="text/csv",
            )

# ---------------------------------------------------------------------------
# Filter results
# ---------------------------------------------------------------------------

filtered = results
if filter_status == "Unlabeled":
    filtered = [r for r in filtered if r["question"] not in labels]
elif filter_status == "Good":
    filtered = [r for r in filtered if labels.get(r["question"], {}).get("label") == "good"]
elif filter_status == "Bad":
    filtered = [r for r in filtered if labels.get(r["question"], {}).get("label") == "bad"]

if filter_category != "All":
    filtered = [r for r in filtered if r["category"] == filter_category]
if filter_type != "All":
    filtered = [r for r in filtered if r["type"] == filter_type]

if not filtered:
    st.info("No results match the current filter.")
    st.stop()

# ---------------------------------------------------------------------------
# Navigator
# ---------------------------------------------------------------------------

if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0

idx = st.session_state.current_idx
idx = min(idx, len(filtered) - 1)
record = filtered[idx]
existing_label = labels.get(record["question"], {})

col_nav_l, col_counter, col_nav_r = st.columns([1, 4, 1])
with col_nav_l:
    if st.button("Prev", use_container_width=True) and idx > 0:
        st.session_state.current_idx -= 1
        st.rerun()
with col_counter:
    st.markdown(f"**Record {idx + 1} of {len(filtered)}**")
with col_nav_r:
    if st.button("Next", use_container_width=True) and idx < len(filtered) - 1:
        st.session_state.current_idx += 1
        st.rerun()

# Jump to specific record
jump = st.number_input("Jump to record", min_value=1, max_value=len(filtered), value=idx + 1, step=1)
if jump - 1 != idx:
    st.session_state.current_idx = jump - 1
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Record display
# ---------------------------------------------------------------------------

status_badge = ""
if existing_label:
    color = "green" if existing_label["label"] == "good" else "red"
    status_badge = f" :{'green' if color == 'green' else 'red'}[{existing_label['label'].upper()}]"

st.subheader(f"Question{status_badge}")
st.markdown(f"> {record['question']}")

col_meta1, col_meta2, col_meta3 = st.columns(3)
col_meta1.caption(f"Category: **{record['category']}**")
col_meta2.caption(f"Type: **{record['type']}**")
col_meta3.caption(f"Duration: **{record['duration_seconds']}s**")

if record.get("error"):
    st.error(f"Agent error: {record['error']}")

# Tool calls
if record.get("tool_calls"):
    with st.expander("Tools called", expanded=False):
        for tc in record["tool_calls"]:
            st.code(f"{tc['name']}({json.dumps(tc['arguments'])})", language="python")
else:
    st.caption("No tool calls made.")

# Answer
st.subheader("Agent Response")
if record.get("answer"):
    st.markdown(record["answer"])
else:
    st.warning("(empty response)")

st.divider()

# ---------------------------------------------------------------------------
# Labeling form
# ---------------------------------------------------------------------------

st.subheader("Label this response")

with st.form(key=f"label_form_{record['question'][:40]}"):
    current_label = existing_label.get("label", "")
    label_choice = st.radio(
        "Is this response good or bad?",
        options=["good", "bad"],
        index=0 if current_label != "bad" else 1,
        horizontal=True,
    )

    current_fc = existing_label.get("failure_category", FAILURE_CATEGORIES[0])
    fc_index = FAILURE_CATEGORIES.index(current_fc) if current_fc in FAILURE_CATEGORIES else 0
    failure_cat = st.selectbox(
        "Failure category (choose if bad)",
        FAILURE_CATEGORIES,
        index=fc_index,
    )

    notes = st.text_area(
        "Notes (optional)",
        value=existing_label.get("notes", ""),
        height=80,
    )

    submitted = st.form_submit_button("Save label", use_container_width=True, type="primary")
    if submitted:
        fc_to_save = failure_cat if label_choice == "bad" else "(none - good response)"
        save_label(record["question"], label_choice, fc_to_save, notes)
        st.success(f"Saved: {label_choice.upper()}")
        # Auto-advance to next unlabeled
        if idx < len(filtered) - 1:
            st.session_state.current_idx += 1
        st.rerun()
