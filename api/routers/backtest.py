from typing import Any

from fastapi import APIRouter

from api import data_service

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

MODEL_NAME_MAP = {
    "Gradient Boosting Regressor": "SquadMetric",
    "Random Forest Regressor": "Random forest",
    "Ridge Regression": "Ridge regression",
    "Naive baseline": "Form average",
    "gradient_boosting": "SquadMetric",
    "random_forest": "Random forest",
    "ridge": "Ridge regression",
    "naive_baseline": "Form average",
}


@router.get("/accuracy")
def accuracy() -> list[dict[str, Any]]:
    raw = data_service.raw_accuracy()
    adjusted = data_service.adjusted_accuracy()
    if raw.empty and adjusted.empty:
        return []

    raw = raw.rename(
        columns={
            "MAE": "raw_MAE",
            "RMSE": "raw_RMSE",
            "beats_naive_MAE": "raw_beats_naive_MAE",
            "beats_naive_RMSE": "raw_beats_naive_RMSE",
        }
    )
    adjusted = adjusted.rename(
        columns={
            "MAE": "adjusted_MAE",
            "RMSE": "adjusted_RMSE",
            "beats_naive_MAE": "adjusted_beats_naive_MAE",
            "beats_naive_RMSE": "adjusted_beats_naive_RMSE",
        }
    )
    merged = raw.merge(adjusted, on="model", how="outer")
    merged["model"] = merged["model"].map(_plain_model_name).fillna(merged["model"])
    return data_service.to_records(merged)


@router.get("/captaincy")
def captaincy() -> list[dict[str, Any]]:
    dataframe = data_service.captaincy_backtest()
    if dataframe.empty:
        return []

    dataframe["strategy"] = dataframe["strategy"].map(_plain_strategy_name)
    return data_service.to_records(dataframe)


@router.get("/top10")
def top10() -> list[dict[str, Any]]:
    dataframe = data_service.top10_metrics()
    if dataframe.empty:
        return []

    dataframe["model"] = dataframe["model"].map(_plain_model_name).fillna(dataframe["model"])
    return data_service.to_records(dataframe)


def _plain_model_name(model: str) -> str:
    return MODEL_NAME_MAP.get(model, model)


def _plain_strategy_name(strategy: str) -> str:
    lowered = strategy.lower()
    if "ridge" in lowered:
        # Ridge is the captain model in the active production portfolio.
        return "SquadMetric"
    if "gradient boosting" in lowered:
        return "Gradient boosting"
    if "random forest" in lowered:
        return "Random forest"
    if "naive" in lowered:
        return "Form average"
    if "most-owned" in lowered or "most owned" in lowered:
        return "Most popular player"
    if "highest prior rolling ppg" in lowered or "highest_ppg" in lowered:
        return "Best points-per-game"
    if "random" in lowered:
        return "Random pick"
    return strategy
