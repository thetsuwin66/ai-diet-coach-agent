# AI Diet Coach Agent

A personalized AI diet coach that learns your goals, builds a weekly meal plan, tracks what you eat, and adapts when life gets in the way.

---

## Problem Statement

People trying to lose weight struggle to turn a vague goal — "I want to lose 8 kg in 2 months" — into a realistic daily plan they can stick to. Generic diet apps don't account for their schedule, food preferences, cooking ability, cultural background, or location. They need a personal coach, not just a calorie counter.

This agent specifically targets users in Southeast Asia who follow Asian diets (Thai, Filipino, Korean, Japanese, Chinese, Vietnamese, etc.), a demographic underserved by Western-centric diet tools.

---

## What It Does

1. **Onboarding** — the agent interviews you to collect your weight, target, timeline, dietary restrictions, preferred cuisines, busy days, location, and body stats.
2. **Weekly meal plan** — generates a personalised 7-day plan (breakfast, lunch, dinner) using 256 recipes (TheMealDB + custom Asian dataset), respecting your restrictions, cuisines, and busy days.
3. **Nutritional tracking** — estimates daily calories, protein, carbs, and fat. Calculates your personal calorie target using the Mifflin-St Jeor formula.
4. **Daily tracking** — mark each meal as eaten or skipped. Log your weight. The next plan generation uses this history to avoid repeats and tighten/loosen calorie targets based on your trend.
5. **Adaptive replanning** — ask the agent to swap a specific meal ("omelette for Tuesday breakfast") or replan a full day ("I have a dinner event on Friday").
6. **Restaurant suggestions** — on busy days the agent finds healthy restaurants near you via Google Maps.
7. **Nutrition lookup** — ask about calories and macros for any food via the USDA FoodData Central API.
8. **Shopping list** — one click generates a grouped ingredient list from your weekly plan.
9. **Chat memory** — each session is summarised and carried into the next so the agent remembers your preferences across conversations.
10. **Progress tab** — weight trend chart, weekly adherence stats, skip-pattern analysis, and an "adjust plan" button when you're off track.

---

## Architecture

```
app.py                  Streamlit UI (login, onboarding, chat, meal plan, progress)
diet_agent.py           Agent loop + all tool definitions (10 tools)
meal_planner.py         Weekly plan generator and single-day replan/swap
user_profile.py         Profile storage with password hashing
tracking.py             Meal logging, weight logging, adherence metrics
calorie_calculator.py   Mifflin-St Jeor BMR/TDEE/macro calculator
shopping_list.py        Ingredient extractor and category grouper
chat_memory.py          Session summariser and memory store
nutrition.py            USDA FoodData Central API integration
restaurants.py          Google Maps Places API integration
monitoring.py           Trace logger (saves every agent call to data/traces/)
eval_judge.py           LLM judge with 3 prompt versions and alignment metrics
run_evals.py            Batch evaluation runner (60 scenarios)
label_evals.py          Streamlit labeling tool for ground-truth dataset
```

### Agent Tools

| Tool | Description |
|---|---|
| `search_recipes` | Full-text search over 256 recipes (RAG with minsearch) |
| `filter_by_max_cook_time` | Returns recipes within a time limit |
| `filter_by_category` | Returns recipes by category (Chicken, Seafood, Vegetarian, etc.) |
| `get_recipe_details` | Full ingredients and step-by-step instructions for a recipe |
| `generate_meal_plan` | Generates a personalised 7-day meal plan |
| `swap_meal` | Instantly swaps one meal slot with a named dish (no LLM needed) |
| `replan` | Re-generates all meals for a specific day (for schedule changes) |
| `get_nutrition_info` | Looks up calories/macros via USDA API |
| `find_nearby_restaurants` | Finds healthy restaurants via Google Maps |

### Knowledge Base

- **Western recipes**: 201 recipes from TheMealDB
- **Asian recipes**: 55 hand-curated recipes (Thai, Korean, Filipino, Japanese, Chinese, Vietnamese, Indonesian, Malaysian, Singaporean, Indian)
- **Search**: minsearch (TF-IDF over name, category, area, ingredients, instructions)

---

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager

### 1. Clone the repo

```bash
git clone <repo-url>
cd ai-diet-coach-agent
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure API keys

```bash
cp .env.example .env
```

Open `.env` and fill in:

```
# Required
OPENAI_API_KEY=your-openai-key

# Optional: nutrition lookup (free) — https://fdc.nal.usda.gov/api-guide.html
USDA_API_KEY=your-usda-key

# Optional: restaurant search (free tier) — console.cloud.google.com
# Enable "Places API" under APIs & Services
GOOGLE_MAPS_API_KEY=your-google-maps-key
```

The app runs without the optional keys — those features will show a helpful message explaining how to get them.

### 4. Run the app

```bash
uv run streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Running with Docker

### Option A — Docker Compose (recommended)

```bash
# Copy and fill in your API keys
cp .env.example .env

# Build and start the app
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501).

User data (profile, meal plan, tracking logs, traces) is persisted in the local `./data` folder via a volume mount.

### Option B — Labeling tool alongside the app

```bash
docker compose --profile eval up --build
```

This starts two services:
- `http://localhost:8501` — main diet coach app
- `http://localhost:8502` — evaluation labeling tool

### Option C — Docker only (no compose)

```bash
docker build -t ai-diet-coach .
docker run -p 8501:8501 --env-file .env -v $(pwd)/data:/app/data ai-diet-coach
```

On first launch you will be prompted to create an account and complete a short onboarding questionnaire.

---

## Makefile

