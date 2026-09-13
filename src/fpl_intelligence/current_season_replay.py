"""Strict point-in-time replay of the current SquadMetric-managed FPL team."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from api.chip_recommendations import projection_frames

from fpl_intelligence.beam_search import (
    FREE_TRANSFER_MINIMUM_HORIZON_GAIN,
    DeterministicBeamPlanner,
    apply_transfer_plan,
)
from fpl_intelligence.chip_simulation import (
    apply_chip,
    apply_chip_to_score,
    apply_squad_transition,
    bench_points_not_autosubbed,
    chip_replaces_ordinary_transfer,
    initial_chip_state,
)
from fpl_intelligence.initial_squad_championship import (
    P3_CONFIGS,
    OpeningProjectionBundle,
    optimize_opening_squad,
)
from fpl_intelligence.launch_intelligence import availability_probability
from fpl_intelligence.live_model_training import BASE_FEATURE_COLUMNS
from fpl_intelligence.multi_gw_projection import project_players
from fpl_intelligence.preseason import build_identity_safe_preseason_pool
from fpl_intelligence.price_economics import (
    initialise_squad_economics,
    refresh_squad_prices,
)
from fpl_intelligence.season_benchmark import score_realistic_gameweek
from fpl_intelligence.season_rules import build_season_rules, payload_hash
from fpl_intelligence.step4_models import (
    build_ridge_model,
    fit_minutes_band_conditional_model,
    load_historical_player_gameweeks,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_PATH = PROJECT_ROOT / "data" / "processed" / "historical_player_gw.csv"
LIVE_PATH = PROJECT_ROOT / "data" / "processed" / "live_2026_27_player_gw.csv"
BOOTSTRAP_PATH = PROJECT_ROOT / "data" / "raw" / "bootstrap-static.json"
SNAPSHOT_ROOT = PROJECT_ROOT / "data" / "raw" / "snapshots" / "2026-27"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "current_season_replay"
SEASON = "2026-27"
HORIZON = 8


@dataclass(frozen=True)
class DeadlineSource:
    gameweek: int
    deadline: str
    captured_at: str
    bootstrap_path: str
    fixture_path: str
    bootstrap_hash: str


def run_current_season_replay(
    *,
    historical_path: Path = HISTORICAL_PATH,
    live_path: Path = LIVE_PATH,
    bootstrap_path: Path = BOOTSTRAP_PATH,
    snapshot_root: Path = SNAPSHOT_ROOT,
) -> dict[str, Any]:
    """Replay every finalized Gameweek without using later observations."""

    historical = load_historical_player_gameweeks(historical_path)
    live = pd.read_csv(live_path)
    current_bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    gameweeks = _validated_finalized_gameweeks(live, current_bootstrap)
    sources = {
        gameweek: _deadline_source(live, gameweek, snapshot_root)
        for gameweek in gameweeks
    }
    snapshots = {
        gameweek: _load_deadline_snapshot(sources[gameweek])
        for gameweek in gameweeks
    }

    first_bootstrap, first_fixtures = snapshots[gameweeks[0]]
    first_projection, first_players = _project_at_deadline(
        historical,
        live,
        gameweek=1,
        bootstrap=first_bootstrap,
        fixtures=first_fixtures,
    )
    squad = _opening_squad(
        historical,
        first_players,
        first_projection,
        data_cutoff=sources[1].captured_at,
    )
    initial_squad = squad.copy()
    initial_bank = round(100.0 - float(squad["price"].sum()), 1)
    bank = initial_bank
    free_transfers = 0
    rules = build_season_rules(
        first_bootstrap,
        season=SEASON,
        source_url=sources[1].bootstrap_path,
    )
    chip_state = initial_chip_state(rules)
    averages = {
        int(event["id"]): int(event.get("average_entry_score") or 0)
        for event in current_bootstrap.get("events", [])
        if int(event.get("id") or 0) in gameweeks
    }

    result_rows: list[dict[str, Any]] = []
    cumulative = 0.0
    for gameweek in gameweeks:
        bootstrap, fixtures = snapshots[gameweek]
        projected, player_rows = (
            (first_projection, first_players)
            if gameweek == 1
            else _project_at_deadline(
                historical,
                live,
                gameweek=gameweek,
                bootstrap=bootstrap,
                fixtures=fixtures,
            )
        )
        frames = projection_frames(projected)
        current = frames[gameweek]
        prices = {
            int(player["element_id"]): float(player["price"])
            for player in player_rows
        }
        squad = refresh_squad_prices(squad, prices)
        bank_before = bank
        free_before = free_transfers
        planner = DeterministicBeamPlanner(
            horizon=HORIZON,
            max_transfers=8,
            max_same_gameweek_transfers=min(5, max(2, free_before + 1)),
            hit_policy="horizon_value",
            allow_chips=True,
            minimum_transfer_horizon_gain=FREE_TRANSFER_MINIMUM_HORIZON_GAIN,
        )
        action = planner.decide(
            gameweek=gameweek,
            squad=squad,
            bank=bank,
            free_transfers=free_before,
            chip_state=chip_state,
            predictions=current.copy(),
            future_predictions={
                target: frame.copy()
                for target, frame in frames.items()
                if target > gameweek
            },
            chip_predictions=current.copy(),
            future_chip_predictions={
                target: frame.copy()
                for target, frame in frames.items()
                if target > gameweek
            },
            rules=build_season_rules(
                bootstrap,
                season=SEASON,
                source_url=sources[gameweek].bootstrap_path,
            ),
        )
        plan = action.transfer_plan
        chip = action.chip
        pre_action_squad = squad.copy()
        active_squad = squad.copy()
        if chip_replaces_ordinary_transfer(chip):
            if action.chip_squad is None:
                raise AssertionError("Squad-changing chip has no legal squad")
            active_squad, squad = apply_squad_transition(
                pre_action_squad,
                action.chip_squad,
                chip,
            )
            if chip is not None and chip.name == "wildcard":
                available_budget = bank_before + float(pre_action_squad["price"].sum())
                bank = round(available_budget - float(squad["price"].sum()), 1)
            free_transfers = free_before
        elif plan.made:
            squad = apply_transfer_plan(pre_action_squad, current, plan)
            bank = round(float(plan.bank_after), 1)
            free_transfers = max(0, free_transfers - plan.count)
            active_squad = squad.copy()
        if chip is not None:
            chip_state = apply_chip(chip_state, chip, gameweek, rules)

        target = live[live["gameweek"].astype(int) == gameweek].copy()
        captain_predictions = current[
            ["player_id", "expected_points_adjusted"]
        ].rename(columns={"expected_points_adjusted": "captain_predicted_points"})
        score = score_realistic_gameweek(
            active_squad,
            target,
            current.set_index("player_id")["expected_points_adjusted"].to_dict(),
            captain_predictions,
        )
        captain_actual = (
            score.vice_captain_actual_points
            if score.vice_captain_fallback
            else score.captain_actual_points
        )
        bench_points = bench_points_not_autosubbed(
            target,
            score.bench_ids,
            score.autosub_ids,
        )
        gross_points = apply_chip_to_score(
            score.points,
            captain_actual,
            chip=chip,
            bench_points=bench_points,
        )
        net_points = gross_points - int(plan.hit_cost)
        cumulative += net_points
        names = {
            int(player["element_id"]): str(player["name"])
            for player in player_rows
        }
        official_average = averages[gameweek]
        result_rows.append(
            {
                "gameweek": gameweek,
                "deadline_snapshot": sources[gameweek].captured_at,
                "training_current_season_through": gameweek - 1,
                "free_transfers_before": free_before,
                "bank_before": bank_before,
                "transfers": [
                    {
                        "out": move.outgoing_name,
                        "in": move.incoming_name,
                        "projected_immediate_gain": round(move.projected_gain, 3),
                    }
                    for move in plan.moves
                ],
                "hit_cost": int(plan.hit_cost),
                "transfer_projected_horizon_gain": round(
                    action.transfer_expected_horizon_gain,
                    3,
                ),
                "transfer_projected_horizon_net_gain": round(
                    action.transfer_expected_horizon_net_gain,
                    3,
                ),
                "chip": chip.name if chip is not None else None,
                "chip_number": chip.number if chip is not None else None,
                "chip_projected_horizon_gain": (
                    round(action.expected_horizon_points - action.no_chip_horizon_points, 3)
                    if chip is not None
                    else None
                ),
                "captain": names.get(score.captain_id),
                "vice_captain": names.get(score.vice_captain_id),
                "captain_points": float(score.captain_actual_points),
                "formation": score.formation,
                "autosubs": [names.get(player_id) for player_id in score.autosub_ids],
                "gross_points": gross_points,
                "net_points": net_points,
                "cumulative_points": cumulative,
                "official_average": official_average,
                "delta_vs_average": net_points - official_average,
                "decision_reason": action.reason,
                "bank_after": bank,
            }
        )
        free_transfers = min(int(rules.max_free_transfers or 5), free_transfers + 1)

    initial_names = {
        int(player["element_id"]): str(player["name"])
        for player in first_players
    }
    initial_rows = [
        {
            "player_id": int(row.player_id),
            "player_name": initial_names.get(int(row.player_id), str(row.player_name)),
            "position": str(row.position),
            "team_id": int(row.team),
            "price": float(row.price),
        }
        for row in initial_squad.itertuples(index=False)
    ]
    official_average_total = sum(averages.values())
    return {
        "schema_version": "squadmetric-current-season-walk-forward-v2",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "season": SEASON,
        "status": "complete",
        "finalized_gameweeks": gameweeks,
        "total_points": cumulative,
        "official_average_total": official_average_total,
        "delta_vs_official_average": cumulative - official_average_total,
        "initial_bank": initial_bank,
        "initial_squad": initial_rows,
        "gameweeks": result_rows,
        "policy": {
            "projection_portfolio": "r2-consumer-portfolio-v1",
            "points_model": "Ridge Regression",
            "minutes_model": "conditional bands",
            "horizon": HORIZON,
            "free_transfer_minimum_horizon_gain": FREE_TRANSFER_MINIMUM_HORIZON_GAIN,
            "hit_minimum_gross_horizon_gain": (
                FREE_TRANSFER_MINIMUM_HORIZON_GAIN + int(rules.transfer_hit_cost or 4)
            ),
            "known_unavailable_players": (
                "official availability is capped at zero and prioritized by projected gain"
            ),
            "proactive_chips": True,
            "automatic_fpl_actions": False,
        },
        "leakage_checks": {
            "deadline_snapshots_precede_deadlines": True,
            "target_or_future_results_in_training": False,
            "current_season_training_cutoff_by_gameweek": {
                str(gameweek): gameweek - 1 for gameweek in gameweeks
            },
            "only_finished_and_data_checked_gameweeks_scored": True,
            "season_local_player_ids_enforced": True,
        },
        "sources": [asdict(sources[gameweek]) for gameweek in gameweeks],
        "limitations": [
            "Historical ranked-player artifacts were not retained per deadline, so the replay "
            "uses the deadline bootstrap's official availability fields and refitted minutes "
            "model without a later role overlay.",
            "GW4 is excluded because official FPL has not marked it finished and data-checked.",
        ],
    }


def persist_replay(report: dict[str, Any], output_root: Path = OUTPUT_ROOT) -> Path:
    """Write an ignored reproducibility artifact without changing accepted benchmarks."""

    output_root.mkdir(parents=True, exist_ok=True)
    last_gameweek = max(report["finalized_gameweeks"])
    path = output_root / f"{report['season']}-through-gw{last_gameweek:02d}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _validated_finalized_gameweeks(
    live: pd.DataFrame,
    bootstrap: dict[str, Any],
) -> list[int]:
    official = [
        int(event["id"])
        for event in bootstrap.get("events", [])
        if bool(event.get("finished")) and bool(event.get("data_checked"))
    ]
    available = sorted(pd.to_numeric(live["gameweek"], errors="raise").astype(int).unique())
    if official != available:
        raise ValueError(
            f"Finalized official gameweeks {official} do not match replay rows {available}"
        )
    for flag in ("official_finished", "official_data_checked"):
        if flag not in live:
            raise ValueError(f"Replay rows require {flag}=true")
        flag_is_true = live[flag].astype("string").str.lower().isin({"true", "1"})
        if not flag_is_true.all():
            raise ValueError(f"Replay rows require {flag}=true")
    return official


def _deadline_source(
    live: pd.DataFrame,
    gameweek: int,
    snapshot_root: Path,
) -> DeadlineSource:
    rows = live[live["gameweek"].astype(int) == int(gameweek)]
    expected_hash = str(rows["predeadline_bootstrap_hash"].iloc[0])
    deadline = str(rows["deadline"].iloc[0])
    matches = sorted(snapshot_root.glob(f"bootstrap-*-{expected_hash[:16]}.json"))
    if len(matches) != 1:
        raise ValueError(f"GW{gameweek} requires exactly one matching bootstrap snapshot")
    bootstrap_path = matches[0]
    timestamp = bootstrap_path.name[len("bootstrap-") :].rsplit("-", 1)[0]
    fixture_matches = sorted(
        path
        for path in snapshot_root.glob(f"fixtures-{timestamp}-*.json")
        if not path.name.endswith(".metadata.json")
    )
    if len(fixture_matches) != 1:
        raise ValueError(f"GW{gameweek} requires exactly one timestamp-matched fixture snapshot")
    metadata_path = bootstrap_path.with_name(
        bootstrap_path.name.replace(".json", ".metadata.json")
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    captured_at = str(metadata.get("captured_at") or metadata.get("generated_at") or "")
    if not captured_at:
        captured_at = _timestamp_from_filename(timestamp)
    if _parse_time(captured_at) >= _parse_time(deadline):
        raise ValueError(f"GW{gameweek} snapshot is not pre-deadline")
    bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    if payload_hash(bootstrap) != expected_hash:
        raise ValueError(f"GW{gameweek} bootstrap hash does not match finalized evidence")
    return DeadlineSource(
        gameweek=gameweek,
        deadline=deadline,
        captured_at=captured_at,
        bootstrap_path=str(bootstrap_path),
        fixture_path=str(fixture_matches[0]),
        bootstrap_hash=expected_hash,
    )


def _load_deadline_snapshot(source: DeadlineSource) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bootstrap = json.loads(Path(source.bootstrap_path).read_text(encoding="utf-8"))
    fixtures = json.loads(Path(source.fixture_path).read_text(encoding="utf-8"))
    return bootstrap, fixtures


def _project_at_deadline(
    historical: pd.DataFrame,
    live: pd.DataFrame,
    *,
    gameweek: int,
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    past = live[live["gameweek"].astype(int) < int(gameweek)].copy()
    training = pd.concat([historical, past], ignore_index=True, sort=False)
    points_model, minutes_model = _fit_models(training)
    players = _player_rows(bootstrap)
    projected = project_players(
        players,
        fixtures,
        bootstrap.get("teams", []),
        gameweek,
        HORIZON,
        models=(points_model, minutes_model),
        history=training,
    )
    return projected, players


def _fit_models(training: pd.DataFrame) -> tuple[Any, Any]:
    available = training.dropna(subset=["next_gameweek_points"]).copy()
    points = build_ridge_model(BASE_FEATURE_COLUMNS)
    points.fit(available[BASE_FEATURE_COLUMNS], available["next_gameweek_points"])
    minutes = fit_minutes_band_conditional_model(available, BASE_FEATURE_COLUMNS)
    return points, minutes


def _player_rows(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    teams = {int(team["id"]): team for team in bootstrap.get("teams", [])}
    positions = {
        int(position["id"]): position
        for position in bootstrap.get("element_types", [])
    }
    rows: list[dict[str, Any]] = []
    for raw in bootstrap.get("elements", []):
        player_id = int(raw["id"])
        team = teams[int(raw["team"])]
        position = positions[int(raw["element_type"])]
        name = (
            f"{raw.get('first_name', '')} {raw.get('second_name', '')}".strip()
            or raw.get("web_name")
            or f"Player {player_id}"
        )
        rows.append(
            {
                "element_id": player_id,
                "player_id": player_id,
                "name": name,
                "player_name": name,
                "web_name": raw.get("web_name") or name,
                "team_id": int(raw["team"]),
                "team": team.get("name"),
                "team_name": team.get("name"),
                "team_code": team.get("code"),
                "position": position.get("singular_name_short")
                or position.get("singular_name"),
                "price": float(raw.get("now_cost") or 0) / 10,
                "price_before_deadline": float(raw.get("now_cost") or 0) / 10,
                "selected_by_percent": float(raw.get("selected_by_percent") or 0),
                "selected_by_percent_before_deadline": float(
                    raw.get("selected_by_percent") or 0
                ),
                "market_snapshot_available": 1,
                "status": raw.get("status"),
                "chance_of_playing_next_round": raw.get(
                    "chance_of_playing_next_round"
                ),
                "news": raw.get("news"),
                "availability_probability": availability_probability(
                    raw.get("status"), raw.get("chance_of_playing_next_round")
                ),
                "start_likelihood": None,
                "prior_source": None,
                "season": SEASON,
                "gameweek": 1,
                "feature_cutoff_gameweek": 0,
                "previous_minutes": raw.get("minutes"),
                "previous_starts": raw.get("starts"),
                "previous_bonus": raw.get("bonus"),
                "previous_bps": raw.get("bps"),
                "previous_cbi": raw.get("clearances_blocks_interceptions"),
                "previous_tackles": raw.get("tackles"),
                "previous_recoveries": raw.get("recoveries"),
                "penalties_order": raw.get("penalties_order"),
                "penalties_text": raw.get("penalties_text"),
                "direct_freekicks_order": raw.get("direct_freekicks_order"),
                "direct_freekicks_text": raw.get("direct_freekicks_text"),
                "corners_and_indirect_freekicks_order": raw.get(
                    "corners_and_indirect_freekicks_order"
                ),
                "corners_and_indirect_freekicks_text": raw.get(
                    "corners_and_indirect_freekicks_text"
                ),
            }
        )
    return rows


def _opening_squad(
    historical: pd.DataFrame,
    players: list[dict[str, Any]],
    projected: list[dict[str, Any]],
    *,
    data_cutoff: str,
) -> pd.DataFrame:
    candidates = build_identity_safe_preseason_pool(
        pd.concat([historical, pd.DataFrame(players)], ignore_index=True, sort=False),
        season=SEASON,
        prior_season="2025-26",
    )
    projection_rows: dict[int, pd.DataFrame] = {}
    for gameweek in range(1, HORIZON + 1):
        rows = []
        for player in projected:
            projection = next(
                row
                for row in player["projections"]
                if int(row["gameweek"]) == gameweek
            )
            start_probabilities = [
                float(fixture.get("start_likelihood") or 0)
                for fixture in projection.get("fixtures", [])
                if fixture.get("start_likelihood") is not None
            ]
            rows.append(
                {
                    "player_id": int(player["element_id"]),
                    "projected_points": float(projection["projected_points"]),
                    "start_probability": (
                        max(start_probabilities) if start_probabilities else 0.0
                    ),
                }
            )
        projection_rows[gameweek] = pd.DataFrame(rows)
    digest = hashlib.sha256()
    for gameweek, frame in projection_rows.items():
        digest.update(str(gameweek).encode("utf-8"))
        digest.update(
            pd.util.hash_pandas_object(
                frame.sort_values("player_id"), index=False
            ).values.tobytes()
        )
    bundle = OpeningProjectionBundle(
        season=SEASON,
        candidates=candidates,
        projections=projection_rows,
        prior_season="2025-26",
        data_cutoff=data_cutoff,
        projection_hash=digest.hexdigest(),
    )
    selected = optimize_opening_squad(bundle, P3_CONFIGS["horizon_8_flexible"])
    squad = selected.squad.copy()
    team_ids = {
        int(player["element_id"]): int(player["team_id"])
        for player in players
    }
    squad["team"] = squad["player_id"].map(team_ids)
    return initialise_squad_economics(squad)


def _timestamp_from_filename(timestamp: str) -> str:
    parsed = datetime.strptime(timestamp, "%Y%m%dT%H%M%S.%f").replace(tzinfo=UTC)
    return parsed.isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    report = run_current_season_replay()
    if not args.no_save:
        path = persist_replay(report)
        report["output_path"] = str(path)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
