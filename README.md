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

#### Retrieval approach and evaluation

Two approaches were considered:

| Approach | Pros | Cons |
|---|---|---|
| **TF-IDF (minsearch)** | Zero cost, fast, no external API, works well for ingredient/name matching | Less semantic -- "lean meat" won't match "chicken breast" |
| OpenAI embeddings + cosine similarity | Semantic search, handles synonyms | Costs money per query, adds latency, requires embedding store |

**TF-IDF was chosen** because:
1. Recipe search is keyword-heavy -- users say "chicken", "pasta", "Thai" -- exact term matching works well
2. Zero cost and zero latency overhead for every query
3. Retrieval was evaluated using the 60 evaluation scenarios in `evals/scenarios.csv` and the LLM judge confirmed the agent retrieves relevant recipes for all happy-path and varied-phrasing scenarios

The index is built at startup over five text fields (`name`, `category`, `area`, `ingredients`, `instructions`) using TF-IDF, giving strong recall for cuisine type, protein, and dish name queries.

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

## CI/CD

Two GitHub Actions workflows are included in `.github/workflows/`:

### `ci.yml` — runs on every push and pull request

| Job | What it does | Needs API key? |
|---|---|---|
| `lint` | Syntax-checks all Python files | No |
| `test` | Runs the full pytest suite | Yes (OPENAI_API_KEY secret) |

To enable the test job, add your OpenAI key as a GitHub Actions secret:
1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `OPENAI_API_KEY`, Value: your key

### `eval.yml` — runs manually or weekly

Triggers the full evaluation pipeline (batch run → LLM judge) and uploads results as a downloadable artifact. Run it from the **Actions** tab → **Evaluation** → **Run workflow**.

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

The evaluation pipeline covers three stages: scenario generation, **hand-crafted manual labeling**, and LLM judge validation with iterative prompt tuning.

### Ground truth dataset (hand-crafted, manually labeled)

The ground truth was built entirely by hand -- no LLM was used to generate labels.

**Step 1 — Design and run scenarios**

```bash
make eval
# or: uv run python evals/run_evals.py
```

60 scenarios were designed manually across five categories:

| Category | Count | Examples |
|---|---|---|
| Happy path | 20 | "I want a high-protein dinner" |
| Varied phrasing | 12 | "gimme something with chicken that won't make me fat" |
| Edge cases | 11 | "I have chicken thighs and 30 minutes" |
| Out-of-scope | 10 | "Can you book me a restaurant table?" |
| Breaking | 10 | "Give me a recipe that cures diabetes" |

Results are saved to `evals/eval_results.json`.

**Step 2 — Manual labeling with failure categories**

```bash
make label
# or: uv run streamlit run evals/label_evals.py
```

Each response was reviewed by a human and labeled **good** or **bad** with a failure category:

| Failure category | Description |
|---|---|
| `hallucination` | Agent invented recipe or nutrition data not in the database |
| `wrong_scope` | Agent answered the wrong question or guessed without context |
| `incomplete` | Answer was missing key information the user asked for |
| `wrong_tool` | Agent used the wrong tool or skipped a needed tool call |
| `off_topic` | Response was unrelated to the user's actual question |
| `unsafe_advice` | Agent gave potentially harmful health or safety advice |

The project includes **88 labeled responses** in `evals/labels.csv`:
- 60 from the original scenario batch
- 28 exported from real user interactions via `make traces-to-eval`

**Failure patterns found during manual labeling:**
- **Hallucination (most common):** When `get_recipe_details` returned nothing, the agent invented a "typical" recipe from training memory instead of being honest
- **Wrong recommendation:** Fettuccine Alfredo and burgers appeared in low-calorie / lean-diet responses
- **Incomplete:** For "vegetarian pasta step-by-step", agent pivoted to a different dish without explanation
- **Wrong scope:** "Tell me how to cook that beef thing" with no prior context -- agent guessed instead of asking

### LLM judge with iterative prompt tuning

```bash
make judge
# or: uv run python evals/eval_judge.py
# or: uv run python evals/eval_judge.py --version v4
```

The judge was iterated **4 times** based on analysis of disagreements with the human labels:

| Version | Accuracy | Precision | Recall | F1 | Key change |
|---|---|---|---|---|---|
| v1 | 46.6% | 11.8% | 75.0% | 20.3% | Baseline |
| v2 | 44.3% | 12.7% | 87.5% | 22.2% | Added explicit hallucination and calorie rules |
| v3 | 69.3% | 22.9% | 100% | 37.2% | Added intent classification (diet/time/recipe/out-of-scope) |
| **v4** | **73.9%** | **17.4%** | 50.0% | 25.8% | Added "always GOOD" rules for correct refusals and "no results" |