A `Makefile` is included for convenience:

```bash
make install      # Install dependencies with uv
make run          # Start the Streamlit app locally
make test         # Run the test suite
make eval         # Run batch evaluation (60 scenarios)
make judge        # Run LLM judge and print alignment metrics
make label        # Open the labeling tool on port 8502
make docker-build # Build the Docker image
make docker-up    # Start the app with docker compose
make docker-down  # Stop docker compose services
```

---

## Deploying to Streamlit Cloud

1. Push this repo to GitHub.

2. Go to [share.streamlit.io](https://share.streamlit.io) and click **New app**.

3. Select your repo, branch (`main`), and set the main file to `app.py`.

4. Under **Advanced settings**, set Python version to **3.12**.

5. Open **Secrets** and paste:

```toml
OPENAI_API_KEY = "your-openai-key"
USDA_API_KEY = "your-usda-key"
GOOGLE_MAPS_API_KEY = "your-google-maps-key"
```

6. Click **Deploy**. Streamlit Cloud will install `requirements.txt` and launch the app.

---

## Running Tests

```bash
uv run pytest tests/ -v
```

Tests cover:

- `tests/test_agent.py` — deterministic checks (tool call order, argument values, out-of-scope behaviour)
- `tests/test_judge.py` — LLM-judge tests for qualitative response properties

---

## Evaluation

### Step 1 — Run batch scenarios

```bash
uv run python run_evals.py
```

Runs 60 evaluation scenarios (happy path, varied phrasing, edge cases, out-of-scope, breaking scenarios) through the agent and saves results to `eval_results.json`.

### Step 2 — Label responses (ground-truth dataset)

```bash
uv run streamlit run label_evals.py
```

Opens a Streamlit labeling tool. Label each response as good/bad and assign a failure category (hallucination, wrong_scope, incomplete, etc.). Labels are saved to `labels.csv`.

The project includes 30 pre-labeled responses covering all scenario types.

### Step 3 — Run the LLM judge

```bash
# Compare all three prompt versions
uv run python eval_judge.py

# Run a specific version
uv run python eval_judge.py --version v3
```

Runs three judge prompt versions (v1, v2, v3) against the labeled dataset and prints alignment metrics:

| Version | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| v1 | 60.0% | 38.9% | 87.5% | 53.8% |
| v2 | 63.3% | 42.1% | 100% | 59.3% |
| v3 | **80.0%** | **60.0%** | 75.0% | **66.7%** |

The key improvement in v3 was adding intent classification (diet-focused vs time-focused vs recipe lookup) so the calorie-fitness rule only fires when the user explicitly mentions diet goals. This cut false positives from 11 to 4.

Full results are saved to `judge_results.json`.

---

## Monitoring

Every agent interaction is saved as a JSON trace in `data/traces/`. Each trace contains:

- Question and full answer
- Tool calls made (name + arguments)
- Token counts (input and output)
- Response latency
- User feedback (thumbs up/down, collected in the chat UI)

### Viewing traces

Run the main app and check the **Session stats** panel in the sidebar. All-time stats (total sessions, average latency, feedback summary) are displayed there.

To inspect raw traces programmatically:

```python
from monitoring import load_all_traces, print_summary
print_summary()
```

---

## Reproducibility

Everything needed to reproduce the project from scratch:

```
uv sync                          # install exact dependency versions (uv.lock)
cp .env.example .env             # add your API keys
uv run streamlit run app.py      # start the app
uv run pytest tests/ -v          # run tests
uv run python run_evals.py       # run batch evaluation
uv run python eval_judge.py      # run LLM judge
uv run streamlit run label_evals.py  # open labeling tool
```

Dependencies are pinned in `uv.lock`. The recipe datasets (`data/recipes.json`, `data/asian_recipes.json`) are included in the repository. No external data downloads are required.

---

## Project Structure

```
ai-diet-coach-agent/
├── app.py                  Main Streamlit application
├── diet_agent.py           Agent loop and tool registry
├── meal_planner.py         Meal plan generation and replanning
├── user_profile.py         User authentication and profile management
├── tracking.py             Daily meal and weight tracking
├── calorie_calculator.py   BMR/TDEE calorie budget calculation
├── shopping_list.py        Shopping list generator
├── chat_memory.py          Cross-session conversation memory
├── nutrition.py            USDA nutrition API integration
├── restaurants.py          Google Maps restaurant search
├── monitoring.py           Trace logging
├── eval_judge.py           LLM judge with alignment metrics
├── run_evals.py            Batch evaluation runner
├── label_evals.py          Ground-truth labeling tool
├── scenarios.csv           60 evaluation scenarios
├── labels.csv              30 hand-labeled ground-truth responses
├── eval_results.json       Batch evaluation results
├── judge_results.json      LLM judge results (v1/v2/v3)
├── data/
│   ├── recipes.json        201 TheMealDB recipes
│   ├── asian_recipes.json  55 Asian recipes (custom dataset)
│   ├── meal_plan.json      Current weekly meal plan
│   ├── profile.json        User profile (gitignored)
│   ├── tracking.json       Meal and weight logs (gitignored)
│   └── traces/             Agent interaction traces (gitignored)
├── tests/
│   ├── test_agent.py       Deterministic agent tests
│   ├── test_judge.py       LLM-judge tests
│   └── judge.py            Judge helper used in tests
├── notebooks/
│   ├── 01-setup.ipynb      Environment smoke test
│   └── 02-rag.ipynb        RAG pipeline exploration
├── pyproject.toml          Project metadata and dependencies
└── uv.lock                 Pinned dependency versions
```
