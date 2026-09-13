"""League-wide, non-personalized chip opportunity signals."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

CHIP_LABELS = {
    "3xc": "Triple Captain",
    "bboost": "Bench Boost",
    "freehit": "Free Hit",
    "wildcard": "Wildcard",
}


def build_chip_opportunities(
    bootstrap: Mapping[str, Any],
    fixtures: Sequence[Mapping[str, Any]],
    projected_players: Sequence[Mapping[str, Any]],
    *,
    target_gameweek: int,
) -> list[dict[str, Any]]:
    """Rank public chip windows without reading an individual manager's squad."""

    elements = list(bootstrap.get("elements", []))
    teams = list(bootstrap.get("teams", []))
    raw_by_id = {
        int(row["id"]): row
        for row in elements
        if row.get("id") is not None
    }
    team_by_id = {
        int(row["id"]): row
        for row in teams
        if row.get("id") is not None
    }
    defence = _defence_profiles(elements, team_by_id)
    weeks = sorted(
        {
            int(projection["gameweek"])
            for player in projected_players
            for projection in player.get("projections", [])
            if projection.get("gameweek") is not None
        }
    )
    return [
        _triple_captain_opportunity(
            projected_players,
            raw_by_id,
            team_by_id,
            defence,
            weeks,
        ),
        _bench_boost_opportunity(projected_players, raw_by_id, weeks),
        _free_hit_opportunity(fixtures, team_by_id, weeks),
        _wildcard_opportunity(fixtures, projected_players, team_by_id, weeks),
    ]


