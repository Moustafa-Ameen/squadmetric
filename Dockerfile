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
COPY data/processed/current_artifact_manifest.json \
    data/processed/current_availability_events.json \
    data/processed/live_2026_27_player_gw.csv \
    data/processed/players_current.csv \
    data/processed/players_ranked.csv \
    ./data/processed/
COPY data/processed/rules ./data/processed/rules
COPY data/reference ./data/reference
COPY models/live_2026_27_gradient_points.joblib \
    models/live_2026_27_minutes_band.joblib \
    models/live_2026_27_minutes_binary.joblib \
    models/live_2026_27_models.json \
    models/live_2026_27_ridge_points.joblib \
    ./models/

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
