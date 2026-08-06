"""Explicit, reversible model routing for live recommendations."""

from __future__ import annotations

import os
from dataclasses import dataclass

from fpl_intelligence.projection_portfolio import ProjectionPortfolio

PORTFOLIO_ENV_VAR = "FPL_PRODUCTION_PORTFOLIO"
DEFAULT_PORTFOLIO_MODE = "r2_validated"


@dataclass(frozen=True)
class ProductionPortfolio:
    """A named live-routing configuration with a stable version identifier."""

    mode: str
    version: str
    projections: ProjectionPortfolio


PORTFOLIOS = {
    "r2_validated": ProductionPortfolio(
        mode="r2_validated",
        version="r2-consumer-portfolio-v1",
        projections=ProjectionPortfolio(
            transfer_model="Ridge Regression",
            captain_model="Ridge Regression",
            chip_model="Gradient Boosting Regressor",
            lineup_model="Ridge Regression",
        ),
    ),
    "m8_control": ProductionPortfolio(
        mode="m8_control",
        version="m8.6.1-ridge-control-v1",
        projections=ProjectionPortfolio(
            transfer_model="Ridge Regression",
            captain_model="Ridge Regression",
            chip_model="Ridge Regression",
            lineup_model="Ridge Regression",
        ),
    ),
}


def get_production_portfolio(mode: str | None = None) -> ProductionPortfolio:
    """Return the explicitly selected live portfolio or fail safely."""

    selected = str(mode or os.getenv(PORTFOLIO_ENV_VAR) or DEFAULT_PORTFOLIO_MODE)
    try:
        return PORTFOLIOS[selected]
    except KeyError as exc:
        allowed = ", ".join(sorted(PORTFOLIOS))
        raise ValueError(
            f"Unknown production portfolio {selected!r}; choose from {allowed}"
        ) from exc
