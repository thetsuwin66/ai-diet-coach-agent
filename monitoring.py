"""
Lightweight file-based monitoring for the AI Diet Coach agent.

Each agent run is saved as a JSON file in data/traces/.
The Streamlit app can later update a trace to add user feedback.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from diet_agent import AgentResult

TRACES_DIR = Path(__file__).parent / "data" / "traces"
TRACES_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Trace:
    trace_id: str
    session_id: str
    timestamp: str
    question: str
    tool_calls: list          # [{"name": ..., "arguments": {...}}]
    answer: str
    input_tokens: int
    output_tokens: int
    duration_seconds: float
    feedback: int | None = None   # 1 = thumbs up, -1 = thumbs down


def save_trace(
    question: str,
    result: AgentResult,
    duration_seconds: float,
    session_id: str,
) -> str:
    trace_id = str(uuid.uuid4())
    trace = Trace(
        trace_id=trace_id,
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        question=question,
        tool_calls=[
            {"name": tc.name, "arguments": tc.arguments}
            for tc in result.tool_calls
        ],
        answer=result.answer,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        duration_seconds=round(duration_seconds, 2),
        feedback=None,
    )

    path = TRACES_DIR / f"{trace_id}.json"
    with open(path, "w") as f:
        json.dump(asdict(trace), f, indent=2)

    return trace_id


def update_feedback(trace_id: str, feedback: int) -> None:
    path = TRACES_DIR / f"{trace_id}.json"
    if not path.exists():
        return
    with open(path) as f:
        data = json.load(f)
    data["feedback"] = feedback
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_all_traces() -> list[dict]:
    traces = []
    for p in sorted(TRACES_DIR.glob("*.json")):
        with open(p) as f:
            traces.append(json.load(f))
    return traces


def print_summary() -> None:
    traces = load_all_traces()
    if not traces:
        print("No traces recorded yet.")
        return

    total = len(traces)
    total_in = sum(t["input_tokens"] for t in traces)
    total_out = sum(t["output_tokens"] for t in traces)
    avg_duration = sum(t["duration_seconds"] for t in traces) / total
    with_feedback = [t for t in traces if t["feedback"] is not None]
    thumbs_up = sum(1 for t in with_feedback if t["feedback"] == 1)
    thumbs_down = sum(1 for t in with_feedback if t["feedback"] == -1)

    print(f"Total sessions : {total}")
    print(f"Avg duration   : {avg_duration:.1f}s")
    print(f"Input tokens   : {total_in:,} total  ({total_in // total:,} avg)")
    print(f"Output tokens  : {total_out:,} total  ({total_out // total:,} avg)")
    print(f"Feedback       : {thumbs_up} up / {thumbs_down} down "
          f"({len(with_feedback)}/{total} rated)")
