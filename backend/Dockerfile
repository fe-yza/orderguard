FROM python:3.12-slim AS base

WORKDIR /app

# System deps for psycopg (binary wheel avoids needing libpq-dev, but
# build-essential covers us if that ever changes) and to keep the image
# minimal otherwise.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

COPY tests ./tests

EXPOSE 8000

# Migrations run before the app starts — this is what makes `docker compose
# up` produce a working schema with no manual step, per the Milestone 9
# requirement. Idempotent: alembic upgrade is a no-op if already current.
CMD ["sh", "-c", "alembic upgrade head && uvicorn orderguard.api.app:app --host 0.0.0.0 --port 8000"]
