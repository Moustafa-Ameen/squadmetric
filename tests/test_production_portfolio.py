import pytest

from fpl_intelligence import production_portfolio
from fpl_intelligence.live_model_training import LIVE_RIDGE_MODEL_PATH
from fpl_intelligence.multi_gw_projection import MODEL_PATHS, load_planner_models


def test_default_portfolio_uses_validated_r2_consumer_assignments(monkeypatch):
    monkeypatch.delenv(production_portfolio.PORTFOLIO_ENV_VAR, raising=False)

    active = production_portfolio.get_production_portfolio()

    assert active.mode == "r2_validated"
    assert active.projections.transfer_model == "Ridge Regression"
    assert active.projections.captain_model == "Ridge Regression"
    assert active.projections.chip_model == "Gradient Boosting Regressor"
    assert active.projections.lineup_model == "Ridge Regression"


def test_control_portfolio_is_explicit_and_reversible():
    active = production_portfolio.get_production_portfolio("m8_control")

    assert active.version == "m8.6.1-ridge-control-v1"
    assert active.projections.as_dict() == {
        "transfer_model": "Ridge Regression",
        "captain_model": "Ridge Regression",
        "chip_model": "Ridge Regression",
        "lineup_model": "Ridge Regression",
    }


def test_invalid_portfolio_setting_fails_safely():
    with pytest.raises(ValueError, match="Unknown production portfolio"):
        production_portfolio.get_production_portfolio("unknown")


@pytest.mark.requires_local_artifacts
def test_planner_model_loader_selects_requested_consumer_artifact(monkeypatch):
    loaded_paths = []
    monkeypatch.setattr(
        "fpl_intelligence.multi_gw_projection.joblib.load",
        lambda path: loaded_paths.append(path) or object(),
    )
    load_planner_models.cache_clear()

    load_planner_models("Ridge Regression")

    assert loaded_paths[0] == LIVE_RIDGE_MODEL_PATH
    assert MODEL_PATHS["Gradient Boosting Regressor"] != LIVE_RIDGE_MODEL_PATH
    load_planner_models.cache_clear()
