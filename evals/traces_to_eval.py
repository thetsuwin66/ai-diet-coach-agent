"""
Convert agent monitoring traces into evaluation scenarios.

Reads all traces from data/traces/, filters for meaningful interactions,
and appends them to evals/eval_results.json so they can be labeled with
label_evals.py and judged with eval_judge.py.

Usage:
    python evals/traces_to_eval.py               # append new traces
    python evals/traces_to_eval.py --min-tokens 50   # only longer responses
    python evals/traces_to_eval.py --dry-run     # preview without saving

This closes the monitoring → evaluation feedback loop:
  user chats → traces saved → traces exported → labeled → judged → prompt improved
"""

import argparse
import json
from pathlib import Path

TRACES_DIR  = Path(__file__).parent.parent / "data" / "traces"
RESULTS_PATH = Path(__file__).parent / "eval_results.json"


def load_traces() -> list[dict]:
    traces = []
    for p in sorted(TRACES_DIR.glob("*.json")):
        with open(p) as f:
            traces.append(json.load(f))
    return traces


def load_existing_results() -> list[dict]:
    if not RESULTS_PATH.exists():
        return []
    with open(RESULTS_PATH) as f:
        return json.load(f)


def traces_to_scenarios(
    traces: list[dict],
    existing: list[dict],
    min_output_tokens: int = 30,
) -> list[dict]:
    existing_questions = {r["question"] for r in existing}
    new_scenarios = []
    next_id = max((r.get("id", 0) for r in existing), default=0) + 1

    for trace in traces:
        question = trace.get("question", "").strip()
        answer   = trace.get("answer", "").strip()

        # Skip empty, duplicates, or very short responses
        if not question or not answer:
            continue
        if question in existing_questions:
            continue
        if trace.get("output_tokens", 0) < min_output_tokens:
            continue

        new_scenarios.append({
            "id": next_id,
            "question": question,
            "category": "from_traces",
            "type": "real_user",
            "answer": answer,
            "tool_calls": trace.get("tool_calls", []),
            "input_tokens": trace.get("input_tokens", 0),
            "output_tokens": trace.get("output_tokens", 0),
            "duration_seconds": trace.get("duration_seconds", 0),
            "error": None,
            "source_trace_id": trace.get("trace_id", ""),
        })
        existing_questions.add(question)
        next_id += 1

    return new_scenarios


def main():
    parser = argparse.ArgumentParser(description="Export traces as eval scenarios")
    parser.add_argument("--min-tokens", type=int, default=30,
                        help="Minimum output tokens to include (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview new scenarios without saving")
    args = parser.parse_args()

    traces   = load_traces()
    existing = load_existing_results()
    new      = traces_to_scenarios(traces, existing, args.min_tokens)

    print(f"Traces found     : {len(traces)}")
    print(f"Already in evals : {len(existing)}")
    print(f"New scenarios    : {len(new)}")

    if not new:
        print("Nothing new to add.")
        return

    print("\nNew scenarios preview:")
    for s in new[:5]:
        print(f"  [{s['id']}] {s['question'][:70]}")
    if len(new) > 5:
        print(f"  ... and {len(new) - 5} more")

    if args.dry_run:
        print("\nDry run -- nothing saved.")
        return

    combined = existing + new
    with open(RESULTS_PATH, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"\nSaved {len(new)} new scenarios to {RESULTS_PATH}")
    print("Next steps:")
    print("  1. Label them:  make label   (or: uv run streamlit run evals/label_evals.py)")
    print("  2. Run judge:   make judge   (or: uv run python evals/eval_judge.py)")


if __name__ == "__main__":
    main()
