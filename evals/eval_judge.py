"""
LLM judge for the AI Diet Coach agent.

Usage:
    # Run judge on labeled data and print alignment metrics
    python eval_judge.py

    # Run with a specific prompt version
    python eval_judge.py --version v2

The judge uses structured output with a reasoning field and a label field.
Two prompt versions are tracked to show iteration/improvement.
"""

import argparse
import csv
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

RESULTS_PATH = Path(__file__).parent / "eval_results.json"
LABELS_PATH = Path(__file__).parent / "labels.csv"
JUDGE_RESULTS_PATH = Path(__file__).parent / "judge_results.json"

client = OpenAI()


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class JudgeOutput(BaseModel):
    reasoning: str
    label: str  # "good" or "bad"


# ---------------------------------------------------------------------------
# Judge prompt versions
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_V1 = """
You are an expert judge evaluating the performance of an AI diet coach chatbot.
The agent has access to a database of 201 recipes and four tools:
- search_recipes(query): full-text search
- filter_by_max_cook_time(max_minutes): time filter
- filter_by_category(category): category filter
- get_recipe_details(name): fetch full recipe

Given the user's question, the tool calls made, and the agent's final answer,
decide whether the response is GOOD or BAD.

A response is GOOD when:
- It directly addresses the user's question
- It uses the appropriate tool(s) from the database
- Recipes mentioned come from the database (not invented)
- Cooking times and ingredients are included when relevant
- For out-of-scope questions, the agent politely declines and redirects

A response is BAD when:
- The agent invents recipes or nutritional data not in the database (hallucination)
- The agent recommends clearly inappropriate items (e.g. Fettuccine Alfredo for
  low-calorie goals, burgers for getting lean)
- The agent fails to call any tool when a tool was clearly needed
- The answer is incomplete or misses what the user actually asked for
- The agent makes up a recipe when it couldn't find one in the database

Respond with your step-by-step reasoning and then your label ("good" or "bad").
""".strip()

# v2 adds explicit callouts for the hallucination and wrong-recommendation
# patterns discovered during labeling
JUDGE_SYSTEM_V2 = """
You are an expert judge evaluating an AI diet coach chatbot.
The agent has a recipe database (201 meals) and four tools:
- search_recipes(query)
- filter_by_max_cook_time(max_minutes)
- filter_by_category(category)
- get_recipe_details(name)

Rate the response GOOD or BAD using these rules:

GOOD if ALL of:
1. The question is answered (or correctly refused if out of scope)
2. At least one tool was called when the question needs a recipe from the DB
3. No factual inventions: recipes, macros, nutritional data are from the DB, not made up
4. Recommendations fit the user's goal (e.g. no high-calorie dish for a low-cal request)
5. Cooking times and recipe names are grounded in the tool output, not hallucinated

BAD if ANY of:
- Agent invents a recipe or nutritional info when the DB search returned nothing
  (hallucination: saying "a typical recipe is..." when DB had no result is BAD)
- Agent recommends a high-calorie or indulgent dish (Fettuccine Alfredo, burger,
  fried food) in response to a low-calorie, lean, or diet-focused question
- No tools called but recipe information was clearly needed
- Response is vague or incomplete when a specific answer was possible
- Agent guesses a recipe name with no context ("that beef thing") instead of asking

Respond with step-by-step reasoning, then label ("good" or "bad").
""".strip()

