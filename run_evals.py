"""
Batch evaluation runner for the AI Diet Coach agent.

Reads scenarios from scenarios.csv, runs each through the agent,
and writes all results to eval_results.json.
"""

import csv
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from diet_agent import run_agent  # noqa: E402 - needs load_dotenv first

SCENARIOS_PATH = Path(__file__).parent / "scenarios.csv"
RESULTS_PATH = Path(__file__).parent / "eval_results.json"


def load_scenarios() -> list[dict]:
    with open(SCENARIOS_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_batch(scenarios: list[dict], resume: bool = True) -> list[dict]:
    existing: dict[str, dict] = {}
    if resume and RESULTS_PATH.exists():
        with open(RESULTS_PATH) as f:
            for r in json.load(f):
                existing[r["question"]] = r
        print(f"Resuming: {len(existing)} results already saved.")

    results = list(existing.values())

    for i, s in enumerate(scenarios):
        question = s["question"]
        if question in existing:
            continue

        print(f"[{i + 1}/{len(scenarios)}] {s['category']} / {s['type']}: {question[:60]}...")
        t0 = time.time()
        try:
            result = run_agent(question)
            duration = round(time.time() - t0, 2)
            entry = {
                "id": i + 1,
                "question": question,
                "category": s["category"],
                "type": s["type"],
                "answer": result.answer,
                "tool_calls": [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in result.tool_calls
                ],
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "duration_seconds": duration,
                "error": None,
            }
        except Exception as exc:
            duration = round(time.time() - t0, 2)
            print(f"  ERROR: {exc}")
            entry = {
                "id": i + 1,
                "question": question,
                "category": s["category"],
                "type": s["type"],
                "answer": "",
                "tool_calls": [],
                "input_tokens": 0,
                "output_tokens": 0,
                "duration_seconds": duration,
                "error": str(exc),
            }

        results.append(entry)
        with open(RESULTS_PATH, "w") as f:
            json.dump(results, f, indent=2)

    return results


def print_summary(results: list[dict]) -> None:
    total = len(results)
    errors = sum(1 for r in results if r["error"])
    categories = {}
    for r in results:
        categories[r["category"]] = categories.get(r["category"], 0) + 1

    print(f"\n{'='*50}")
    print(f"Batch run complete: {total} scenarios ({errors} errors)")
    print("Breakdown by category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")
    print(f"Results saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    resume = "--fresh" not in sys.argv
    scenarios = load_scenarios()
    print(f"Loaded {len(scenarios)} scenarios from {SCENARIOS_PATH}")
    results = run_batch(scenarios, resume=resume)
    print_summary(results)
