import json
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from minsearch import Index

load_dotenv()

DATA_PATH = Path(__file__).parent / "data" / "recipes.json"


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class AgentResult:
    answer: str
    tool_calls: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


def _load_documents():
    with open(DATA_PATH) as f:
        return json.load(f)


def _build_index(documents):
    idx = Index(
        text_fields=["name", "category", "area", "ingredients", "instructions"],
        keyword_fields=["category", "area"],
    )
    idx.fit(documents)
    return idx


documents = _load_documents()
index = _build_index(documents)
openai_client = OpenAI()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def search_recipes(query: str) -> list:
    return index.search(query, num_results=5)


def filter_by_max_cook_time(max_minutes: int) -> list:
    results = [
        doc for doc in documents
        if doc.get("cooking_time_minutes", 9999) <= max_minutes
    ]
    return results[:10]


def filter_by_category(category: str) -> list:
    results = [
        doc for doc in documents
        if doc.get("category", "").lower() == category.lower()
    ]
    return results[:10]


def get_recipe_details(name: str) -> dict:
    name_lower = name.lower()
    for doc in documents:
        if name_lower in doc["name"].lower():
            return doc
    return {"error": f"No recipe found matching '{name}'"}


TOOL_REGISTRY = {
    "search_recipes": search_recipes,
    "filter_by_max_cook_time": filter_by_max_cook_time,
    "filter_by_category": filter_by_category,
    "get_recipe_details": get_recipe_details,
}


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "name": "search_recipes",
        "description": (
            "Search the recipe database for meals that match a query. "
            "Use this when the user describes a goal, ingredient, cuisine type, "
            "or any free-text request like 'high protein' or 'low calorie pasta'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query",
                }
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "filter_by_max_cook_time",
        "description": (
            "Return recipes that can be cooked within a given number of minutes. "
            "Use this when the user says they have limited time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_minutes": {
                    "type": "integer",
                    "description": "Maximum cooking time in minutes",
                }
            },
            "required": ["max_minutes"],
        },
    },
    {
        "type": "function",
        "name": "filter_by_category",
        "description": (
            "Return all recipes in a specific food category such as 'Chicken', "
            "'Beef', 'Seafood', 'Vegetarian', 'Pasta', etc. "
            "Use this when the user specifies a dietary preference or protein type."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Food category, e.g. 'Chicken', 'Seafood', 'Vegetarian'",
                }
            },
            "required": ["category"],
        },
    },
    {
        "type": "function",
        "name": "get_recipe_details",
        "description": (
            "Retrieve the full ingredients list and step-by-step instructions for a "
            "specific recipe by name. Use this when the user asks 'how do I make X' "
            "or after finding a recipe the user wants to know more about."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The recipe name or partial name to look up",
                }
            },
            "required": ["name"],
        },
    },
]


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

INSTRUCTIONS = """
You are an AI diet coach helping users reach their weight-loss goals through
personalized meal recommendations.

You have access to a database of 201 recipes. Use your tools to answer every
question - never invent recipes that are not in the database.

When to call each tool:
- search_recipes: when the user describes a goal, ingredient, cuisine, or mood
  (e.g. 'high protein', 'quick dinner', 'Asian food', 'something with chicken').
  Always start here for general queries.
- filter_by_max_cook_time: when the user mentions a time limit
  (e.g. 'I only have 15 minutes', 'quick', 'under 20 min').
- filter_by_category: when the user specifies a protein or food type
  (e.g. 'only chicken', 'vegetarian options', 'seafood dishes').
- get_recipe_details: when the user wants the full recipe for a specific dish
  (e.g. 'how do I make the stir-fry?', 'give me the full recipe').

How to respond:
- For each recommended recipe include: name, category, cooking time, key
  ingredients, and one sentence explaining why it fits the user's goal.
- If the user is on a weight-loss programme, prefer lower-calorie options and
  lean proteins. Mention calorie-related reasoning when relevant.
- If no suitable recipes are found, say so honestly and give a general
  dietary tip instead.
- Be concise and supportive - you are a coach, not a cookbook index.
""".strip()


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def _make_call(tool_call):
    arguments = json.loads(tool_call.arguments)
    name = tool_call.name
    fn = TOOL_REGISTRY.get(name)
    result = fn(**arguments) if fn else {"error": f"Unknown tool '{name}'"}
    return (
        {
            "type": "function_call_output",
            "call_id": tool_call.call_id,
            "output": json.dumps(result),
        },
        ToolCall(name=name, arguments=arguments),
    )


def run_agent(user_question: str, model: str = "gpt-4o-mini") -> AgentResult:
    message_history = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": user_question},
    ]

    all_tool_calls: list[ToolCall] = []
    final_answer = None
    total_input_tokens = 0
    total_output_tokens = 0

    while True:
        response = openai_client.responses.create(
            model=model,
            input=message_history,
            tools=TOOLS,
        )

        if response.usage:
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

        message_history.extend(response.output)
        has_tool_calls = False

        for item in response.output:
            if item.type == "function_call":
                output_item, tc = _make_call(item)
                message_history.append(output_item)
                all_tool_calls.append(tc)
                has_tool_calls = True
            elif item.type == "message":
                final_answer = item.content[0].text

        if not has_tool_calls:
            break

    return AgentResult(
        answer=final_answer or "",
        tool_calls=all_tool_calls,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )
