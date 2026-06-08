FROM python:3.13-slim

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev extras, no cache to keep image small)
RUN uv sync --frozen --no-dev --no-cache

# Copy source code
COPY *.py ./
COPY data/recipes.json data/recipes.json
COPY data/asian_recipes.json data/asian_recipes.json

# Create directories for runtime data
RUN mkdir -p data/traces

# Streamlit runs on 8501
EXPOSE 8501

# Streamlit config: disable the welcome page and CORS for Docker
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

CMD ["uv", "run", "streamlit", "run", "app.py"]
