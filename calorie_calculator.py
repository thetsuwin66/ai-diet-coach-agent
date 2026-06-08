"""
Calorie budget calculator using the Mifflin-St Jeor equation.

Calculates BMR -> TDEE -> daily target for weight loss.
"""

ACTIVITY_MULTIPLIERS = {
    "Sedentary (little or no exercise)": 1.2,
    "Light (1-3 days/week)":             1.375,
    "Moderate (3-5 days/week)":          1.55,
    "Active (6-7 days/week)":            1.725,
    "Very active (twice a day)":         1.9,
}

# 0.5 kg/week loss requires ~500 kcal daily deficit
DEFICIT_PER_KG_WEEK = 500


def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    """Mifflin-St Jeor BMR formula."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if gender.lower() == "male" else base - 161


def calculate_tdee(bmr: float, activity_level: str) -> float:
    multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
    return round(bmr * multiplier)


def calculate_daily_target(
    weight_kg: float,
    target_weight_kg: float,
    height_cm: float,
    age: int,
    gender: str,
    activity_level: str,
    weekly_loss_kg: float = 0.5,
) -> dict:
    """
    Returns a full calorie breakdown:
    - bmr, tdee, daily_target, weekly_deficit
    - macro split (protein 30%, carbs 40%, fat 30%)
    """
    bmr = calculate_bmr(weight_kg, height_cm, age, gender)
    tdee = calculate_tdee(bmr, activity_level)
    deficit = int(weekly_loss_kg * DEFICIT_PER_KG_WEEK)
    daily_target = max(1200, tdee - deficit)  # never below 1200 kcal

    # Macro split (protein 30%, carbs 40%, fat 30%)
    protein_g = round(daily_target * 0.30 / 4)   # 4 kcal per gram
    carbs_g   = round(daily_target * 0.40 / 4)
    fat_g     = round(daily_target * 0.30 / 9)   # 9 kcal per gram

    return {
        "bmr": round(bmr),
        "tdee": tdee,
        "daily_target": daily_target,
        "deficit": deficit,
        "weekly_loss_kg": weekly_loss_kg,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
    }


def calorie_context_for_prompt(profile: dict) -> str:
    """Returns a one-liner for injection into the agent/planner prompt."""
    target = profile.get("daily_calorie_target")
    if not target:
        return ""
    protein = profile.get("daily_protein_g", "")
    carbs   = profile.get("daily_carbs_g", "")
    fat     = profile.get("daily_fat_g", "")
    return (
        f"Daily calorie target: {target} kcal "
        f"(protein {protein}g / carbs {carbs}g / fat {fat}g). "
        f"Plan meals to hit this target."
    )
