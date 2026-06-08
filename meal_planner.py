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
from pydantic import BaseModel, Field

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
    estimated_calories: int = Field(default=0)
    estimated_protein_g: int = Field(default=0)
    estimated_carbs_g: int = Field(default=0)
    estimated_fat_g: int = Field(default=0)


class DayPlan(BaseModel):
    day: str
    is_busy: bool = Field(default=False)
    breakfast: Meal
    lunch: Meal
    dinner: Meal
    total_calories: int = Field(default=0)
    total_protein_g: int = Field(default=0)
    total_carbs_g: int = Field(default=0)
    total_fat_g: int = Field(default=0)


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
You will receive a list of available recipes, the user's profile, and their
history from last week (what they ate, skipped, and their weight trend).

Rules:
- Only use recipes from the provided list. Never invent recipes.
- No recipe should appear more than twice across the entire week.
- For busy days: all meals must have cooking_time_minutes <= 20.
- Respect all dietary restrictions -- skip any recipe that violates them.
- Prefer the user's preferred cuisines but ensure variety across the week.
- The "why" field: one short sentence explaining why this meal fits the user.

Using the history section:
- Do NOT repeat meals the user ate last week (give them variety).
- If a meal type (breakfast/lunch/dinner) was frequently skipped, assign
  simpler and quicker options for that slot this week.
- If weight is trending up or not changing, lower the daily calorie target
  by preferring lean proteins, salads, soups, and lighter dishes.
- If weight is trending down, maintain the current plan style.
- If last week's adherence was low overall, plan simpler meals across all days.

Nutrition estimates (per meal, realistic values):
- estimated_calories: approximate kcal for one serving
- estimated_protein_g: grams of protein
- estimated_carbs_g: grams of carbohydrates
- estimated_fat_g: grams of fat
- total_calories/protein/carbs/fat per day = sum of the three meals
Use realistic nutrition estimates based on typical serving sizes.
- week_start must be the Monday of the coming week in YYYY-MM-DD format.
""".strip()


def _build_tracking_context() -> str:
    """Build a plain-text summary of last week's tracking data for the planner."""
    try:
        from tracking import (
            get_meal_log_for_week, get_weight_logs, get_weekly_adherence,
            get_skip_patterns, STATUS_EATEN, STATUS_SKIPPED,
        )
        from datetime import timedelta

        # Last week's logs
        today = date.today()
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_week_logs = get_meal_log_for_week(last_monday)

        eaten_meals  = [m["meal_name"] for m in last_week_logs if m["status"] == STATUS_EATEN]
        skipped_meals = [m["meal_name"] for m in last_week_logs if m["status"] == STATUS_SKIPPED]

        adherence = get_weekly_adherence()
        patterns  = get_skip_patterns(num_weeks=2)
        skips     = patterns["skips_by_meal_type"]
        most_skipped = max(skips, key=skips.get) if any(skips.values()) else None

        # Weight trend
        weight_logs = get_weight_logs()
        weight_trend = "unknown"
        weight_note  = ""
        if len(weight_logs) >= 2:
            delta = weight_logs[-1]["weight_kg"] - weight_logs[0]["weight_kg"]
            if delta < -0.3:
                weight_trend = "decreasing"
                weight_note  = f"Lost {abs(round(delta,1))} kg so far -- keep it up."
            elif delta > 0.3:
                weight_trend = "increasing"
                weight_note  = f"Gained {round(delta,1)} kg -- tighten calories this week."
            else:
                weight_trend = "stable"
                weight_note  = "Weight is stable -- consider reducing portions slightly."

        lines = ["Last week's tracking summary:"]

        if eaten_meals:
            lines.append(f"- Meals eaten: {', '.join(eaten_meals[:10])}")
            lines.append("  (avoid repeating these for variety)")
        else:
            lines.append("- No meal logs from last week.")

        if skipped_meals:
            lines.append(f"- Meals skipped: {', '.join(skipped_meals[:5])}")

        if most_skipped and skips[most_skipped] > 0:
            lines.append(
                f"- Most skipped meal type: {most_skipped} "
                f"({skips[most_skipped]} skips) -- assign simpler/quicker options here."
            )

        lines.append(
            f"- Last week adherence: {adherence['adherence_pct']}% "
            f"({adherence['eaten']} eaten, {adherence['skipped']} skipped)"
        )
        if adherence["adherence_pct"] < 50 and adherence["logged"] >= 6:
            lines.append("  -> Low adherence: plan easier, quicker meals this week.")

        if weight_note:
            lines.append(f"- Weight trend: {weight_trend}. {weight_note}")

        return "\n".join(lines)

    except Exception:
        return ""  # tracking not yet populated -- skip silently


def generate_weekly_plan(profile: dict | None = None) -> dict:
    if profile is None:
        profile = load_profile() or {}

    recipe_pool = _fetch_recipe_pool(profile)
    profile_context = profile_to_context(profile)
    busy_days = set(profile.get("busy_days", []))
    tracking_context = _build_tracking_context()

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

{tracking_context}

Week starts: {next_monday} (Monday)

Available recipes:
{recipe_text}

Build the 7-day meal plan using the history and profile above.
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
# Fast single-meal swap (no LLM needed)
# ---------------------------------------------------------------------------

