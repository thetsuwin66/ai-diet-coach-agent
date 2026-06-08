.PHONY: install run test eval judge label docker-build docker-up docker-down help

help:
	@echo "Available commands:"
	@echo "  make install       Install dependencies with uv"
	@echo "  make run           Start the Streamlit app"
	@echo "  make test          Run the test suite"
	@echo "  make eval          Run batch evaluation (60 scenarios)"
	@echo "  make judge         Run LLM judge and print alignment metrics"
	@echo "  make label         Open the Streamlit labeling tool"
	@echo "  make docker-build  Build the Docker image"
	@echo "  make docker-up     Start the app with docker compose"
	@echo "  make docker-down   Stop docker compose services"

install:
	uv sync

run:
	uv run streamlit run app.py

test:
	uv run pytest tests/ -v

eval:
	uv run python evals/run_evals.py

judge:
	uv run python evals/eval_judge.py

label:
	uv run streamlit run evals/label_evals.py --server.port 8502

docker-build:
	docker build -t ai-diet-coach .

docker-up:
	docker compose up --build

docker-down:
	docker compose down