def _triple_captain_opportunity(
    projected_players: Sequence[Mapping[str, Any]],
    raw_by_id: Mapping[int, Mapping[str, Any]],
    team_by_id: Mapping[int, Mapping[str, Any]],
    defence: Mapping[str, Mapping[str, Any]],
    weeks: Sequence[int],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for player in projected_players:
        player_id = _integer(player.get("element_id"))
        if player_id is None or str(player.get("position")) not in {"MID", "FWD"}:
            continue
        raw = raw_by_id.get(player_id, {})
        if str(raw.get("status") or "a") in {"i", "s", "u"}:
            continue
        team = team_by_id.get(_integer(player.get("team_id")) or -1, {})
        for projection in player.get("projections", []):
            gameweek = _integer(projection.get("gameweek"))
            if gameweek not in weeks or bool(projection.get("blank")):
                continue
            fixture_rows = list(projection.get("fixtures") or [])
            start = _average(
                [_number(row.get("start_likelihood")) for row in fixture_rows],
                default=0.0,
            )
            opponent_profiles = [
                defence.get(str(row.get("opponent_name") or ""), {})
                for row in fixture_rows
            ]
            opponent_xgc = _average(
                [_number(row.get("xgc_per_90")) for row in opponent_profiles],
                default=0.0,
            )
            opponent_rank = max(
                (_integer(row.get("weakness_rank")) or 0 for row in opponent_profiles),
                default=0,
            )
            candidates.append(
                {
                    "gameweek": gameweek,
                    "player": _player_name(player, raw),
                    "team": str(team.get("name") or player.get("team_name") or "Unknown"),
                    "opponents": [
                        str(row.get("opponent_name") or row.get("opponent") or "Unknown")
                        for row in fixture_rows
                    ],
                    "venue": _venue_label(fixture_rows),
                    "projected_points": round(_number(projection.get("projected_points")), 2),
                    "start_probability": round(start, 3),
                    "xgi_per_90": round(
                        _number(raw.get("expected_goal_involvements_per_90")),
                        2,
                    ),
                    "form": round(_number(raw.get("form")), 2),
                    "opponent_xgc_per_90": round(opponent_xgc, 2),
                    "opponent_weakness_rank": opponent_rank,
                    "double_gameweek": bool(projection.get("double")),
                }
            )
    candidates.sort(
        key=lambda row: (
            row["projected_points"],
            row["start_probability"],
            row["opponent_xgc_per_90"],
        ),
        reverse=True,
    )
    if not candidates:
        return _no_window("3xc", "No reliable Triple Captain candidate is visible yet.")
    best = candidates[0]
    opponents = " and ".join(best["opponents"])
    confidence = _confidence(
        high=best["projected_points"] >= 7.0 and best["start_probability"] >= 0.82,
        medium=best["projected_points"] >= 5.0 and best["start_probability"] >= 0.7,
    )
    return {
        "chip_type": "3xc",
        "chip": CHIP_LABELS["3xc"],
        "recommended_gameweek": best["gameweek"],
        "headline": (
            f"Consider Triple Captaining {best['player']} against {opponents} "
            f"in GW{best['gameweek']}"
        ),
        "summary": (
            f"{best['player']} has the strongest upcoming attacker projection at "
            f"{best['projected_points']:.2f} points with a "
            f"{best['start_probability']:.0%} projected start probability."
        ),
        "confidence": confidence,
        "why_now": [
            f"Opponent defensive xGC/90 proxy: {best['opponent_xgc_per_90']:.2f}",
            f"Player expected goal involvements/90: {best['xgi_per_90']:.2f}",
            f"Fixture: {best['venue']}",
        ],
        "why_wait": (
            "Wait if minutes become uncertain or a stronger double-gameweek captain "
            "appears before the chip expires."
        ),
        "primary_candidate": best,
        "alternatives": _distinct_week_alternatives(candidates[1:], limit=3),
    }


def _bench_boost_opportunity(
    projected_players: Sequence[Mapping[str, Any]],
    raw_by_id: Mapping[int, Mapping[str, Any]],
    weeks: Sequence[int],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for gameweek in weeks:
        goalkeeper: list[dict[str, Any]] = []
        outfield: list[dict[str, Any]] = []
        for player in projected_players:
            player_id = _integer(player.get("element_id"))
            raw = raw_by_id.get(player_id or -1, {})
            if str(raw.get("status") or "a") in {"i", "s", "u"}:
                continue
            projection = next(
                (
                    row
                    for row in player.get("projections", [])
                    if _integer(row.get("gameweek")) == gameweek
                ),
                None,
            )
            if projection is None or bool(projection.get("blank")):
                continue
            fixtures = list(projection.get("fixtures") or [])
            row = {
                "player": _player_name(player, raw),
                "position": str(player.get("position") or ""),
                "price": round(_number(player.get("price")), 1),
                "projected_points": round(_number(projection.get("projected_points")), 2),
                "start_probability": round(
                    _average(
                        [_number(item.get("start_likelihood")) for item in fixtures],
                        default=0.0,
                    ),
                    3,
                ),
                "double_gameweek": bool(projection.get("double")),
            }
            if row["position"] == "GKP" and row["price"] <= 5.0:
                goalkeeper.append(row)
            elif row["position"] != "GKP" and row["price"] <= 5.5:
                outfield.append(row)
        goalkeeper.sort(key=_bench_candidate_key, reverse=True)
        outfield.sort(key=_bench_candidate_key, reverse=True)
        bench = goalkeeper[:1] + outfield[:3]
        if len(bench) != 4:
            continue
        candidates.append(
            {
                "gameweek": gameweek,
                "projected_bench_points": round(
                    sum(row["projected_points"] for row in bench),
                    2,
                ),
                "average_start_probability": round(
                    _average([row["start_probability"] for row in bench]),
                    3,
                ),
                "double_gameweek_players": sum(
                    int(row["double_gameweek"]) for row in bench
                ),
                "sample_budget_bench": bench,
            }
        )
    candidates.sort(
        key=lambda row: (
            row["projected_bench_points"],
            row["average_start_probability"],
        ),
        reverse=True,
    )
    if not candidates:
        return _no_window("bboost", "No credible Bench Boost window is visible yet.")
    best = candidates[0]
    names = ", ".join(row["player"] for row in best["sample_budget_bench"])
    confidence = _confidence(
        high=(
            best["projected_bench_points"] >= 14
            and best["average_start_probability"] >= 0.8
        ),
        medium=(
            best["projected_bench_points"] >= 10
            and best["average_start_probability"] >= 0.7
        ),
    )
    return {
        "chip_type": "bboost",
        "chip": CHIP_LABELS["bboost"],
        "recommended_gameweek": best["gameweek"],
        "headline": f"GW{best['gameweek']} is the strongest visible Bench Boost window",
        "summary": (
            f"A representative affordable bench projects for "
            f"{best['projected_bench_points']:.2f} points: {names}."
        ),
        "confidence": confidence,
        "why_now": [
            f"Budget-bench projection: {best['projected_bench_points']:.2f} points",
            f"Average projected start probability: {best['average_start_probability']:.0%}",
            f"Double-gameweek players in sample: {best['double_gameweek_players']}",
        ],
        "why_wait": (
            "This is a league-wide depth signal, not a judgment on your bench. "
            "Wait if your own four substitutes are weaker or carry minutes risk."
        ),
        "primary_candidate": best,
        "alternatives": candidates[1:4],
    }


def _free_hit_opportunity(
    fixtures: Sequence[Mapping[str, Any]],
    team_by_id: Mapping[int, Mapping[str, Any]],
    weeks: Sequence[int],
) -> dict[str, Any]:
    total_teams = len(team_by_id)
    candidates = []
    for gameweek in weeks:
        counts = _fixture_counts(fixtures, gameweek)
        blanks = [team_id for team_id in team_by_id if counts.get(team_id, 0) == 0]
        doubles = [team_id for team_id, count in counts.items() if count > 1]
        disruption = 2 * len(blanks) + 2 * len(doubles)
        candidates.append(
            {
                "gameweek": gameweek,
                "blank_teams": [_team_name(team_by_id, team_id) for team_id in blanks],
                "double_teams": [_team_name(team_by_id, team_id) for team_id in doubles],
                "teams_playing": total_teams - len(blanks),
                "disruption_score": disruption,
            }
        )
    candidates.sort(key=lambda row: (row["disruption_score"], row["gameweek"]), reverse=True)
    if not candidates or candidates[0]["disruption_score"] == 0:
        return _no_window(
            "freehit",
            "No blank or double Gameweek strong enough for a general Free Hit "
            "recommendation is visible.",
        )
    best = candidates[0]
    confidence = "high" if best["disruption_score"] >= 12 else "medium"
    return {
        "chip_type": "freehit",
        "chip": CHIP_LABELS["freehit"],
        "recommended_gameweek": best["gameweek"],
        "headline": f"GW{best['gameweek']} is the strongest visible Free Hit landscape",
        "summary": (
            f"{len(best['blank_teams'])} teams blank and "
            f"{len(best['double_teams'])} teams play twice."
        ),
        "confidence": confidence,
        "why_now": [
            f"Blank teams: {', '.join(best['blank_teams']) or 'none'}",
            f"Double teams: {', '.join(best['double_teams']) or 'none'}",
            f"Teams with a fixture: {best['teams_playing']} of {total_teams}",
        ],
        "why_wait": "Save the chip if later announced blanks or doubles create more disruption.",
        "primary_candidate": best,
        "alternatives": [row for row in candidates[1:4] if row["disruption_score"] > 0],
    }


def _wildcard_opportunity(
    fixtures: Sequence[Mapping[str, Any]],
    projected_players: Sequence[Mapping[str, Any]],
    team_by_id: Mapping[int, Mapping[str, Any]],
    weeks: Sequence[int],
) -> dict[str, Any]:
    projection_strength = _team_projection_strength(projected_players)
    candidates = []
    for gameweek in weeks:
        team_runs = []
        for team_id in team_by_id:
            difficulties = _team_difficulties(fixtures, team_id, gameweek, length=5)
            if not difficulties:
                continue
            team_runs.append(
                {
                    "team": _team_name(team_by_id, team_id),
                    "average_difficulty": round(_average(difficulties), 2),
                    "fixtures": len(difficulties),
                    "projection_strength": round(
                        _average(
                            [
                                projection_strength.get((team_id, target), 0.0)
                                for target in range(gameweek, gameweek + 5)
                            ]
                        ),
                        2,
                    ),
                }
            )
        team_runs.sort(
            key=lambda row: (
                row["projection_strength"] - 2.0 * row["average_difficulty"],
                row["projection_strength"],
            ),
            reverse=True,
        )
        cluster = team_runs[:4]
        if not cluster:
            continue
        candidates.append(
            {
                "gameweek": gameweek,
                "teams": cluster,
                "cluster_average_difficulty": round(
                    _average([row["average_difficulty"] for row in cluster]),
                    2,
                ),
                "cluster_projection_strength": round(
                    _average([row["projection_strength"] for row in cluster]),
                    2,
                ),
            }
        )
    candidates.sort(
        key=lambda row: (
            row["cluster_projection_strength"]
            - 2.0 * row["cluster_average_difficulty"],
            -row["gameweek"],
        ),
        reverse=True,
    )
    if not candidates:
        return _no_window("wildcard", "No reliable Wildcard fixture swing is visible yet.")
    best = candidates[0]
    team_names = ", ".join(row["team"] for row in best["teams"])
    confidence = _confidence(
        high=best["cluster_average_difficulty"] <= 2.2,
        medium=best["cluster_average_difficulty"] <= 2.7,
    )
    return {
        "chip_type": "wildcard",
        "chip": CHIP_LABELS["wildcard"],
        "recommended_gameweek": best["gameweek"],
        "headline": f"Consider a Wildcard fixture swing from GW{best['gameweek']}",
        "summary": (
            f"The strongest five-week fixture cluster belongs to {team_names}."
        ),
        "confidence": confidence,
        "why_now": [
            f"Cluster average fixture difficulty: {best['cluster_average_difficulty']:.2f}",
            *[
                f"{row['team']}: {row['average_difficulty']:.2f} fixture difficulty, "
                f"{row['projection_strength']:.2f} core projection"
                for row in best["teams"][:3]
            ],
        ],
        "why_wait": (
            "Wildcard value also depends on injuries, transfers and price changes; "
            "this card identifies the league-wide fixture swing only."
        ),
        "primary_candidate": best,
        "alternatives": candidates[1:4],
    }


def _team_projection_strength(
    projected_players: Sequence[Mapping[str, Any]],
) -> dict[tuple[int, int], float]:
    """Return each team's top-five player projection total by Gameweek."""

    scores: dict[tuple[int, int], list[float]] = defaultdict(list)
    for player in projected_players:
        team_id = _integer(player.get("team_id"))
        if team_id is None:
            continue
        for projection in player.get("projections", []):
            gameweek = _integer(projection.get("gameweek"))
            if gameweek is None:
                continue
            scores[(team_id, gameweek)].append(
                _number(projection.get("projected_points"))
            )
    return {
        key: round(sum(sorted(values, reverse=True)[:5]), 2)
        for key, values in scores.items()
    }


def _defence_profiles(
    elements: Iterable[Mapping[str, Any]],
    team_by_id: Mapping[int, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    totals: dict[int, dict[str, float]] = defaultdict(
        lambda: {"minutes": 0.0, "weighted_xgc": 0.0, "weighted_gc": 0.0}
    )
    for player in elements:
        if _integer(player.get("element_type")) not in {1, 2}:
            continue
        team_id = _integer(player.get("team"))
        minutes = _number(player.get("minutes"))
        if team_id is None or minutes <= 0:
            continue
        xgc_per_90 = _per_90(player, "expected_goals_conceded")
        gc_per_90 = _per_90(player, "goals_conceded")
        totals[team_id]["minutes"] += minutes
        totals[team_id]["weighted_xgc"] += xgc_per_90 * minutes
        totals[team_id]["weighted_gc"] += gc_per_90 * minutes
    rows = []
    for team_id, total in totals.items():
        if total["minutes"] <= 0:
            continue
        rows.append(
            {
                "team_id": team_id,
                "name": _team_name(team_by_id, team_id),
                "xgc_per_90": total["weighted_xgc"] / total["minutes"],
                "goals_conceded_per_90": total["weighted_gc"] / total["minutes"],
            }
        )
    rows.sort(key=lambda row: row["xgc_per_90"], reverse=True)
    count = len(rows)
    for index, row in enumerate(rows, start=1):
        row["weakness_rank"] = count - index + 1
    return {str(row["name"]): row for row in rows}


def _fixture_counts(
    fixtures: Sequence[Mapping[str, Any]], gameweek: int
) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for fixture in fixtures:
        if _integer(fixture.get("event")) != gameweek:
            continue
        for key in ("team_h", "team_a"):
            team_id = _integer(fixture.get(key))
            if team_id is not None:
                counts[team_id] += 1
    return dict(counts)


def _team_difficulties(
    fixtures: Sequence[Mapping[str, Any]],
    team_id: int,
    start_gameweek: int,
    *,
    length: int,
) -> list[float]:
    output = []
    end_gameweek = start_gameweek + length - 1
    for fixture in fixtures:
        gameweek = _integer(fixture.get("event"))
        if gameweek is None or not start_gameweek <= gameweek <= end_gameweek:
            continue
        if _integer(fixture.get("team_h")) == team_id:
            output.append(_number(fixture.get("team_h_difficulty"), default=3.0))
        elif _integer(fixture.get("team_a")) == team_id:
            output.append(_number(fixture.get("team_a_difficulty"), default=3.0))
    return output


def _distinct_week_alternatives(
    candidates: Sequence[dict[str, Any]], *, limit: int
) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for candidate in candidates:
        if candidate["gameweek"] in seen:
            continue
        seen.add(candidate["gameweek"])
        output.append(candidate)
        if len(output) >= limit:
            break
    return output


def _no_window(chip_type: str, message: str) -> dict[str, Any]:
    return {
        "chip_type": chip_type,
        "chip": CHIP_LABELS[chip_type],
        "recommended_gameweek": None,
        "headline": message,
        "summary": "The published fixture window does not currently justify a general call.",
        "confidence": "low",
        "why_now": [],
        "why_wait": "Recheck after fixtures or player availability change.",
        "primary_candidate": None,
        "alternatives": [],
    }


def _bench_candidate_key(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        _number(row.get("projected_points")),
        _number(row.get("start_probability")),
        -_number(row.get("price")),
    )


def _player_name(player: Mapping[str, Any], raw: Mapping[str, Any]) -> str:
    return str(
        player.get("name")
        or player.get("web_name")
        or raw.get("web_name")
        or "Unknown"
    )


def _team_name(team_by_id: Mapping[int, Mapping[str, Any]], team_id: int) -> str:
    row = team_by_id.get(team_id, {})
    return str(row.get("name") or row.get("short_name") or f"Team {team_id}")


def _venue_label(fixtures: Sequence[Mapping[str, Any]]) -> str:
    if len(fixtures) > 1:
        return "double Gameweek"
    if not fixtures:
        return "fixture unavailable"
    return "home" if bool(fixtures[0].get("home")) else "away"


def _confidence(*, high: bool, medium: bool) -> str:
    if high:
        return "high"
    if medium:
        return "medium"
    return "low"


def _per_90(player: Mapping[str, Any], key: str) -> float:
    direct = player.get(f"{key}_per_90")
    if direct not in (None, ""):
        return _number(direct)
    minutes = _number(player.get("minutes"))
    return _number(player.get(key)) * 90.0 / minutes if minutes > 0 else 0.0


def _average(values: Iterable[float], *, default: float = 0.0) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else default


def _integer(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _number(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
