"""Multi-gameweek projections for the guided transfer planner.

The planner holds each player's current rolling minutes/points features and
ownership constant across the horizon. Fixture opponent, venue, and opponent
strength are refreshed for every target gameweek. This is an intentional
near-term planning simplification: projections assume current form and role
continue, while fixture context changes week by week.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from fpl_intelligence.fixture_scenarios import FixtureScenario
from fpl_intelligence.live_model_training import (
    LIVE_GRADIENT_MODEL_PATH,
    LIVE_MINUTES_BAND_MODEL_PATH,
    LIVE_RIDGE_MODEL_PATH,
)
from fpl_intelligence.scoring_regime_adjustment import bps_v2_adjustment
from fpl_intelligence.set_piece_intelligence import (
    SetPieceContext,
    build_set_piece_context,
    set_piece_transition_adjustment,
)

ALLOWED_HORIZONS = (3, 5, 8)
MODEL_NAME = "Gradient Boosting Regressor"
MODEL_PATHS = {
    "Ridge Regression": LIVE_RIDGE_MODEL_PATH,
    "Gradient Boosting Regressor": LIVE_GRADIENT_MODEL_PATH,
}
RECENT_WINDOW = 3


@lru_cache(maxsize=4)
def load_planner_models(model_name: str = MODEL_NAME):
    """Load a consumer-specific, current-season points/minutes artifact pair."""

    points_path = MODEL_PATHS.get(model_name)
    if points_path is None:
        allowed = ", ".join(sorted(MODEL_PATHS))
        raise ValueError(f"Unknown planner model {model_name!r}; choose from {allowed}")
    missing = (
        [str(points_path)]
        if not Path(points_path).exists()
        else []
    )
    if not Path(LIVE_MINUTES_BAND_MODEL_PATH).exists():
        missing.append(str(LIVE_MINUTES_BAND_MODEL_PATH))
    if missing:
        raise FileNotFoundError(f"Planner model artifacts are missing: {', '.join(missing)}")

    try:
        return joblib.load(points_path), joblib.load(LIVE_MINUTES_BAND_MODEL_PATH)
    except (AttributeError, ImportError, ModuleNotFoundError, ValueError) as exc:
        raise RuntimeError(
            f"Planner model artifacts could not be loaded for {model_name}: {exc}"
        ) from exc


def project_player(
    player_id_or_name: int | str,
    start_gameweek: int,
    horizon_length: int,
    players: Iterable[dict[str, Any]],
    fixtures: Iterable[dict[str, Any]],
    teams: Iterable[dict[str, Any]],
    models=None,
    history: pd.DataFrame | None = None,
    fixture_scenario: FixtureScenario | None = None,
) -> list[dict[str, Any]]:
    """Return per-gameweek projections for one player.

    ``players`` contains current player records, ``fixtures`` contains FPL
    fixture rows, and ``teams`` contains bootstrap team strength metadata.
    Blank gameweeks return zero; two fixtures in the same gameweek are summed.
    """
    if horizon_length not in ALLOWED_HORIZONS:
        raise ValueError(f"horizon_length must be one of {ALLOWED_HORIZONS}")

    player_rows = list(players)
    set_piece_context = build_set_piece_context(player_rows)
    player = _find_player(player_id_or_name, player_rows)
    return _project_row(
        player,
        start_gameweek,
        horizon_length,
        list(fixtures),
        list(teams),
        models=models,
        history=history,
        fixture_scenario=fixture_scenario,
        set_piece_context=set_piece_context,
    )


def project_players(
    players: Iterable[dict[str, Any]],
    fixtures: Iterable[dict[str, Any]],
    teams: Iterable[dict[str, Any]],
    start_gameweek: int,
    horizon_length: int,
    models=None,
    history: pd.DataFrame | None = None,
    fixture_scenario: FixtureScenario | None = None,
) -> list[dict[str, Any]]:
    """Project all supplied players over a 3, 5, or 8 gameweek horizon."""
    if horizon_length not in ALLOWED_HORIZONS:
        raise ValueError(f"horizon_length must be one of {ALLOWED_HORIZONS}")

    player_rows = list(players)
    fixture_rows = (
        list(fixture_scenario.fixtures)
        if fixture_scenario is not None
        else list(fixtures)
    )
    team_by_id = {team.get("id"): team for team in teams}
    points_model, minutes_model = models or load_planner_models()
    baselines = _recent_baselines(history)
    set_piece_context = build_set_piece_context(player_rows)
    projections = [{**player, "projections": []} for player in player_rows]

    # Batch each GW's fixture rows so the sklearn preprocessing pipeline runs
    # a few times per GW instead of once for every player-fixture pair.
    for gameweek in range(start_gameweek, start_gameweek + horizon_length):
        pending: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        fixture_groups: dict[int, list[dict[str, Any]]] = {}
        for index, player in enumerate(player_rows):
            player_fixtures = _fixtures_for_player(player, gameweek, fixture_rows, team_by_id)
            if not player_fixtures:
                projections[index]["projections"].append(
                    _gameweek_metadata(
                        {
                            "gameweek": gameweek,
                            "projected_points": 0.0,
                            "blank": True,
                            "double": False,
                            "fixtures": [],
                        },
                        fixture_scenario,
                    )
                )
                continue

            baseline = _baseline_for_player(player, baselines)
            fixture_groups[index] = []
            for fixture in player_fixtures:
                fixture_groups[index].append(fixture)
                pending.append((index, _feature_row(player, fixture, baseline), fixture))

        if not pending:
            continue

        feature_frame = pd.DataFrame([item[1] for item in pending])
        predicted_points, projected_points, start_likelihoods = _projected_values(
            points_model, minutes_model, feature_frame
        )
        fixture_results: dict[int, list[dict[str, Any]]] = {index: [] for index in fixture_groups}
        for pending_item, predicted, projected, start_likelihood in zip(
            pending, predicted_points, projected_points, start_likelihoods, strict=True
        ):
            index, _, fixture = pending_item
            predicted_value = max(0.0, float(predicted))
            model_start = max(0.0, min(1.0, float(start_likelihood)))
            start_value = _live_start_likelihood(
                model_start,
                player_rows[index],
                _baseline_for_player(player_rows[index], baselines),
            )
            projected_value = _rescale_projected_points(
                predicted_value,
                max(0.0, float(projected)),
                model_start,
                start_value,
            )
            regime = bps_v2_adjustment(
                player_rows[index],
                _baseline_for_player(player_rows[index], baselines),
            )
            projected_value = max(0.0, projected_value - regime.total_penalty * start_value)
            set_piece = set_piece_transition_adjustment(
                player_rows[index], set_piece_context
            )
            projected_value = max(
                0.0,
                projected_value + set_piece.total_adjustment * start_value,
            )
            fixture_results[index].append(
                {
                    "opponent": fixture["opponent"],
                    "opponent_name": fixture["opponent_name"],
                    "home": fixture["home"],
                    "opponent_difficulty": fixture["opponent_difficulty"],
                    "opponent_strength": fixture["opponent_strength"],
                    "predicted_points": round(predicted_value, 2),
                    "start_likelihood": round(start_value, 4),
                    "projected_points": round(projected_value, 2),
                    "scoring_regime_adjustment": regime.to_dict(),
                    "set_piece_adjustment": set_piece.to_dict(),
                    **_fixture_metadata(fixture),
                }
            )

        for index, fixture_projections in fixture_results.items():
            projections[index]["projections"].append(
                _gameweek_metadata(
                    {
                        "gameweek": gameweek,
                        "projected_points": round(
                            sum(fixture["projected_points"] for fixture in fixture_projections), 2
                        ),
                        "blank": False,
                        "double": len(fixture_projections) > 1,
                        "fixtures": fixture_projections,
                    },
                    fixture_scenario,
                )
            )

    return projections


def _project_row(
    player: dict[str, Any],
    start_gameweek: int,
    horizon_length: int,
    fixtures: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    models=None,
    history: pd.DataFrame | None = None,
    fixture_scenario: FixtureScenario | None = None,
    set_piece_context: SetPieceContext | None = None,
) -> list[dict[str, Any]]:
    points_model, minutes_model = models or load_planner_models()
    projection_fixtures = (
        list(fixture_scenario.fixtures)
        if fixture_scenario is not None
        else fixtures
    )
    team_by_id = {team.get("id"): team for team in teams}
    baselines = _recent_baselines(history)
    baseline = _baseline_for_player(player, baselines)
    role_context = set_piece_context or build_set_piece_context([player])

    output = []
    for gameweek in range(start_gameweek, start_gameweek + horizon_length):
        player_fixtures = _fixtures_for_player(
            player, gameweek, projection_fixtures, team_by_id
        )
        if not player_fixtures:
            output.append(
                _gameweek_metadata(
                    {
                        "gameweek": gameweek,
                        "projected_points": 0.0,
                        "blank": True,
                        "double": False,
                        "fixtures": [],
                    },
                    fixture_scenario,
                )
            )
            continue

        fixture_projections = []
        for fixture in player_fixtures:
            features = _feature_row(player, fixture, baseline)
            feature_frame = pd.DataFrame([features])
            predicted_points, projected_points, start_likelihood = _projected_values(
                points_model, minutes_model, feature_frame
            )
            predicted_points = max(0.0, float(predicted_points[0]))
            model_start = max(0.0, min(1.0, float(start_likelihood[0])))
            start_likelihood = _live_start_likelihood(model_start, player, baseline)
            projected_points = _rescale_projected_points(
                predicted_points,
                max(0.0, float(projected_points[0])),
                model_start,
                start_likelihood,
            )
            regime = bps_v2_adjustment(player, baseline)
            projected_points = max(
                0.0, projected_points - regime.total_penalty * start_likelihood
            )
            set_piece = set_piece_transition_adjustment(player, role_context)
            projected_points = max(
                0.0,
                projected_points + set_piece.total_adjustment * start_likelihood,
            )
            fixture_projections.append(
                {
                    "opponent": fixture["opponent"],
                    "opponent_name": fixture["opponent_name"],
                    "home": fixture["home"],
                    "opponent_difficulty": fixture["opponent_difficulty"],
                    "opponent_strength": fixture["opponent_strength"],
                    "predicted_points": round(predicted_points, 2),
                    "start_likelihood": round(start_likelihood, 4),
                    "projected_points": round(projected_points, 2),
                    "scoring_regime_adjustment": regime.to_dict(),
                    "set_piece_adjustment": set_piece.to_dict(),
                    **_fixture_metadata(fixture),
                }
            )

        output.append(
            _gameweek_metadata(
                {
                    "gameweek": gameweek,
                    "projected_points": round(
                        sum(fixture["projected_points"] for fixture in fixture_projections), 2
                    ),
                    "blank": False,
                    "double": len(fixture_projections) > 1,
                    "fixtures": fixture_projections,
                },
                fixture_scenario,
            )
        )

    return output


def _projected_values(points_model: Any, minutes_model: Any, features: pd.DataFrame):
    """Return raw points, adjusted points, and 60+ likelihood.

    The fallback keeps pre-M2 binary artifacts usable.  New M2 artifacts expose
    ``predict_expected_points`` and therefore calculate the full three-band
    conditional expectation.
    """
    predicted_points = points_model.predict(features)
    if hasattr(minutes_model, "predict_expected_points"):
        projected_points = minutes_model.predict_expected_points(features)
        start_likelihoods = np.asarray(minutes_model.predict_proba(features))[:, 2]
    else:
        start_likelihoods = np.asarray(minutes_model.predict_proba(features))[:, 1]
        projected_points = predicted_points * start_likelihoods
    return predicted_points, projected_points, start_likelihoods


def _live_start_likelihood(
    model_start: float,
    player: dict[str, Any],
    baseline: dict[str, Any],
) -> float:
    """Blend the historical minutes model with current source-attributed role evidence."""

    prior_raw = player.get("start_likelihood")
    if prior_raw is None:
        blended = model_start
    else:
        prior = max(0.0, min(1.0, _number(prior_raw)))
        source = str(player.get("prior_source") or "")
        if source.startswith("launch_evidence:"):
            prior_weight = 0.85
        elif source == "new_player_position_prior" or not baseline:
            prior_weight = 0.75
        else:
            prior_weight = 0.35
        blended = prior_weight * prior + (1.0 - prior_weight) * model_start

    availability_raw = player.get("availability_probability")
    availability = (
        max(0.0, min(1.0, _number(availability_raw)))
        if availability_raw is not None
        else 1.0
    )
    return max(0.0, min(1.0, blended, availability))


def _rescale_projected_points(
    predicted_points: float,
    model_projected_points: float,
    model_start: float,
    live_start: float,
) -> float:
    if live_start <= 0:
        return 0.0
    if model_start > 0.05:
        adjusted = model_projected_points * live_start / model_start
    else:
        adjusted = predicted_points * live_start
    # The role overlay may correct availability, but must not manufacture an
    # extreme ceiling from a near-zero model denominator.
    return max(0.0, min(adjusted, predicted_points * 1.15))


def _feature_row(
    player: dict[str, Any], fixture: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    return {
        # Live bootstrap values are fetched before the upcoming deadline, so they
        # already represent the model's pre-deadline market features. Historical
        # rows use the explicitly lagged equivalents built in historical_data.py.
        "price_before_deadline": _number(
            player.get("price_before_deadline", player.get("price"))
        ),
        "minutes_last_3": _number(player.get("minutes_last_3", baseline.get("minutes_last_3", 0))),
        "points_last_3": _number(player.get("points_last_3", baseline.get("points_last_3", 0))),
        "opponent_strength": _number(fixture.get("opponent_strength")),
        "selected_by_percent_before_deadline": _number(
            player.get("selected_by_percent_before_deadline", player.get("selected_by_percent"))
        ),
        "market_snapshot_available": _number(player.get("market_snapshot_available", 1)),
        "position": _position_code(player.get("position")),
        "home_or_away": "H" if fixture.get("home") else "A",
    }


def _fixtures_for_player(
    player: dict[str, Any],
    gameweek: int,
    fixtures: list[dict[str, Any]],
    team_by_id: dict[Any, dict[str, Any]],
) -> list[dict[str, Any]]:
    team_id = player.get("team_id", player.get("team"))
    rows = []
    for fixture in fixtures:
        if fixture.get("event") != gameweek:
            continue

        if fixture.get("team_h") == team_id:
            opponent_id = fixture.get("team_a")
            opponent = team_by_id.get(opponent_id, {})
            raw_strength = fixture.get(
                "opponent_strength", opponent.get("strength_overall_away")
            )
            rows.append(
                {
                    "fixture_id": fixture.get("fixture_id", fixture.get("id")),
                    "opponent": opponent.get("short_name") or fixture.get("team_a_short", "-"),
                    "opponent_name": opponent.get("name") or fixture.get("team_a_name", "Unknown"),
                    "home": True,
                    "opponent_difficulty": _fpl_difficulty(raw_strength),
                    "opponent_strength": _model_opponent_strength(raw_strength),
                    **_fixture_metadata(fixture),
                }
            )
        elif fixture.get("team_a") == team_id:
            opponent_id = fixture.get("team_h")
            opponent = team_by_id.get(opponent_id, {})
            raw_strength = fixture.get(
                "opponent_strength", opponent.get("strength_overall_home")
            )
            rows.append(
                {
                    "fixture_id": fixture.get("fixture_id", fixture.get("id")),
                    "opponent": opponent.get("short_name") or fixture.get("team_h_short", "-"),
                    "opponent_name": opponent.get("name") or fixture.get("team_h_name", "Unknown"),
                    "home": False,
                    "opponent_difficulty": _fpl_difficulty(raw_strength),
                    "opponent_strength": _model_opponent_strength(raw_strength),
                    **_fixture_metadata(fixture),
                }
            )

    return rows


def _fixture_metadata(fixture: dict[str, Any]) -> dict[str, Any]:
    keys = ("status", "confirmed", "postponed", "rescheduled")
    return {key: fixture[key] for key in keys if key in fixture}


def _model_opponent_strength(value: Any) -> float:
    """Map the live 1-5 FDR scale onto the historical model's strength scale."""

    raw = _number(value)
    if raw <= 0:
        return 1150.0
    if raw <= 5:
        return 925.0 + 75.0 * raw
    return raw


