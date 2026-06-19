FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.5

COPY pyproject.toml ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY . .

RUN mkdir -p wiki/sources wiki/concepts wiki/entities wiki/synthesis raw

EXPOSE 8080

CMD ["python", "-m", "app.web"]
