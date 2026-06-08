"""
Daily meal tracking and weight logging for the AI Diet Coach.

Stores data in data/tracking.json.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

TRACKING_PATH = Path(__file__).parent / "data" / "tracking.json"

MEAL_TYPES = ["breakfast", "lunch", "dinner"]
STATUS_EATEN  = "eaten"
STATUS_SKIPPED = "skipped"
STATUS_SWAPPED = "swapped"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not TRACKING_PATH.exists():
        return {"meal_logs": [], "weight_logs": []}
    with open(TRACKING_PATH) as f:
        return json.load(f)


def _save(data: dict) -> None:
    TRACKING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKING_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Meal logging
# ---------------------------------------------------------------------------

def log_meal(
    day: str,
    meal_type: str,
    meal_name: str,
    status: str,
    log_date: str | None = None,
    notes: str = "",
) -> None:
    data = _load()
    today = log_date or str(date.today())

    # Remove any existing log for same date + meal_type
    data["meal_logs"] = [
        m for m in data["meal_logs"]
        if not (m["date"] == today and m["meal_type"] == meal_type)
    ]

    data["meal_logs"].append({
        "date": today,
        "day": day,
        "meal_type": meal_type,
        "meal_name": meal_name,
        "status": status,
        "notes": notes,
        "logged_at": datetime.now().isoformat(),
    })
    _save(data)


def get_meal_log_for_date(log_date: str | None = None) -> dict:
    """Returns {meal_type: log_entry} for a given date."""
    target = log_date or str(date.today())
    data = _load()
    return {
        m["meal_type"]: m
        for m in data["meal_logs"]
        if m["date"] == target
    }


def get_meal_log_for_week(week_start: date | None = None) -> list[dict]:
    """Returns all logs from Monday to Sunday of the given week."""
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    dates = {str(week_start + timedelta(days=i)) for i in range(7)}
    data = _load()
    return [m for m in data["meal_logs"] if m["date"] in dates]


# ---------------------------------------------------------------------------
# Weight logging
# ---------------------------------------------------------------------------

def log_weight(weight_kg: float, log_date: str | None = None) -> None:
    data = _load()
    today = log_date or str(date.today())
    # Replace existing entry for today
    data["weight_logs"] = [w for w in data["weight_logs"] if w["date"] != today]
    data["weight_logs"].append({"date": today, "weight_kg": weight_kg})
    data["weight_logs"].sort(key=lambda x: x["date"])
    _save(data)


def get_weight_logs() -> list[dict]:
    return _load().get("weight_logs", [])


def get_latest_weight() -> float | None:
    logs = get_weight_logs()
    return logs[-1]["weight_kg"] if logs else None


# ---------------------------------------------------------------------------
# Adherence metrics
# ---------------------------------------------------------------------------

def get_weekly_adherence(week_start: date | None = None) -> dict:
    """
    Returns adherence stats for the current week.
    {
      total_planned, eaten, skipped, not_logged,
      adherence_pct,  -- % of logged meals that were eaten
      log_rate_pct,   -- % of planned meals that have any log
    }
    """
    logs = get_meal_log_for_week(week_start)
    total_planned = 7 * 3  # 7 days x 3 meals
    eaten   = sum(1 for m in logs if m["status"] == STATUS_EATEN)
    skipped = sum(1 for m in logs if m["status"] == STATUS_SKIPPED)
    logged  = eaten + skipped
    not_logged = total_planned - logged

    adherence_pct = round(eaten / logged * 100) if logged else 0
    log_rate_pct  = round(logged / total_planned * 100)

    return {
        "total_planned": total_planned,
        "eaten": eaten,
        "skipped": skipped,
        "not_logged": not_logged,
        "logged": logged,
        "adherence_pct": adherence_pct,
        "log_rate_pct": log_rate_pct,
    }


def get_skip_patterns(num_weeks: int = 2) -> dict:
    """
    Returns which meal types and days are most often skipped.
    Useful for adaptive replanning.
    """
    data = _load()
    today = date.today()
    cutoff = str(today - timedelta(weeks=num_weeks))
    recent = [m for m in data["meal_logs"] if m["date"] >= cutoff]

    skips_by_type = {"breakfast": 0, "lunch": 0, "dinner": 0}
    eaten_by_type = {"breakfast": 0, "lunch": 0, "dinner": 0}
    for m in recent:
        t = m.get("meal_type", "")
        if t in skips_by_type:
            if m["status"] == STATUS_SKIPPED:
                skips_by_type[t] += 1
            elif m["status"] == STATUS_EATEN:
                eaten_by_type[t] += 1

    return {
        "skips_by_meal_type": skips_by_type,
        "eaten_by_meal_type": eaten_by_type,
    }


# ---------------------------------------------------------------------------
# On-track check
# ---------------------------------------------------------------------------

def is_on_track(profile: dict) -> dict:
    """
    Returns a dict with on_track bool and a reason string.
    Checks: weight trend + weekly adherence.
    """
    weight_logs = get_weight_logs()
    adherence = get_weekly_adherence()
    issues = []

    # Weight trend check (need at least 2 logs)
    weight_trending_down = None
    if len(weight_logs) >= 2:
        first = weight_logs[0]["weight_kg"]
        latest = weight_logs[-1]["weight_kg"]
        target = profile.get("target_weight_kg")
        if target and latest > first:
            issues.append(f"Weight has gone up from {first}kg to {latest}kg")
            weight_trending_down = False
        else:
            weight_trending_down = True

    # Adherence check (only if user has been logging)
    if adherence["logged"] >= 6:  # at least 2 days logged
        if adherence["adherence_pct"] < 60:
            issues.append(
                f"Only {adherence['adherence_pct']}% of logged meals were eaten "
                f"({adherence['eaten']} eaten, {adherence['skipped']} skipped)"
            )

    on_track = len(issues) == 0
    return {
        "on_track": on_track,
        "issues": issues,
        "weight_trending_down": weight_trending_down,
        "adherence": adherence,
    }