def _fpl_difficulty(value: Any) -> int | None:
    raw = _number(value)
    if 1 <= raw <= 5:
        return int(raw)
    return None


def _gameweek_metadata(
    row: dict[str, Any], fixture_scenario: FixtureScenario | None
) -> dict[str, Any]:
    if fixture_scenario is None:
        return row
    return {**row, **fixture_scenario.metadata()}


def _recent_baselines(history: pd.DataFrame | None) -> dict[Any, dict[str, Any]]:
    if history is None or history.empty:
        return {}

    required = {"season", "gameweek", "minutes"}
    if not required.issubset(history.columns):
        return {}

    current = history.copy()
    if "total_points" not in current.columns:
        if "next_gameweek_points" not in current.columns:
            return {}
        current["total_points"] = current["next_gameweek_points"]
    elif "next_gameweek_points" in current.columns:
        current["total_points"] = current["total_points"].fillna(
            current["next_gameweek_points"]
        )
    current["gameweek"] = pd.to_numeric(current["gameweek"], errors="coerce")
    current["total_points"] = pd.to_numeric(current["total_points"], errors="coerce")
    current["minutes"] = pd.to_numeric(current["minutes"], errors="coerce")
    current = current.dropna(subset=["season", "gameweek", "total_points", "minutes"])
    if current.empty:
        return {}

    current = current[current["season"] == current["season"].max()].sort_values("gameweek")
    output: dict[Any, dict[str, Any]] = {}
    if "player_name" in current.columns:
        current["player_key"] = current["player_name"].map(_normalise)
        recent = (
            current[current["player_key"] != ""]
            .groupby("player_key", sort=False)
            .tail(RECENT_WINDOW)
        )
        for player_name, rows in recent.groupby("player_key"):
            baseline = {
                "minutes_last_3": float(rows["minutes"].sum()),
                "points_last_3": float(rows["total_points"].sum()),
                "prior_team": str(rows.iloc[-1].get("team") or ""),
                "source_season": str(rows.iloc[-1]["season"]),
                "latest_gameweek": int(rows["gameweek"].max()),
            }
            output[("name", player_name)] = baseline

        id_column = next(
            (column for column in ("player_id", "element_id") if column in current.columns),
            None,
        )
        if id_column is not None:
            current[id_column] = pd.to_numeric(current[id_column], errors="coerce")
            id_rows = current.dropna(subset=[id_column]).copy()
            id_rows[id_column] = id_rows[id_column].astype(int)
            recent_by_id = id_rows.groupby(id_column, sort=False).tail(RECENT_WINDOW)
            for player_id, rows in recent_by_id.groupby(id_column):
                output[("id", int(player_id))] = {
                    "minutes_last_3": float(rows["minutes"].sum()),
                    "points_last_3": float(rows["total_points"].sum()),
                    "prior_team": str(rows.iloc[-1].get("team") or ""),
                    "source_season": str(rows.iloc[-1]["season"]),
                    "latest_gameweek": int(rows["gameweek"].max()),
                }

    return output


