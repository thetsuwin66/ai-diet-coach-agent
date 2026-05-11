"""
Deterministic tests for the AI Diet Coach agent.

Each test runs the agent on a fixed prompt and checks concrete, observable
properties of the result - no LLM judge involved.
"""

import pytest
from diet_agent import run_agent


# ---------------------------------------------------------------------------
# Scenario 1: general high-protein query triggers search_recipes
#
# The agent should call search_recipes as its first tool when the user asks
# for high-protein meals. The answer must name at least one recipe and
# mention cooking time.
# ---------------------------------------------------------------------------
def test_high_protein_query_calls_search_recipes():
    result = run_agent("I want a high-protein dinner. What do you recommend?")

    tool_names = [tc.name for tc in result.tool_calls]
    assert len(tool_names) >= 1, "agent made no tool calls"
    assert tool_names[0] == "search_recipes", (
        f"expected search_recipes as first tool, got {tool_names[0]}"
    )


def test_high_protein_answer_mentions_cooking_time():
    result = run_agent("I want a high-protein dinner. What do you recommend?")

    answer_lower = result.answer.lower()
    assert "min" in answer_lower, (
        "answer does not mention cooking time (expected 'min')"
    )


# ---------------------------------------------------------------------------
# Scenario 2: time-constrained query triggers filter_by_max_cook_time
#
# When the user says "only 15 minutes", the agent must call
# filter_by_max_cook_time (not just search_recipes) so the recommendations
# are guaranteed to fit the time budget.
# ---------------------------------------------------------------------------
def test_time_constrained_query_calls_filter_by_max_cook_time():
    result = run_agent("I only have 15 minutes. What can I cook?")

    tool_names = [tc.name for tc in result.tool_calls]
    assert "filter_by_max_cook_time" in tool_names, (
        f"expected filter_by_max_cook_time to be called, got {tool_names}"
    )


def test_time_constrained_max_minutes_argument():
    result = run_agent("I only have 15 minutes. What can I cook?")

    for tc in result.tool_calls:
        if tc.name == "filter_by_max_cook_time":
            assert tc.arguments.get("max_minutes") <= 15, (
                f"filter_by_max_cook_time called with max_minutes="
                f"{tc.arguments.get('max_minutes')}, expected <= 15"
            )
            break


# ---------------------------------------------------------------------------
# Scenario 3: full-recipe request triggers get_recipe_details
#
# When the user asks for full cooking instructions for a specific dish,
# the agent should call get_recipe_details and include actual steps in
# the answer, not just a general description.
# ---------------------------------------------------------------------------
def test_full_recipe_request_calls_get_recipe_details():
    result = run_agent(
        "How do I make a beef stir-fry? Give me the full recipe with steps."
    )

    tool_names = [tc.name for tc in result.tool_calls]
    assert "get_recipe_details" in tool_names, (
        f"expected get_recipe_details to be called, got {tool_names}"
    )


def test_full_recipe_answer_includes_ingredients():
    result = run_agent(
        "How do I make a beef stir-fry? Give me the full recipe with steps."
    )

    answer_lower = result.answer.lower()
    assert "ingredient" in answer_lower or "tablespoon" in answer_lower or "cup" in answer_lower or "g " in answer_lower, (
        "answer does not appear to include ingredient quantities"
    )


# ---------------------------------------------------------------------------
# Scenario 4: out-of-scope request - agent should not hallucinate capabilities
#
# When the user asks the agent to book a restaurant, it cannot and should not
# pretend otherwise. No tool calls are expected, and the answer should not
# claim the agent can make bookings.
# ---------------------------------------------------------------------------
def test_out_of_scope_does_not_claim_booking_capability():
    result = run_agent(
        "Can you book me a table at a nearby restaurant for tonight?"
    )

    answer_lower = result.answer.lower()
    # The agent must not claim it made or can make a booking
    assert "booked" not in answer_lower and "reservation confirmed" not in answer_lower, (
        "agent incorrectly claimed to have made a booking"
    )


# ---------------------------------------------------------------------------
# Scenario 5: category filter query triggers filter_by_category
#
# When the user explicitly restricts to a protein type, the agent should
# call filter_by_category so it does not recommend off-category dishes.
# ---------------------------------------------------------------------------
def test_category_query_calls_filter_by_category():
    result = run_agent("Show me only vegetarian dishes I can make.")

    tool_names = [tc.name for tc in result.tool_calls]
    assert "filter_by_category" in tool_names, (
        f"expected filter_by_category to be called, got {tool_names}"
    )


def test_category_query_passes_correct_category():
    result = run_agent("Show me only vegetarian dishes I can make.")

    for tc in result.tool_calls:
        if tc.name == "filter_by_category":
            cat = tc.arguments.get("category", "").lower()
            assert "vegetarian" in cat, (
                f"expected category argument to contain 'vegetarian', got '{cat}'"
            )
            break