# v3: targets the exact failure patterns found in v1/v2 disagreements:
#   - v1 over-penalized correct time-constrained answers for including burgers
#   - v2 applied calorie rules to ALL queries, not just diet-focused ones
#   - v2 also produced "beef" as label on one response (context bleed)
JUDGE_SYSTEM_V3 = """
You are an expert judge for an AI diet coach chatbot. The agent has 201 recipes
and four tools: search_recipes, filter_by_max_cook_time, filter_by_category,
get_recipe_details.

Rate each response strictly as "good" or "bad" (no other values).

STEP 1 - Determine question intent:
  A) Diet-focused: question mentions weight loss, low-calorie, lean, slimming, healthy, won't make me fat
  B) Time-focused: question only mentions time constraints with no diet context
  C) Recipe lookup: user wants full recipe / cooking steps
  D) Out-of-scope: question is unrelated to recipes or cooking

STEP 2 - Apply the matching rules:

For type A (diet-focused):
  GOOD: tools called, recipes from DB, no obviously high-calorie item (e.g. Fettuccine
        Alfredo, deep-fried food) presented as a healthy/diet option
  BAD: hallucinated recipe/nutrition data, high-calorie item promoted as diet food,
       no tool called, vague unhelpful answer

For type B (time-focused):
  GOOD: filter_by_max_cook_time called with a sensible limit; recipes listed fit the
        time budget; recipe names come from the DB
  BAD: wrong tool used, time limit ignored, hallucinated recipes

For type C (recipe lookup):
  GOOD: get_recipe_details called; actual ingredients and steps provided from DB
  BAD: recipe not found but agent invents a generic recipe from training memory
       instead of being honest about the gap; incomplete (no steps given)

For type D (out-of-scope):
  GOOD: agent politely declines and optionally redirects to what it can do
  BAD: agent claims capabilities it doesn't have, or gives dangerous health advice

Edge cases:
  - "tell me how to cook that beef thing" with no prior context: BAD (wrong_scope -
    agent should ask which recipe the user means)
  - A recipe that seems calorie-dense appearing in a neutral/time-only response: GOOD
    (don't penalize for calorie content unless the user asked for diet-friendly food)

Output your step-by-step reasoning, then your label. Label MUST be exactly "good" or "bad".
""".strip()

JUDGE_SYSTEM_V4 = """
You are an expert judge for an AI diet coach chatbot. The agent has 256 recipes
(Thai, Korean, Filipino, Japanese, Chinese, Vietnamese, Indonesian, and Western)
and these tools: search_recipes, filter_by_max_cook_time, filter_by_category,
get_recipe_details, generate_meal_plan, swap_meal, replan, get_nutrition_info,
find_nearby_restaurants.

Rate GOOD or BAD using these rules. Label MUST be exactly "good" or "bad".

── ALWAYS GOOD (no further checks needed) ──────────────────────────────────────
1. Out-of-scope refusal: user asks something outside diet/recipes (weather, wine,
   gym workouts, supplements, restaurant bookings, ordering food) and agent politely
   declines and/or redirects. No tool call needed. GOOD.
2. Impossible request: zero-calorie recipes, negative cook time, curing diseases --
   agent explains why it can't help. GOOD.
3. No results honestly reported: agent searched the DB and found nothing for the
   requested cuisine/dish (e.g. "no Korean recipes", "omelette not in database")
   and says so clearly. GOOD. The database has limited coverage -- this is expected.
4. Safety refusal: agent refuses raw chicken, dangerous advice. GOOD.

── CLASSIFY INTENT then apply rules ────────────────────────────────────────────
A) Diet-focused (mentions weight loss, low-calorie, lean, slimming, healthy):
   GOOD: tools called, recipes from DB, no high-calorie item promoted as diet food
   BAD: hallucinated recipes, high-calorie item as diet food, no tool + no refusal

B) Time-focused (mentions minutes, quick, fast -- no diet context):
   GOOD: filter_by_max_cook_time used OR honest "no results"; time budget respected
   BAD: time limit ignored, hallucinated recipes

C) Recipe lookup (wants full recipe / how to make X):
   GOOD: get_recipe_details called, OR "not in DB" honestly stated
   BAD: recipe not found but agent invents one from memory

D) Meal plan / swap (adjust plan, swap a meal, replan a day):
   GOOD: replan or swap_meal called, OR plan updated and user informed
   BAD: agent claims it changed the plan without calling any tool

E) Restaurant / nearby food:
   GOOD: find_nearby_restaurants called, OR honest explanation if API fails
   BAD: agent ignores the question entirely with no useful response

── NEVER penalise for ──────────────────────────────────────────────────────────
- Not calling a tool when a polite decline or "not found" is the right answer
- Including a calorie-dense dish in a neutral/time-only response
- Limited DB coverage (no Filipino, Korean, omelette, etc.)

Output reasoning then label ("good" or "bad").
""".strip()

JUDGE_PROMPTS = {
    "v1": JUDGE_SYSTEM_V1,
    "v2": JUDGE_SYSTEM_V2,
    "v3": JUDGE_SYSTEM_V3,
    "v4": JUDGE_SYSTEM_V4,
}

