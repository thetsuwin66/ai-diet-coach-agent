"""
Persistent chat memory for the AI Diet Coach.

After each session, GPT summarizes what was learned about the user
(preferences, dislikes, goals, progress notes). The last 4 summaries
are injected into new sessions so the agent feels continuous.

Stored in data/chat_memory.json.
"""

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MEMORY_PATH = Path(__file__).parent.parent / "data" / "chat_memory.json"
MAX_MEMORIES = 4
client = OpenAI()

SUMMARIZER_SYSTEM = """
You are summarizing a conversation between a user and their AI diet coach.
Extract only what is personally relevant about the user: food preferences,
dislikes, goals mentioned, complaints, things they enjoyed, health notes,
or anything that would help a coach personalise future advice.

Be concise (3-5 bullet points max). Write in third person about the user.
Omit generic recipe descriptions -- focus on personal signals only.
If nothing relevant was said, output: "(no personal signals this session)"
""".strip()


def _load() -> dict:
    if not MEMORY_PATH.exists():
        return {"sessions": []}
    with open(MEMORY_PATH) as f:
        return json.load(f)


def _save(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def save_session_memory(messages: list[dict], session_id: str) -> None:
    """Summarize a completed session and save to memory store."""
    if not messages:
        return

    # Only summarize if there was meaningful back-and-forth
    user_turns = [m for m in messages if m.get("role") == "user"]
    if len(user_turns) < 2:
        return

    # Build conversation text for summarizer
    convo = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}"
        for m in messages
        if m.get("role") in ("user", "assistant")
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=256,
            messages=[
                {"role": "system", "content": SUMMARIZER_SYSTEM},
                {"role": "user", "content": convo},
            ],
        )
        summary = response.choices[0].message.content.strip()
    except Exception:
        return  # fail silently -- memory is a nice-to-have

    data = _load()
    data["sessions"].append({
        "session_id": session_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": summary,
    })
    # Keep only the most recent MAX_MEMORIES sessions
    data["sessions"] = data["sessions"][-MAX_MEMORIES:]
    _save(data)


def load_memory_context() -> str:
    """Return a formatted string of recent session summaries for the system prompt."""
    data = _load()
    sessions = data.get("sessions", [])
    if not sessions:
        return ""

    lines = ["Previous session notes (use to personalise your responses):"]
    for s in sessions[-MAX_MEMORIES:]:
        lines.append(f"\n[{s['date']}]\n{s['summary']}")

    return "\n".join(lines)


def clear_memory() -> None:
    _save({"sessions": []})
