# AI Diet Coach Agent

A personalized AI diet coach that interviews you, builds a weekly meal plan, and adapts it when life gets in the way.

## The Problem

People trying to lose weight struggle to stay consistent — generic meal plans don't account for a busy schedule, local restaurant options, or dietary restrictions, so they get abandoned fast.

## What It Does

The agent interviews the user to collect their current weight, target weight, deadline, dietary restrictions, daily schedule, and location. It then generates a personalized weekly meal plan: recipes for days they have time to cook, and nearby restaurant suggestions for busy days. When plans change — a late meeting, a trip, a craving — the agent re-plans automatically.

Typical interaction:
1. The user answers a short set of questions (weight, goal, timeline, restrictions, schedule, city).
2. The agent produces a 7-day meal plan with recipes and calorie estimates for cook-at-home days, and ranked restaurant suggestions (filtered by dietary needs) for busy days.
3. If the user reports a change ("I can't cook Wednesday"), the agent revises just that day and updates the plan.

## Setup

1. Install uv if you don't have it yet: https://docs.astral.sh/uv/getting-started/installation/

2. Clone this repository (or download the zip and extract it).

3. Create a `.env` file from the template and add your API key:

       cp .env.example .env

4. Install dependencies:

       uv sync

5. Start Jupyter:

       uv run jupyter notebook

## Notebooks

- `notebooks/01-setup.ipynb` - smoke test that confirms your environment works
- `notebooks/02-rag.ipynb` - a minimal RAG baseline you can adapt to your own data

## Data

Put your project data in the `data/` folder. See `notebooks/02-rag.ipynb` for how to load it.
