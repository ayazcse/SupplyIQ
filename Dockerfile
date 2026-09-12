# SupplyIQ — Application container
# Builds an image that can run either the FastAPI backend or the Streamlit app,
# selected via the CMD override in docker-compose.yml.
FROM python:3.12-slim

WORKDIR /app

# System deps for lightgbm (libgomp) and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/raw /app/data/processed /app/data/synthetic /app/database /app/logs

EXPOSE 8000 8501

# Default: run the full pipeline once, then serve the API.
# Override this command in docker-compose.yml to run Streamlit instead.
CMD ["sh", "-c", "python scripts/run_pipeline.py && uvicorn src.api.main:app --host 0.0.0.0 --port 8000"]
