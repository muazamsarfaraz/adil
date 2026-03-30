# Stage 1 — Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2 — Runtime
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8001

# SERVICE_ROLE controls what this container runs:
#   "worker" → arq worker (no HTTP, no healthcheck)
#   anything else → alembic migrations + uvicorn API server
ENV SERVICE_ROLE=api

CMD ["sh", "-c", "if [ \"$SERVICE_ROLE\" = 'worker' ]; then echo 'Starting arq worker...' && arq app.workers.settings.WorkerSettings; else alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}; fi"]
