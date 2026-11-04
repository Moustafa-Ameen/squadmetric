import numpy as np
import pandas as pd

from squadmetric.fixture_adjustment import (
    FixtureMultipliers,
    add_point_in_time_opponent_strength,
    fit_fixture_multipliers,
)
from squadmetric.season_benchmark import _with_fixture_multipliers


def _training_rows(count: int = 20000) -> pd.DataFrame:
    rng = np.random.default_rng(4)
    home = rng.random(count) < 0.5
    strength = rng.uniform(-2, 2, count)
    base = rng.uniform(2, 6, count)
    # Forwards score far more at home against weak opponents than an additive model allows.
    points = base * (1 + 0.25 * home - 0.15 * strength) + rng.normal(0, 0.5, count)
    # Most rows are fringe players with no fixture effect, as in real data, which is
    # what flattens the shared additive coefficients.
    fringe = rng.random(count) < 0.7
    points = np.where(fringe, rng.uniform(0, 1, count), points)
    return pd.DataFrame(
        {
            "price_before_deadline": base * 2,
            "minutes_last_3": np.where(fringe, 0.0, 270.0),
            "points_last_3": base * 3,
            "opponent_strength": strength,
            "selected_by_percent_before_deadline": 10.0,
            "market_snapshot_available": 1,
            "position": "FWD",
            "home_or_away": np.where(home, "H", "A"),
            "next_gameweek_points": points,
        }
    )


def test_multipliers_favour_home_games_against_weak_opponents():
    multipliers = fit_fixture_multipliers(_training_rows())

    best = multipliers.multiplier("FWD", "H", -2.0)
    worst = multipliers.multiplier("FWD", "A", 2.0)

    assert best > 1.0 > worst
    assert 0.8 <= worst and best <= 1.25


def test_too_little_history_and_unknown_fixtures_change_nothing():
    empty = fit_fixture_multipliers(_training_rows(100))
    fitted = fit_fixture_multipliers(_training_rows())

    assert empty.table == {}
    assert empty.multiplier("FWD", "H", -2.0) == 1.0
    assert fitted.multiplier("FWD", "M", -2.0) == 1.0
    assert fitted.multiplier("FWD", "H", None) == 1.0


def test_scaling_applies_each_players_own_fixture_without_changing_the_input():
    multipliers = FixtureMultipliers(
        low_strength=-1.0,
        high_strength=1.0,
        table={"FWD|H|easy": 1.2, "FWD|A|hard": 0.9},
    )
    frame = pd.DataFrame(
        {
            "player_id": [1, 2, 3],
            "position": ["FWD", "FWD", "FWD"],
            "expected_points_adjusted": [5.0, 5.0, 5.0],
        }
    )
    context = {(4, 1): ("H", -2.0), (4, 2): ("A", 2.0)}

    scaled = _with_fixture_multipliers(frame, 4, multipliers, context)

    assert scaled["expected_points_adjusted"].tolist() == [6.0, 4.5, 5.0]
    assert frame["expected_points_adjusted"].tolist() == [5.0, 5.0, 5.0]


def _strength_rows() -> pd.DataFrame:
    rows = []
    for season, final in (("2024-25", 1200.0), ("2025-26", 1300.0)):
        for gameweek in (1, 2, 3):
            rows.append(
                {
                    "season": season,
                    "gameweek": gameweek,
                    "team": "Arsenal",
                    "opponent_team": "Hull",
                    "home_or_away": "H",
                    "team_goals": 0,
                    "opponent_goals": 3,
                    "opponent_strength": final,
                }
            )
            rows.append(
                {
                    "season": season,
                    "gameweek": gameweek,
                    "team": "Hull",
                    "opponent_team": "Arsenal",
                    "home_or_away": "A",
                    "team_goals": 3,
                    "opponent_goals": 0,
                    "opponent_strength": final - 100,
                }
            )
    return pd.DataFrame(rows)


def test_point_in_time_strength_ignores_the_seasons_own_rating_and_later_results():
    rows = _strength_rows()

    rebuilt = add_point_in_time_opponent_strength(rows)
    hull = rebuilt[(rebuilt["season"] == "2025-26") & (rebuilt["opponent_team"] == "Hull")]
    by_gameweek = hull.set_index("gameweek")["opponent_strength"]

    assert by_gameweek[1] == 1200.0  # last season's rating, not this season's 1300
    assert by_gameweek[2] > by_gameweek[1]  # Hull won its first match

    changed = rows.copy()
    later = changed["gameweek"] >= 2
    changed.loc[later, ["team_goals", "opponent_goals"]] = 0
    changed.loc[changed["season"] == "2025-26", "opponent_strength"] = 999.0
    rebuilt_changed = add_point_in_time_opponent_strength(changed)
    same_row = rebuilt_changed[
        (rebuilt_changed["season"] == "2025-26")
        & (rebuilt_changed["opponent_team"] == "Hull")
        & (rebuilt_changed["gameweek"] == 2)
    ]
    assert same_row["opponent_strength"].iloc[0] == by_gameweek[2]
