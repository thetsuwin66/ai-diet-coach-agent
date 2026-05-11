"""
LLM judge tests for the AI Diet Coach agent.

These tests check qualities that are hard to assert with string matching,
such as whether recommendations are actually relevant to the user's goal
and whether the agent uses the right tools in the right order.
"""

import pytest
from diet_agent import run_agent
from tests.judge import assert_criteria


def test_high_protein_recommendations_are_relevant():
    result = run_agent("I want to lose weight. Suggest a high-protein dinner.")

    assert_criteria(result, [
        "the agent called search_recipes as the first tool call before giving any recommendation",
        "every recipe mentioned in the answer includes a cooking time expressed in minutes",
    ])


def test_time_constrained_recommendations_respect_limit():
    result = run_agent("I only have 15 minutes tonight. What can I cook?")

    assert_criteria(result, [
        "the agent called filter_by_max_cook_time with a max_minutes value of 15 or less",
        "every recipe the agent recommends has a cooking time of 15 minutes or less",
    ])


def test_full_recipe_response_contains_steps():
    result = run_agent(
        "How do I make a quick Asian stir-fry? Give me the full cooking steps."
    )

    assert_criteria(result, [
        "the agent called get_recipe_details at some point during the conversation",
        "the answer contains numbered or bulleted step-by-step cooking instructions, not just a general description",
    ])
