import pytest

from fpl_intelligence.projection_portfolio import ProjectionPortfolio
from fpl_intelligence.season_benchmark import (
    train_gameweek_predictions,
    train_realistic_captain_predictions,
)
from fpl_intelligence.step4_models import load_historical_player_gameweeks


def test_projection_portfolio_keeps_consumers_explicit():
    portfolio = ProjectionPortfolio(
        transfer_model="Gradient Boosting Regressor",
        captain_model="Ridge Regression",
        chip_model="Ridge Regression",
        lineup_model="Gradient Boosting Regressor",
    )

    assert portfolio.model_for("transfer") == "Gradient Boosting Regressor"
    assert portfolio.model_for("captain") == "Ridge Regression"
    assert portfolio.model_for("chip") == "Ridge Regression"
    assert portfolio.model_for("lineup") == "Gradient Boosting Regressor"


def test_projection_portfolio_allows_experimental_chip_model_override():
    portfolio = ProjectionPortfolio(
        transfer_model="Ridge Regression",
        captain_model="Ridge Regression",
        chip_model="Gradient Boosting Regressor",
    )

    assert portfolio.model_for("transfer") == "Ridge Regression"
    assert portfolio.model_for("chip") == "Gradient Boosting Regressor"


def test_projection_portfolio_rejects_unknown_consumer():
    with pytest.raises(ValueError, match="Unknown projection consumer"):
        ProjectionPortfolio().model_for("minutes")  # type: ignore[arg-type]


@pytest.mark.requires_local_artifacts
def test_captain_model_override_is_not_silently_replaced_by_ridge():
    players = load_historical_player_gameweeks()
    predictions = train_realistic_captain_predictions(
        players,
        "2024-25",
        10,
        model_name="Gradient Boosting Regressor",
    )

    assert predictions["captain_model"].eq("Gradient Boosting Regressor").all()
    assert predictions["captain_model_name"].eq("Gradient Boosting Regressor").all()


@pytest.mark.requires_local_artifacts
def test_transfer_prediction_model_name_is_preserved():
    players = load_historical_player_gameweeks()
    predictions, _ = train_gameweek_predictions(
        players,
        "2024-25",
        10,
        model_name="Gradient Boosting Regressor",
    )

    assert predictions["model"].eq("Gradient Boosting Regressor").all()
