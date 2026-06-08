"""
User profile management for the AI Diet Coach.

Handles registration, login (username + hashed password),
and profile CRUD. All data is stored in data/profile.json.
Single-user per installation.
"""

import hashlib
import json
import os
import secrets
from pathlib import Path

PROFILE_PATH = Path(__file__).parent.parent / "data" / "profile.json"

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

CUISINE_OPTIONS = [
    "Thai", "Japanese", "Korean", "Filipino", "Indonesian",
    "Chinese", "Vietnamese", "Indian", "Western", "Mediterranean",
    "Mexican", "Italian",
]

ACTIVITY_LEVELS = [
    "Sedentary (little or no exercise)",
    "Light (1-3 days/week)",
    "Moderate (3-5 days/week)",
    "Active (6-7 days/week)",
    "Very active (twice a day)",
]


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return key.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    computed, _ = _hash_password(password, salt)
    return computed == stored_hash


# ---------------------------------------------------------------------------
# Profile load / save
# ---------------------------------------------------------------------------

def profile_exists() -> bool:
    return PROFILE_PATH.exists()


def load_profile() -> dict | None:
    if not PROFILE_PATH.exists():
        return None
    with open(PROFILE_PATH) as f:
        return json.load(f)


def save_profile(profile: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)


def create_profile(username: str, password: str) -> dict:
    pw_hash, salt = _hash_password(password)
    profile = {
        "username": username,
        "password_hash": pw_hash,
        "password_salt": salt,
        # Health goals
        "current_weight_kg": None,
        "target_weight_kg": None,
        "deadline": None,
        # Body stats (for calorie calculation)
        "height_cm": None,
        "age": None,
        "gender": "",
        # Calorie targets (computed from body stats)
        "daily_calorie_target": None,
        "daily_protein_g": None,
        "daily_carbs_g": None,
        "daily_fat_g": None,
        # Diet
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        # Schedule
        "busy_days": [],
        # Location
        "location": "",
        # Activity
        "activity_level": "",
        # Onboarding complete flag
        "onboarding_complete": False,
    }
    save_profile(profile)
    return profile


def update_profile(updates: dict) -> dict:
    profile = load_profile() or {}
    profile.update(updates)
    save_profile(profile)
    return profile


def is_onboarding_complete() -> bool:
    profile = load_profile()
    if not profile:
        return False
    return bool(profile.get("onboarding_complete"))


# ---------------------------------------------------------------------------
# Profile summary for agent injection
# ---------------------------------------------------------------------------

def profile_to_context(profile: dict) -> str:
    """Return a plain-text summary of the user profile for the agent system prompt."""
    if not profile or not profile.get("onboarding_complete"):
        return ""

    lines = ["User profile:"]

    cw  = profile.get("current_weight_kg")
    tw  = profile.get("target_weight_kg")
    dl  = profile.get("deadline")
    age = profile.get("age")
    ht  = profile.get("height_cm")
    gen = profile.get("gender")
    cal = profile.get("daily_calorie_target")

    if cw and tw:
        lines.append(f"- Weight goal: {cw}kg -> {tw}kg by {dl or 'no deadline set'}")
    if age and ht and gen:
        lines.append(f"- Body: {gen}, {age} years old, {ht} cm")
    if cal:
        lines.append(
            f"- Daily calorie target: {cal} kcal "
            f"(protein {profile.get('daily_protein_g')}g / "
            f"carbs {profile.get('daily_carbs_g')}g / "
            f"fat {profile.get('daily_fat_g')}g)"
        )

    restrictions = profile.get("dietary_restrictions", [])
    if restrictions:
        lines.append(f"- Dietary restrictions: {', '.join(restrictions)}")
    else:
        lines.append("- No dietary restrictions")

    cuisines = profile.get("preferred_cuisines", [])
    if cuisines:
        lines.append(f"- Preferred cuisines: {', '.join(cuisines)}")

    busy = profile.get("busy_days", [])
    if busy:
        lines.append(f"- Busy days (less time to cook): {', '.join(busy)}")

    location = profile.get("location", "")
    if location:
        lines.append(f"- Location: {location}")

    activity = profile.get("activity_level", "")
    if activity:
        lines.append(f"- Activity level: {activity}")

    return "\n".join(lines)
