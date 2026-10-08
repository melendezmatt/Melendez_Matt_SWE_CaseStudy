FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UNIVERSE_FILE=/app/config/universe.yaml \
    SNAPSHOT_DIR=/app/data/snapshot

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[dev]"

COPY config ./config
COPY data ./data
COPY scripts ./scripts
COPY tests ./tests

EXPOSE 8000

# Load the committed snapshot if the database doesn't already hold it (no network needed), then serve.
CMD ["sh", "-c", "python -m tracker.ingest seed --if-changed && exec uvicorn tracker.api:app --host 0.0.0.0 --port 8000"]