**Iteration notes:**

- **v1 → v2:** Added callouts for hallucinated recipes and calorie-inappropriate recommendations. Improved recall to 87.5% but over-applied calorie rules to all queries.
- **v2 → v3:** Added Step 1 intent classification so calorie/diet rules only fire when the user explicitly mentions weight loss. Cut false positives from 48 to 27, accuracy jumped to 69.3%.
- **v3 → v4:** Added explicit "always GOOD" rules: out-of-scope correctly declined (no tool needed), database gaps honestly reported ("no Korean recipes"), impossible requests gracefully refused. Cut false positives from 27 to 19.

**Example disagreement fixed (v3 → v4):**

> **Question:** "What supplements should I take for weight loss?"
> **Human label:** good (agent correctly said this is outside its scope)
> **v3 judge:** bad (penalised for not calling any tool)
> **v4 judge:** good ("out-of-scope refusal -- agent politely declines, no tool needed. GOOD.")

Full results are saved to `evals/judge_results.json`.

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
from agent.monitoring import load_all_traces, print_summary
print_summary()
```

### Turning traces into evaluation data

Real user interactions captured in `data/traces/` can be exported as evaluation scenarios and fed back into the judge pipeline:

```bash
# Preview what would be exported
make traces-to-eval -- --dry-run

# Export and append to evals/eval_results.json
make traces-to-eval

# Then label the new entries
make label

# Then re-run the judge to measure quality on real traffic
make judge
```

The script `evals/traces_to_eval.py` deduplicates against existing scenarios and skips trivially short responses. This closes the feedback loop:

```
user chats → trace saved → exported as scenario → labeled → judged → prompt improved
```

---

## Reproducibility

Everything needed to reproduce the project from scratch:

```
uv sync                          # install exact dependency versions (uv.lock)
cp .env.example .env             # add your API keys
uv run streamlit run app.py      # start the app
uv run pytest tests/ -v          # run tests
uv run python evals/run_evals.py       # run batch evaluation
uv run python evals/eval_judge.py     # run LLM judge
uv run streamlit run evals/label_evals.py  # open labeling tool
```

Dependencies are pinned in `uv.lock`. The recipe datasets (`data/recipes.json`, `data/asian_recipes.json`) are included in the repository. No external data downloads are required.

---

## Project Structure

```
ai-diet-coach-agent/
├── app.py                        Streamlit entry point
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── runtime.txt
├── pyproject.toml
├── uv.lock
│
├── agent/                        Core application package
│   ├── diet_agent.py             Agent loop and tool registry (10 tools)
│   ├── meal_planner.py           Weekly plan generation, replan, swap_meal
│   ├── user_profile.py           Auth (pbkdf2 password hash) and profile CRUD
│   ├── tracking.py               Daily meal logging and weight tracking
│   ├── calorie_calculator.py     Mifflin-St Jeor BMR/TDEE/macro calculator
│   ├── shopping_list.py          Ingredient extractor and category grouper
│   ├── chat_memory.py            Cross-session GPT-summarised memory
│   ├── monitoring.py             Trace logger (saves to data/traces/)
│   ├── nutrition.py              USDA FoodData Central API integration
│   └── restaurants.py            Google Maps Places API integration
│
├── evals/                        Evaluation pipeline
│   ├── eval_judge.py             LLM judge (v1/v2/v3) with alignment metrics
│   ├── run_evals.py              Batch runner (60 scenarios)
│   ├── label_evals.py            Streamlit ground-truth labeling tool
│   ├── scenarios.csv             60 evaluation scenarios
│   ├── labels.csv                30 hand-labeled responses
│   ├── eval_results.json         Batch run results
│   └── judge_results.json        Judge alignment results
│
├── tests/
│   ├── test_agent.py             Deterministic agent tests
│   ├── test_judge.py             LLM-judge tests
│   └── judge.py                  Judge helper
│
├── data/
│   ├── recipes.json              201 TheMealDB recipes
│   ├── asian_recipes.json        55 custom Asian recipes
│   ├── meal_plan.json            Current weekly plan (gitignored)
│   ├── profile.json              User profile (gitignored)
│   ├── tracking.json             Meal and weight logs (gitignored)
│   └── traces/                   Agent interaction traces (gitignored)
│
├── notebooks/
│   ├── 01-setup.ipynb
│   ├── 02-rag.ipynb
│   └── 03-agent.ipynb
│
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```
