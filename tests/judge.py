import json
from openai import OpenAI
from agent.diet_agent import AgentResult

openai_client = OpenAI()

JUDGE_SYSTEM = """
You are an expert judge evaluating the performance of an AI diet coach agent.
You will be given the agent's final answer, the list of tool calls it made,
and a set of criteria to evaluate.

For each criterion respond with whether it passed (true/false) and a short
explanation citing specific evidence from the output or tool calls.

Respond only with valid JSON in this exact shape:
{
  "criteria": [
    {"criterion": "<criterion text>", "passed": true, "judgement": "<explanation>"}
  ],
  "feedback": "<overall summary>"
}
""".strip()

JUDGE_USER_TEMPLATE = """
Evaluate the agent's performance based on the following criteria:
<CRITERIA>
{criteria}
</CRITERIA>

The agent's final answer:
<ANSWER>
{answer}
</ANSWER>

Tool calls made (in order):
<TOOL_CALLS>
{tool_calls}
</TOOL_CALLS>
""".strip()


def assert_criteria(result: AgentResult, criteria: list[str]) -> None:
    tool_calls_text = "\n".join(
        f"{i + 1}. {tc.name}({json.dumps(tc.arguments)})"
        for i, tc in enumerate(result.tool_calls)
    ) or "(none)"

    user_prompt = JUDGE_USER_TEMPLATE.format(
        criteria="\n".join(f"- {c}" for c in criteria),
        answer=result.answer,
        tool_calls=tool_calls_text,
    )

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )

    parsed = json.loads(response.choices[0].message.content)

    print("\n=== Judge feedback ===")
    print(parsed.get("feedback", ""))
    for item in parsed.get("criteria", []):
        status = "PASS" if item["passed"] else "FAIL"
        print(f"  [{status}] {item['criterion']}: {item['judgement']}")

    for item in parsed.get("criteria", []):
        assert item["passed"], (
            f"Criterion FAILED: {item['criterion']}\n"
            f"Judgement: {item['judgement']}"
        )
