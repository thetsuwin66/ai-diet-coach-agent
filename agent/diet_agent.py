import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import logfire
from dotenv import load_dotenv
from openai import OpenAI
from minsearch import Index

load_dotenv()

DATA_PATH = Path(__file__).parent.parent / "data" / "recipes.json"
ASIAN_DATA_PATH = Path(__file__).parent.parent / "data" / "asian_recipes.json"

# Configure Logfire -- only activates if LOGFIRE_TOKEN is set
if os.getenv("LOGFIRE_TOKEN"):
    logfire.configure(token=os.getenv("LOGFIRE_TOKEN"), service_name="ai-diet-coach")
    logfire.instrument_openai()


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
        western = json.load(f)
    with open(ASIAN_DATA_PATH) as f:
        asian = json.load(f)
    # minsearch requires text fields to be strings -- join list ingredients
    for doc in asian:
        if isinstance(doc.get("ingredients"), list):
            doc["ingredients"] = ", ".join(doc["ingredients"])
    return western + asian


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


def generate_meal_plan() -> dict:
    from .meal_planner import generate_weekly_plan
    from .user_profile import load_profile
    profile = load_profile() or {}
    plan = generate_weekly_plan(profile)
    summary = {"week_start": plan.get("week_start"), "days": []}
    for day in plan.get("days", []):
        summary["days"].append({
            "day": day["day"],
            "breakfast": day["breakfast"]["name"],
            "lunch": day["lunch"]["name"],
            "dinner": day["dinner"]["name"],
        })
    return summary


def get_nutrition_info(food_name: str) -> dict:
    from .nutrition import get_nutrition_info as _get
    return _get(food_name)


def find_nearby_restaurants(dietary_preference: str = "") -> list:
    from .restaurants import find_nearby_restaurants as _find
    from .user_profile import load_profile
    profile = load_profile() or {}
    location = profile.get("location", "")
    return _find(location=location, dietary_preference=dietary_preference)


def replan(day: str, reason: str) -> dict:
    from .meal_planner import replan_day
    from .user_profile import load_profile
    profile = load_profile() or {}
    return replan_day(day=day, reason=reason, profile=profile)


def swap_meal(day: str, meal_type: str, meal_name: str) -> dict:
    from .meal_planner import swap_meal as _swap
    return _swap(day=day, meal_type=meal_type, meal_name=meal_name)


TOOL_REGISTRY = {
    "search_recipes": search_recipes,
    "filter_by_max_cook_time": filter_by_max_cook_time,
    "filter_by_category": filter_by_category,
    "get_recipe_details": get_recipe_details,
    "generate_meal_plan": generate_meal_plan,
    "get_nutrition_info": get_nutrition_info,
    "find_nearby_restaurants": find_nearby_restaurants,
    "replan": replan,
    "swap_meal": swap_meal,
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
    {
        "type": "function",
        "name": "generate_meal_plan",
        "description": (
            "Generate a personalized 7-day weekly meal plan (breakfast, lunch, dinner) "
            "based on the user's profile, dietary restrictions, preferred cuisines, and "
            "busy days. Use this when the user asks to create, generate, or see their "
            "weekly meal plan."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_nutrition_info",
        "description": (
            "Look up nutrition information (calories, protein, fat, carbs, fiber) for a "
            "food item or dish. Use this when the user asks about macros, calories, or "
            "nutritional content of a specific food."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "food_name": {
                    "type": "string",
                    "description": "The food or dish name to look up, e.g. 'chicken breast', 'brown rice'",
                }
            },
            "required": ["food_name"],
        },
    },
    {
        "type": "function",
        "name": "find_nearby_restaurants",
        "description": (
            "Find healthy or diet-friendly restaurants near the user's location. "
            "Use this when the user asks for restaurant recommendations, eating out options, "
            "or says they don't have time to cook."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dietary_preference": {
                    "type": "string",
                    "description": (
                        "Type of restaurant to find, e.g. 'healthy', 'vegetarian', "
                        "'low calorie', 'salad'. Defaults to 'healthy' if not specified."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "swap_meal",
        "description": (
            "Instantly swap one specific meal (breakfast, lunch, or dinner) on a given day "
            "with a named dish. Use this when the user requests a specific food for a specific "
            "meal slot, e.g. 'I want omelette for Tuesday breakfast' or 'change my Monday lunch "
            "to pad thai'. This is faster than replan -- use it for single-meal dish requests."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Day of the week, e.g. 'Monday', 'Tuesday'",
                },
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner"],
                    "description": "Which meal to replace",
                },
                "meal_name": {
                    "type": "string",
                    "description": "The dish the user wants, e.g. 'omelette', 'pad thai', 'chicken salad'",
                },
            },
            "required": ["day", "meal_type", "meal_name"],
        },
    },
    {
        "type": "function",
        "name": "replan",
        "description": (
            "Re-generate all three meals for a specific day when the user's schedule changes. "
            "Use this for schedule-based changes like a dinner event, a very busy day, or a full "
            "day swap. For single specific dish requests, use swap_meal instead (it's faster)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Day of the week to replan, e.g. 'Monday', 'Friday'",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for replanning, e.g. 'dinner event', 'very busy day', 'eating out for lunch'",
                },
            },
            "required": ["day", "reason"],
        },
    },
]


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

