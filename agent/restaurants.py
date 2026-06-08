"""
Nearby restaurant finder using Google Maps Places API (classic Text Search).

Steps to get a free API key:
1. Go to https://console.cloud.google.com
2. Create a project -> APIs & Services -> Enable APIs
3. Enable "Places API" (the classic one, not "Places API New")
4. Go to Credentials -> Create API Key
5. Add to .env: GOOGLE_MAPS_API_KEY=your-key-here

Free tier includes $200/month credit (~5,000 text searches).
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


def find_nearby_restaurants(location: str, dietary_preference: str = "") -> list:
    """
    Find diet-friendly restaurants near the user's location.

    Args:
        location: City or address from user profile (e.g. "Singapore 210662")
        dietary_preference: Optional filter like "healthy", "vegetarian", "low calorie"

    Returns list of restaurants with name, address, rating, and price level.
    """
    if not GOOGLE_MAPS_API_KEY:
        return [{
            "error": (
                "GOOGLE_MAPS_API_KEY not configured. "
                "Get a free key at https://console.cloud.google.com "
                "(enable Places API) and add to .env as GOOGLE_MAPS_API_KEY=your-key-here"
            )
        }]

    if not location:
        return [{"error": "No location set in your profile. Please update your profile with your city."}]

    preference = dietary_preference or "healthy"
    query = f"{preference} restaurant near {location}"

    try:
        resp = requests.get(
            PLACES_URL,
            params={
                "query": query,
                "key": GOOGLE_MAPS_API_KEY,
                "type": "restaurant",
                "language": "en",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return [{"error": f"Google Maps API request failed: {e}"}]

    status = data.get("status")
    if status == "REQUEST_DENIED":
        return [{"error": f"API key error: {data.get('error_message', 'REQUEST_DENIED')}. Make sure 'Places API' is enabled in Google Cloud Console."}]
    if status == "ZERO_RESULTS":
        return [{"message": f"No restaurants found near '{location}' for '{preference}'."}]
    if status != "OK":
        return [{"error": f"Google Maps returned status: {status}"}]

    results = []
    for p in data.get("results", [])[:5]:
        price_level = p.get("price_level")
        price_str = "$" * price_level if price_level else ""
        results.append({
            "name": p.get("name", "Unknown"),
            "address": p.get("formatted_address", ""),
            "rating": p.get("rating"),
            "reviews": p.get("user_ratings_total"),
            "price": price_str,
            "open_now": p.get("opening_hours", {}).get("open_now"),
        })

    return results
