import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    backtest,
    chips,
    fixtures,
    fpl_live,
    operations,
    planner,
    players,
    predictions,
)
from fpl_intelligence.artifact_contract import validate_current_artifacts

app = FastAPI(title="FPL Intelligence API")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("FPL_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(players.router)
app.include_router(fixtures.router)
app.include_router(predictions.router)
app.include_router(planner.router)
app.include_router(fpl_live.router)
app.include_router(backtest.router)
app.include_router(chips.router)
app.include_router(operations.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/readiness")
def readiness() -> dict[str, Any]:
    return validate_current_artifacts(check_models=True).to_dict()