def _baseline_for_player(
    player: dict[str, Any], baselines: dict[Any, dict[str, Any]]
) -> dict[str, Any]:
    """Resolve by season-local FPL ID, then by cross-season player name.

    FPL element IDs are stable only within a season. At an opening deadline,
    current-season history can be empty, so an equal numeric ID from the prior
    season must never be treated as the same player.
    """

    raw_id = player.get("element_id", player.get("id"))
    try:
        player_id = int(raw_id)
    except (TypeError, ValueError):
        player_id = None
    id_baseline = baselines.get(("id", player_id)) if player_id is not None else None
    player_season = str(player.get("season") or "").strip()
    if id_baseline is not None and (
        not player_season
        or not id_baseline.get("source_season")
        or str(id_baseline["source_season"]) == player_season
    ):
        return id_baseline
    return baselines.get(("name", _normalise(player.get("name"))), {})


def _find_player(player_id_or_name: int | str, players: list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(player_id_or_name, int):
        match = next(
            (
                player
                for player in players
                if player.get("element_id", player.get("id")) == player_id_or_name
            ),
            None,
        )
    else:
        key = _normalise(player_id_or_name)
        match = next((player for player in players if _normalise(player.get("name")) == key), None)

    if match is None:
        raise KeyError(f"Player not found: {player_id_or_name}")
    return match


def _position_code(position: Any) -> str:
    return {
        "Goalkeeper": "GK",
        "GKP": "GK",
        "Defender": "DEF",
        "Midfielder": "MID",
        "Forward": "FWD",
    }.get(str(position), str(position))


def _normalise(value: Any) -> str:
    return str(value or "").strip().casefold()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