JUDGE_USER_TEMPLATE = """
User question: {question}

Tool calls made (in order):
{tool_calls}

Agent's final answer:
{answer}
""".strip()


# ---------------------------------------------------------------------------
# Judge call
# ---------------------------------------------------------------------------

def judge_response(question: str, tool_calls: list, answer: str, version: str = "v2") -> JudgeOutput:
    tool_calls_text = "\n".join(
        f"{i + 1}. {tc['name']}({json.dumps(tc['arguments'])})"
        for i, tc in enumerate(tool_calls)
    ) or "(none)"

    user_prompt = JUDGE_USER_TEMPLATE.format(
        question=question,
        tool_calls=tool_calls_text,
        answer=answer,
    )

    # Truncate very long answers to avoid token limit errors
    truncated_prompt = user_prompt
    if len(answer) > 1500:
        truncated_answer = answer[:1500] + "... [truncated]"
        truncated_prompt = JUDGE_USER_TEMPLATE.format(
            question=question,
            tool_calls=tool_calls_text,
            answer=truncated_answer,
        )

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        max_tokens=2048,
        messages=[
            {"role": "system", "content": JUDGE_PROMPTS[version]},
            {"role": "user", "content": truncated_prompt},
        ],
        response_format=JudgeOutput,
    )
    out = response.choices[0].message.parsed
    # Validate label - guard against context bleed producing non-label text
    if out is None or out.label not in ("good", "bad"):
        raw = response.choices[0].message.content or ""
        out = JudgeOutput(
            reasoning=raw[:500],
            label="bad" if "bad" in raw.lower() else "good",
        )
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(human_labels: list[str], judge_labels: list[str]) -> dict:
    assert len(human_labels) == len(judge_labels)
    n = len(human_labels)

    tp = sum(1 for h, j in zip(human_labels, judge_labels) if h == "bad" and j == "bad")
    tn = sum(1 for h, j in zip(human_labels, judge_labels) if h == "good" and j == "good")
    fp = sum(1 for h, j in zip(human_labels, judge_labels) if h == "good" and j == "bad")
    fn = sum(1 for h, j in zip(human_labels, judge_labels) if h == "bad" and j == "good")

    accuracy = (tp + tn) / n if n else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    return {
        "accuracy": round(accuracy, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "total": n,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_results() -> dict[str, dict]:
    with open(RESULTS_PATH) as f:
        results = json.load(f)
    return {r["question"]: r for r in results}


def load_human_labels() -> dict[str, dict]:
    with open(LABELS_PATH, newline="", encoding="utf-8") as f:
        return {row["question"]: row for row in csv.DictReader(f)}


def run_judge(version: str = "v2") -> list[dict]:
    results_by_q = load_results()
    human_labels = load_human_labels()

    judge_results = []
    print(f"\nRunning judge ({version}) on {len(human_labels)} labeled examples...")
    print("-" * 60)

    for i, (question, label_row) in enumerate(human_labels.items()):
        result = results_by_q.get(question)
        if not result:
            print(f"  [SKIP] Not found in results: {question[:50]}")
            continue

        human_label = label_row["label"]
        try:
            judge_out = judge_response(
                question=question,
                tool_calls=result.get("tool_calls", []),
                answer=result.get("answer", ""),
                version=version,
            )
        except Exception as exc:
            print(f"  [SKIP] Error judging '{question[:50]}': {exc}")
            continue

        match = judge_out.label == human_label
        symbol = "OK" if match else "!!"

        print(
            f"[{symbol}] [{i + 1:02d}] human={human_label:<4} judge={judge_out.label:<4} | "
            f"{question[:55]}"
        )
        if not match:
            print(f"       Reasoning: {judge_out.reasoning[:120]}...")

        judge_results.append({
            "question": question,
            "human_label": human_label,
            "judge_label": judge_out.label,
            "reasoning": judge_out.reasoning,
            "failure_category": label_row.get("failure_category", ""),
            "match": match,
            "version": version,
        })

    return judge_results


def print_metrics(judge_results: list[dict], version: str) -> None:
    human_labels = [r["human_label"] for r in judge_results]
    judge_labels = [r["judge_label"] for r in judge_results]
    metrics = compute_metrics(human_labels, judge_labels)

    print(f"\n{'='*60}")
    print(f"Judge alignment metrics  [{version}]")
    print(f"{'='*60}")
    print(f"  Accuracy  : {metrics['accuracy']:.1%}  ({metrics['tp'] + metrics['tn']}/{metrics['total']} correct)")
    print(f"  Precision : {metrics['precision']:.1%}  (when judge says bad, how often right?)")
    print(f"  Recall    : {metrics['recall']:.1%}  (of all bad responses, how many caught?)")
    print(f"  F1        : {metrics['f1']:.1%}")
    print(f"\n  Confusion matrix:")
    print(f"    TP (both bad)  : {metrics['tp']}")
    print(f"    TN (both good) : {metrics['tn']}")
    print(f"    FP (judge bad, human good): {metrics['fp']}")
    print(f"    FN (judge good, human bad): {metrics['fn']}")

    disagreements = [r for r in judge_results if not r["match"]]
    if disagreements:
        print(f"\n  Disagreements ({len(disagreements)}):")
        for d in disagreements:
            print(f"    human={d['human_label']} judge={d['judge_label']} | {d['question'][:60]}")
            print(f"      Reasoning: {d['reasoning'][:100]}...")

    return metrics


def compare_versions() -> None:
    """Run all three judge versions and print a side-by-side comparison."""
    print("\n" + "="*60)
    print("COMPARING JUDGE VERSIONS: v1 vs v2 vs v3")
    print("="*60)

    all_results = {}
    all_metrics = {}
    for ver in ["v1", "v2", "v3", "v4"]:
        print(f"\n{'='*60}")
        r = run_judge(ver)
        m = compute_metrics(
            [x["human_label"] for x in r],
            [x["judge_label"] for x in r],
        )
        print_metrics(r, ver)
        all_results[ver] = r
        all_metrics[ver] = m

    print("\n" + "="*60)
    print("IMPROVEMENT SUMMARY  (v1 -> v2 -> v3)")
    print("="*60)
    for metric in ["accuracy", "precision", "recall", "f1"]:
        v1 = all_metrics["v1"][metric]
        v2 = all_metrics["v2"][metric]
        v3 = all_metrics["v3"][metric]
        d12 = v2 - v1
        d23 = v3 - v2
        print(
            f"  {metric:<10}: v1={v1:.1%}  "
            f"v2={v2:.1%} ({'+' if d12 >= 0 else ''}{d12:.1%})  "
            f"v3={v3:.1%} ({'+' if d23 >= 0 else ''}{d23:.1%})"
        )

    # Find a fixed disagreement (v1 wrong, v3 right)
    disagreements_v1 = {r["question"]: r for r in all_results["v1"] if not r["match"]}
    fixed_by_v3 = [
        r for r in all_results["v3"]
        if r["match"] and r["question"] in disagreements_v1
    ]
    if fixed_by_v3:
        ex = fixed_by_v3[0]
        v1_ex = disagreements_v1[ex["question"]]
        print(f"\nExample disagreement fixed by v3:")
        print(f"  Question   : {ex['question']}")
        print(f"  Human label: {ex['human_label']}")
        print(f"  v1 judge   : {v1_ex['judge_label']}  (WRONG)")
        print(f"  v3 judge   : {ex['judge_label']}  (CORRECT)")
        print(f"  v3 Reasoning: {ex['reasoning'][:250]}...")

    # Save combined results
    combined = {ver: {"results": all_results[ver], "metrics": all_metrics[ver]} for ver in ["v1", "v2", "v3"]}
    with open(JUDGE_RESULTS_PATH, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"\nFull results saved to {JUDGE_RESULTS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        choices=["v1", "v2", "v3", "v4", "compare"],
        default="compare",
        help="Judge prompt version to run (default: compare both)",
    )
    args = parser.parse_args()

    if args.version == "compare":
        compare_versions()
    else:
        results = run_judge(args.version)
        print_metrics(results, args.version)
        with open(JUDGE_RESULTS_PATH, "w") as f:
            json.dump({args.version: {"results": results}}, f, indent=2)
