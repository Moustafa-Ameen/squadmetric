FROM mirror.gcr.io/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FPL_ACTIVE_SEASON=2026-27

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# An editable install keeps package paths rooted at /app/src. Several artifact
# contracts deliberately derive the repository root from their source location.
RUN pip install --no-cache-dir -e .

COPY api ./api
COPY data/raw/bootstrap-static.json data/raw/fixtures.json ./data/raw/
COPY data/processed ./data/processed
COPY data/reference ./data/reference
COPY models ./models

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
