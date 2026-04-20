FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY src ./src
COPY docs ./docs

RUN pip install --no-cache-dir .

CMD exec uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8080}
