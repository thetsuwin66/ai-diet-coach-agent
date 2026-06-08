"""
Shopping list generator from the weekly meal plan.

Extracts ingredients from every recipe in the plan,
deduplicates, and groups by category.
"""

from .diet_agent import get_recipe_details

CATEGORY_KEYWORDS = {
    "Proteins": [
        "chicken", "beef", "pork", "lamb", "shrimp", "prawn", "fish", "salmon",
        "tuna", "crab", "tofu", "tempeh", "egg", "eggs", "turkey", "duck", "mince",
        "sausage", "anchovy", "clam", "squid", "calamar",
    ],
    "Vegetables & Herbs": [
        "onion", "garlic", "ginger", "spring onion", "shallot", "tomato", "carrot",
        "broccoli", "spinach", "cabbage", "lettuce", "cucumber", "zucchini",
        "eggplant", "mushroom", "bok choy", "kangkong", "chilli", "pepper",
        "lemongrass", "galangal", "kaffir", "basil", "coriander", "mint",
        "papaya", "bean sprout", "bamboo", "celery", "pandan", "lime leaves",
        "leek", "chive", "radish",
    ],
    "Fruits": [
        "lime", "lemon", "mango", "pear", "tomato", "tamarind", "pineapple",
        "coconut", "calamansi",
    ],
    "Grains & Noodles": [
        "rice", "noodle", "pasta", "bread", "flour", "vermicelli", "ramen",
        "udon", "soba", "canton", "wonton wrapper", "spring roll wrapper",
        "gyoza wrapper", "mantou", "bun",
    ],
    "Dairy & Eggs": [
        "milk", "cream", "butter", "cheese", "yogurt", "paneer", "ghee",
    ],
    "Sauces & Condiments": [
        "soy sauce", "fish sauce", "oyster sauce", "hoisin", "kecap",
        "miso", "doubanjiang", "gochujang", "sriracha", "vinegar", "sesame oil",
        "chilli sauce", "tomato sauce", "curry paste", "sambal", "ssamjang",
        "worcestershire", "tahini",
    ],
    "Spices & Pantry": [
        "salt", "pepper", "sugar", "oil", "cumin", "coriander", "turmeric",
        "paprika", "chilli powder", "garam masala", "star anise", "cinnamon",
        "cardamom", "clove", "bay leaf", "saffron", "dashi", "stock", "broth",
        "cornstarch", "baking powder",
    ],
    "Nuts & Seeds": [
        "peanut", "sesame", "cashew", "almond", "walnut", "pine nut",
    ],
    "Canned & Dried": [
        "coconut milk", "canned", "dried", "paste", "powder", "seaweed",
        "nori", "wakame", "dried shrimp", "anchovy stock",
    ],
}


def _categorize(ingredient: str) -> str:
    ing_lower = ingredient.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in ing_lower:
                return category
    return "Other"


def _parse_ingredients(raw) -> list[str]:
    if isinstance(raw, list):
        return [i.strip() for i in raw if i.strip()]
    if isinstance(raw, str):
        return [i.strip() for i in raw.split(",") if i.strip()]
    return []


def generate_shopping_list(plan: dict) -> dict[str, list[str]]:
    """
    Returns a dict of {category: [sorted unique ingredients]}
    from all meals in the weekly plan.
    """
    all_ingredients: set[str] = set()

    for day_plan in plan.get("days", []):
        for meal_key in ["breakfast", "lunch", "dinner"]:
            meal = day_plan.get(meal_key, {})
            name = meal.get("name", "")
            if not name or name == "Dining Out":
                continue
            recipe = get_recipe_details(name)
            if "error" in recipe:
                continue
            for ing in _parse_ingredients(recipe.get("ingredients", [])):
                if ing:
                    all_ingredients.add(ing.lower())

    grouped: dict[str, list[str]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    grouped["Other"] = []

    for ingredient in sorted(all_ingredients):
        cat = _categorize(ingredient)
        grouped[cat].append(ingredient.title())

    # Remove empty categories
    return {k: sorted(v) for k, v in grouped.items() if v}
