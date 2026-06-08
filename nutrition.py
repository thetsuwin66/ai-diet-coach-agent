"""
Nutrition lookup using USDA FoodData Central API.

Free API key: https://fdc.nal.usda.gov/api-guide.html
Add to .env:  USDA_API_KEY=your-key-here
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

USDA_API_KEY = os.getenv("USDA_API_KEY", "")
USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# USDA nutrient IDs we care about
NUTRIENT_MAP = {
    1008: "calories_kcal",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carbs_g",
    1079: "fiber_g",
}


def get_nutrition_info(food_name: str) -> dict:
    """
    Look up nutrition info for a food item or dish name.
    Returns calories, protein, fat, carbs, and fiber per 100g serving.
    """
    if not USDA_API_KEY:
        return {
            "error": (
                "USDA_API_KEY not configured. "
                "Get a free key at https://fdc.nal.usda.gov/api-guide.html "
                "and add it to your .env file as USDA_API_KEY=your-key-here"
            )
        }

    try:
        resp = requests.get(
            USDA_SEARCH_URL,
            params={
                "query": food_name,
                "api_key": USDA_API_KEY,
                "pageSize": 1,
                "dataType": "Foundation,SR Legacy",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"error": f"USDA API request failed: {e}"}

    foods = data.get("foods", [])
    if not foods:
        return {"error": f"No nutrition data found for '{food_name}'"}

    food = foods[0]
    result = {
        "food_name": food.get("description", food_name),
        "serving": "per 100g",
        "brand": food.get("brandOwner", ""),
    }

    for nutrient in food.get("foodNutrients", []):
        nid = nutrient.get("nutrientId")
        if nid in NUTRIENT_MAP:
            key = NUTRIENT_MAP[nid]
            result[key] = round(nutrient.get("value", 0), 1)

    # Ensure all fields present
    for field in ["calories_kcal", "protein_g", "fat_g", "carbs_g", "fiber_g"]:
        result.setdefault(field, None)

    return result