def swap_meal(day: str, meal_type: str, meal_name: str) -> dict:
    """
    Directly swap one meal in the existing plan with a named recipe.
    Much faster than replan_day -- no LLM call, just a recipe lookup.
    Returns the updated meal dict or an error.
    """
    from diet_agent import get_recipe_details

    plan = load_meal_plan()
    if not plan:
        return {"error": "No meal plan found. Generate a weekly plan first."}

    if meal_type not in ("breakfast", "lunch", "dinner"):
        return {"error": f"Invalid meal type '{meal_type}'. Use breakfast, lunch, or dinner."}

    # Look up recipe in database
    recipe = get_recipe_details(meal_name)
    if "error" in recipe:
        # Try a fuzzy search fallback
        from diet_agent import search_recipes
        results = search_recipes(meal_name)
        if not results:
            return {"error": f"No recipe found matching '{meal_name}'. Try a different name."}
        recipe = results[0]

    new_meal = {
        "name": recipe["name"],
        "category": recipe.get("category", ""),
        "cooking_time_minutes": recipe.get("cooking_time_minutes", 0),
        "why": f"Requested by user for {meal_type}",
        "estimated_calories": 0,
        "estimated_protein_g": 0,
        "estimated_carbs_g": 0,
        "estimated_fat_g": 0,
    }

    # Update the plan
    replaced = False
    for day_plan in plan["days"]:
        if day_plan["day"].lower() == day.lower():
            day_plan[meal_type] = new_meal
            replaced = True
            break

    if not replaced:
        return {"error": f"Day '{day}' not found in the current plan."}

    save_meal_plan(plan)
    return {
        "success": True,
        "day": day,
        "meal_type": meal_type,
        "new_meal": recipe["name"],
        "message": f"{day}'s {meal_type} has been changed to {recipe['name']}. Check the Weekly Meal Plan tab.",
    }


# ---------------------------------------------------------------------------
# Replan a single day
# ---------------------------------------------------------------------------

REPLAN_SYSTEM = """
You are a diet coach adjusting a single day in an existing weekly meal plan.
Given a reason for the change and a list of available recipes, re-generate
breakfast, lunch, and dinner for that one day only.

Rules:
- Only use recipes from the provided list, EXCEPT for "Dining Out" (see below).
- If the reason mentions eating out, a restaurant, a dinner event, or a social event
  for a specific meal, set that meal as follows:
    name: "Dining Out"
    category: "Restaurant"
    cooking_time_minutes: 0
    why: one sentence describing the event (e.g. "Dinner out at a restaurant on Sunday")
    estimated_calories: 600, estimated_protein_g: 30, estimated_carbs_g: 60, estimated_fat_g: 25
- If the reason mentions being very busy, all meals must be <= 20 minutes.
- Respect the user's dietary restrictions for any home-cooked meals.
- The "why" field should reference the reason for replanning.
- Provide realistic nutrition estimates for all meals.
- total_calories/protein/carbs/fat = sum of the three meals.
""".strip()


def replan_day(day: str, reason: str, profile: dict | None = None) -> dict:
    """Re-generate a single day's meals in the existing plan."""
    if profile is None:
        profile = load_profile() or {}

    plan = load_meal_plan()
    if not plan:
        return {"error": "No existing meal plan found. Generate a weekly plan first."}

    recipe_pool = _fetch_recipe_pool(profile)
    profile_context = profile_to_context(profile)
    busy_days = set(profile.get("busy_days", []))
    is_busy = day in busy_days or "busy" in reason.lower()

    recipe_lines = [
        f"- {r['name']} | category: {r.get('category','?')} | "
        f"time: {r.get('cooking_time_minutes','?')} min | area: {r.get('area','?')}"
        for r in recipe_pool
    ]

    user_prompt = f"""
{profile_context}

Day to replan: {day}
Reason: {reason}
Is busy day: {is_busy}

Available recipes:
{chr(10).join(recipe_lines)}

Replan only {day}. Return a single DayPlan object.
""".strip()

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        max_tokens=1500,
        messages=[
            {"role": "system", "content": REPLAN_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        response_format=DayPlan,
    )

    new_day = response.choices[0].message.parsed
    if new_day is None:
        return {"error": "Could not generate a new plan for that day. Please try again."}

    new_day_dict = new_day.model_dump()
    new_day_dict["day"] = day
    new_day_dict["is_busy"] = is_busy

    # Auto-compute totals if LLM left them as 0
    if new_day_dict["total_calories"] == 0:
        for meal_key in ["breakfast", "lunch", "dinner"]:
            m = new_day_dict[meal_key]
            new_day_dict["total_calories"] += m.get("estimated_calories", 0)
            new_day_dict["total_protein_g"] += m.get("estimated_protein_g", 0)
            new_day_dict["total_carbs_g"] += m.get("estimated_carbs_g", 0)
            new_day_dict["total_fat_g"] += m.get("estimated_fat_g", 0)

    # Replace the day in existing plan
    replaced = False
    for i, d in enumerate(plan["days"]):
        if d["day"].lower() == day.lower():
            plan["days"][i] = new_day_dict
            replaced = True
            break

    if not replaced:
        plan["days"].append(new_day_dict)

    save_meal_plan(plan)
    return {
        "success": True,
        "day": day,
        "breakfast": new_day_dict["breakfast"]["name"],
        "lunch": new_day_dict["lunch"]["name"],
        "dinner": new_day_dict["dinner"]["name"],
        "message": f"{day} has been updated. Check the Weekly Meal Plan tab to see the changes.",
    }


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
