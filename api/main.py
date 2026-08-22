import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.readiness import live_decision_context
from api.routers import (
    backtest,
    chips,
    fixtures,
    fpl_live,
    operations,
    planner,
    players,
    predictions,
    review,
)

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
app.include_router(review.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/readiness")
async def readiness() -> dict[str, Any]:
    decision_readiness, _, _ = await live_decision_context(check_models=True)
    return decision_readiness.to_dict()