BASE_INSTRUCTIONS = """
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
- generate_meal_plan: when the user asks to create or see their weekly meal plan
  (e.g. 'make me a meal plan', 'plan my week', 'what should I eat this week').
- get_nutrition_info: when the user asks about calories, macros, or nutritional
  content of a food (e.g. 'how many calories in chicken breast?', 'protein in salmon').
- find_nearby_restaurants: when the user wants to eat out or asks for restaurant
  suggestions near their location (e.g. 'where can I eat healthy near me?',
  'I don't have time to cook tonight').
- swap_meal: when the user wants a specific dish for a specific meal slot
  (e.g. 'I want omelette for Tuesday breakfast', 'change Monday lunch to pad thai').
  ALWAYS prefer this over replan for single-meal dish requests -- it is instant.
- replan: ONLY for schedule-based full-day changes like a dinner event, very busy day,
  or complete day overhaul. Not for specific dish requests.

How to respond:
- For each recommended recipe include: name, category, cooking time, key
  ingredients, and one sentence explaining why it fits the user's goal.
- If the user is on a weight-loss programme, prefer lower-calorie options and
  lean proteins. Mention calorie-related reasoning when relevant.
- Always personalise recommendations using the user profile below when available.
  Respect dietary restrictions, prefer their listed cuisines, and account for
  their busy days when suggesting cooking time.
- If no suitable recipes are found, say so honestly and give a general
  dietary tip instead.
- Be concise and supportive - you are a coach, not a cookbook index.
""".strip()


def build_instructions(user_profile_context: str = "") -> str:
    if user_profile_context:
        return f"{BASE_INSTRUCTIONS}\n\n{user_profile_context}"
    return BASE_INSTRUCTIONS


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def _make_call(tool_call):
    arguments = json.loads(tool_call.arguments)
    name = tool_call.name
    fn = TOOL_REGISTRY.get(name)
    with logfire.span("tool_call {tool_name}", tool_name=name, arguments=arguments):
        try:
            result = fn(**arguments) if fn else {"error": f"Unknown tool '{name}'"}
        except Exception as exc:
            result = {"error": f"Tool '{name}' failed: {exc}"}
            logfire.error("Tool failed: {error}", error=str(exc))
    return (
        {
            "type": "function_call_output",
            "call_id": tool_call.call_id,
            "output": json.dumps(result),
        },
        ToolCall(name=name, arguments=arguments),
    )


def run_agent(user_question: str, model: str = "gpt-4o-mini", user_profile_context: str = "") -> AgentResult:
    with logfire.span("agent_run", question=user_question[:120], model=model):
        message_history = [
            {"role": "system", "content": build_instructions(user_profile_context)},
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

        logfire.info(
            "agent_run complete",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            tool_calls_count=len(all_tool_calls),
        )

    return AgentResult(
        answer=final_answer or "",
        tool_calls=all_tool_calls,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )
