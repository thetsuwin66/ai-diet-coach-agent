"""
Weekly meal plan generator for the AI Diet Coach.

Uses the recipe database to fetch a suitable pool, then asks GPT-4o-mini
to assign breakfast / lunch / dinner for each of the 7 days, respecting
the user's profile (busy days, cuisines, restrictions, weight goal).

Saves the plan to data/meal_plan.json.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from diet_agent import (
    filter_by_category,
    filter_by_max_cook_time,
    search_recipes,
)
from user_profile import load_profile, profile_to_context

load_dotenv()

PLAN_PATH = Path(__file__).parent / "data" / "meal_plan.json"
client = OpenAI()

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class Meal(BaseModel):
    name: str
    category: str
    cooking_time_minutes: int
    why: str


class DayPlan(BaseModel):
    day: str
    is_busy: bool
    breakfast: Meal
    lunch: Meal
    dinner: Meal


class WeeklyPlan(BaseModel):
    week_start: str
    days: list[DayPlan]


# ---------------------------------------------------------------------------
# Recipe pool fetching
# ---------------------------------------------------------------------------

def _fetch_recipe_pool(profile: dict) -> list[dict]:
    """Gather a diverse pool of ~40 recipes suited to this user's profile."""
    pool: dict[str, dict] = {}

    def add(recipes):
        for r in recipes:
            pool[r["name"]] = r

    cuisines = profile.get("preferred_cuisines", [])
    restrictions = profile.get("dietary_restrictions", [])
    busy_days = profile.get("busy_days", [])

    # General healthy recipes
    add(search_recipes("healthy low calorie dinner"))
    add(search_recipes("high protein meal"))
    add(search_recipes("light lunch"))
    add(search_recipes("quick breakfast"))

    # Cuisine-specific
    for cuisine in cuisines[:3]:
        add(search_recipes(cuisine))

    # Quick recipes for busy days
    if busy_days:
        add(filter_by_max_cook_time(20))

    # Category-based variety
    for cat in ["Chicken", "Seafood", "Vegetarian"]:
        add(filter_by_category(cat))

    # Filter out restricted ingredients
    filtered = []
    for recipe in pool.values():
        ingredients_text = " ".join(recipe.get("ingredients", [])).lower()
        skip = False
        for restriction in restrictions:
            keyword = restriction.lower().replace("no ", "").replace("intolerant", "").strip()
            if keyword and keyword in ingredients_text:
                skip = True
                break
        if not skip:
            filtered.append(recipe)

    return filtered[:50]


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

PLANNER_SYSTEM = """
You are a diet coach building a personalized 7-day meal plan.
You will receive a list of available recipes and the user's profile.
Assign exactly 3 meals per day (breakfast, lunch, dinner) from the recipe list.

Rules:
- Only use recipes from the provided list. Never invent recipes.
- No recipe should appear more than twice across the entire week.
- For busy days: all meals must have cooking_time_minutes <= 20.
- Respect all dietary restrictions -- skip any recipe that violates them.
- Prefer the user's preferred cuisines but ensure variety across the week.
- For weight loss: prefer lean proteins and low-calorie options.
- The "why" field: one short sentence explaining why this meal fits the user's goals.
- cooking_time_minutes must be an integer taken directly from the recipe data.
- week_start must be the Monday of the coming week in YYYY-MM-DD format.
""".strip()


def generate_weekly_plan(profile: dict | None = None) -> dict:
    if profile is None:
        profile = load_profile() or {}

    recipe_pool = _fetch_recipe_pool(profile)
    profile_context = profile_to_context(profile)
    busy_days = set(profile.get("busy_days", []))

    # Build recipe list for the prompt
    recipe_lines = []
    for r in recipe_pool:
        recipe_lines.append(
            f"- {r['name']} | category: {r.get('category', '?')} | "
            f"time: {r.get('cooking_time_minutes', '?')} min | "
            f"area: {r.get('area', '?')}"
        )
    recipe_text = "\n".join(recipe_lines)

    # Next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)

    busy_note = f"Busy days this week: {', '.join(busy_days)}" if busy_days else "No busy days."

    user_prompt = f"""
{profile_context}

{busy_note}

Week starts: {next_monday} (Monday)

Available recipes:
{recipe_text}

Build the 7-day meal plan.
""".strip()

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        max_tokens=4096,
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        response_format=WeeklyPlan,
    )

    plan = response.choices[0].message.parsed
    plan_dict = plan.model_dump()
    plan_dict["generated_at"] = str(date.today())

    save_meal_plan(plan_dict)
    return plan_dict


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_meal_plan(plan: dict) -> None:
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PLAN_PATH, "w") as f:
        json.dump(plan, f, indent=2)


def load_meal_plan() -> dict | None:
    if not PLAN_PATH.exists():
        return None
    with open(PLAN_PATH) as f:
        return json.load(f)
