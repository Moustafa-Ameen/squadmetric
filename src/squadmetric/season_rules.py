"""Versioned FPL season rules and immutable source snapshot utilities.

The live bootstrap payload is the authoritative machine-readable source for the
current game configuration.  This module keeps the complete payload intact and
also exposes a small normalized manifest for code that needs stable rule
semantics.  Historical rule regimes are explicit so missing historical fields
are never silently interpreted as zeroes.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RULES_SCHEMA_VERSION = "m6-v3"
DEFAULT_TRANSFER_HIT_COST = 4
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_SNAPSHOT_DIR = PROJECT_ROOT / "data" / "raw" / "snapshots"
RULE_MANIFEST_DIR = PROJECT_ROOT / "data" / "processed" / "rules"

PROMOTED_TEAMS_BY_SEASON: dict[str, tuple[str, ...]] = {
    "2026-27": ("Coventry City", "Ipswich Town", "Hull City"),
}
RELEGATED_TEAMS_BY_SEASON: dict[str, tuple[str, ...]] = {
    "2026-27": ("Burnley", "West Ham United", "Wolverhampton Wanderers"),
}

HISTORICAL_RULE_SOURCE_URLS = {
    "2023-24": "https://www.premierleague.com/en/news/4026959",
    "2024-25": "https://www.premierleague.com/en/news/4058895",
    "2025-26": "https://www.premierleague.com/en/news/4362027",
}

# Popularity counters move continuously but cannot change player eligibility,
# price, availability, scoring rules, or fixture decisions. They remain in raw
# snapshots; only the decision-contract hash excludes them.
VOLATILE_BOOTSTRAP_FIELDS = {
    "selected_by_percent",
    "selected_rank",
    "selected_rank_type",
    "transfers_in",
    "transfers_in_event",
    "transfers_out",
    "transfers_out_event",
}


@dataclass(frozen=True)
class SeasonRules:
    """Normalized, serializable rules contract for one FPL season."""

    season: str
    rules_version: str
    effective_from_gameweek: int | None
    effective_to_gameweek: int | None
    budget: float | None
    squad_size: int | None
    starting_xi_size: int | None
    max_players_per_team: int | None
    transfer_hit_cost: int | None
    transfer_sell_on_fee: float | None
    transfers_per_gameweek: int
    max_extra_free_transfers: int | None
    max_free_transfers: int | None
    position_limits: dict[str, dict[str, int | None]]
    chips: list[dict[str, Any]]
    chip_rules_version: str
    chip_reset_gameweek: int | None
    scoring: dict[str, Any]
    dc_rule_version: str
    bps_rule_version: str
    source_url: str
    retrieved_at: str
    cutoff_at: str
    payload_hash: str
    schema_version: str = RULES_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_timestamp(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def canonical_json(value: Any) -> str:
    """Return stable JSON suitable for hashing and reproducibility checks."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def decision_bootstrap_hash(bootstrap: Mapping[str, Any]) -> str:
    """Hash official bootstrap fields that can change an FPL decision."""

    contract = {
        key: value
        for key, value in bootstrap.items()
        if key not in {"elements", "total_players"}
    }
    contract["elements"] = [
        {
            key: value
            for key, value in player.items()
            if key not in VOLATILE_BOOTSTRAP_FIELDS
        }
        for player in bootstrap.get("elements", [])
        if isinstance(player, Mapping)
    ]
    return payload_hash(contract)


def rules_contract_hash(rules: SeasonRules) -> str:
    """Hash only decision-relevant rules, excluding source observation metadata."""

    contract = rules.to_dict()
    for source_field in (
        "source_url",
        "retrieved_at",
        "cutoff_at",
        "payload_hash",
    ):
        contract.pop(source_field, None)
    return hashlib.sha256(canonical_json(contract).encode("utf-8")).hexdigest()


def infer_season_from_bootstrap(bootstrap: Mapping[str, Any]) -> str:
    deadlines = [
        str(event.get("deadline_time"))
        for event in bootstrap.get("events") or []
        if isinstance(event, Mapping) and event.get("deadline_time")
    ]
    if not deadlines:
        return "unknown"
    year = int(min(deadlines)[:4])
    return f"{year}-{str(year + 1)[-2:]}"


def build_snapshot_metadata(
    payload: Mapping[str, Any],
    *,
    season: str,
    source_url: str,
    retrieved_at: datetime | str | None = None,
    cutoff_at: datetime | str | None = None,
    schema_version: str = RULES_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Build metadata without modifying the source payload."""

    return {
        "season": season,
        "source_url": source_url,
        "retrieved_at": _utc_timestamp(retrieved_at),
        "cutoff_at": _utc_timestamp(cutoff_at or retrieved_at),
        "payload_hash": payload_hash(payload),
        "schema_version": schema_version,
    }


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _effective_gameweeks(bootstrap: Mapping[str, Any]) -> tuple[int | None, int | None]:
    events = bootstrap.get("events") or []
    ids = [_safe_int(event.get("id")) for event in events if isinstance(event, Mapping)]
    ids = [event_id for event_id in ids if event_id is not None]
    return (min(ids), max(ids)) if ids else (None, None)


def _position_limits(bootstrap: Mapping[str, Any]) -> dict[str, dict[str, int | None]]:
    limits: dict[str, dict[str, int | None]] = {}
    for position in bootstrap.get("element_types") or []:
        if not isinstance(position, Mapping):
            continue
        short_name = str(
            position.get("singular_name_short")
            or position.get("plural_name_short")
            or position.get("singular_name")
            or position.get("id")
        )
        limits[short_name] = {
            "position_id": _safe_int(position.get("id")),
            "squad_select": _safe_int(position.get("squad_select")),
            "squad_min_play": _safe_int(position.get("squad_min_play")),
            "squad_max_play": _safe_int(position.get("squad_max_play")),
        }
    return limits


def _normalized_chips(bootstrap: Mapping[str, Any]) -> list[dict[str, Any]]:
    chips = bootstrap.get("chips") or []
    normalized: list[dict[str, Any]] = []
    occurrences: dict[str, int] = {}
    for chip in chips:
        if not isinstance(chip, Mapping):
            continue
        name = str(chip.get("name") or "")
        occurrences[name] = occurrences.get(name, 0) + 1
        number = _safe_int(chip.get("number"))
        if number in (None, 1) and occurrences[name] > 1:
            number = occurrences[name]
        normalized.append(
            {
                "id": _safe_int(chip.get("id")),
                "name": chip.get("name"),
                "number": number,
                "start_event": _safe_int(chip.get("start_event")),
                "stop_event": _safe_int(chip.get("stop_event")),
                "chip_type": chip.get("chip_type"),
                "overrides": chip.get("overrides", {}),
                **_chip_behavior(str(chip.get("name") or "")),
            }
        )
    return normalized


def _chip_behavior(name: str) -> dict[str, Any]:
    """Return stable behavior metadata shared by live and historical chips."""

    normalized_name = name.lower().replace("_", "").replace(" ", "")
    if normalized_name == "wildcard":
        return {
            "duration_gameweeks": 1,
            "permanent_transfers": True,
            "free_hit_reversion": False,
            "bench_points_included": False,
            "captain_multiplier": 2,
            "blocks_other_chips": False,
        }
    if normalized_name == "freehit":
        return {
            "duration_gameweeks": 1,
            "permanent_transfers": False,
            "free_hit_reversion": True,
            "bench_points_included": False,
            "captain_multiplier": 2,
            "blocks_other_chips": False,
        }
    if normalized_name in {"bboost", "benchboost"}:
        return {
            "duration_gameweeks": 1,
            "permanent_transfers": False,
            "free_hit_reversion": False,
            "bench_points_included": True,
            "captain_multiplier": 2,
            "blocks_other_chips": False,
        }
    if normalized_name in {"3xc", "triplecaptain"}:
        return {
            "duration_gameweeks": 1,
            "permanent_transfers": False,
            "free_hit_reversion": False,
            "bench_points_included": False,
            "captain_multiplier": 3,
            "blocks_other_chips": False,
        }
    if normalized_name in {"assistantmanager", "assistant_mgr"}:
        return {
            "duration_gameweeks": 3,
            "permanent_transfers": False,
            "free_hit_reversion": False,
            "bench_points_included": False,
            "captain_multiplier": 2,
            "blocks_other_chips": True,
        }
    return {
        "duration_gameweeks": 1,
        "permanent_transfers": False,
        "free_hit_reversion": False,
        "bench_points_included": False,
        "captain_multiplier": 2,
        "blocks_other_chips": False,
    }


def _chip_rules_version(season: str, chips: list[dict[str, Any]]) -> str:
    names = {str(chip.get("name", "")).lower() for chip in chips}
    second_half_names = {
        str(chip.get("name", "")).lower()
        for chip in chips
        if chip.get("number") == 2
    }
    if "assistant_manager" in names:
        return "chips_v2_assistant_manager_2024_25"
    if len(second_half_names) >= 4:
        return f"chips_v{4 if season == '2026-27' else 3}_double_set_{season.replace('-', '_')}"
    return f"chips_v1_single_set_{season.replace('-', '_')}"


def _chip_reset_gameweek(chips: list[dict[str, Any]]) -> int | None:
    first_half = {
        str(chip.get("name", "")).lower()
        for chip in chips
        if chip.get("number") == 1
    }
    second_half = {
        str(chip.get("name", "")).lower()
        for chip in chips
        if chip.get("number") == 2
    }
    return 19 if len(first_half & second_half) >= 4 else None


def _regime_versions(season: str, bootstrap: Mapping[str, Any]) -> tuple[str, str]:
    """Return explicit DC/BPS eras without filling missing historical data."""

    if season < "2025-26":
        return "pre_dc", "bps_pre_2025_26"
    if season == "2025-26":
        return "dc_v1", "bps_v1_2025_26"

    scoring = ((bootstrap.get("game_config") or {}).get("scoring") or {})
    has_dc_scoring = "defensive_contribution" in scoring
    return ("dc_v1" if has_dc_scoring else "dc_unknown"), "bps_v2_2026_27"


def build_season_rules(
    bootstrap: Mapping[str, Any],
    *,
    season: str,
    source_url: str,
    retrieved_at: datetime | str | None = None,
    cutoff_at: datetime | str | None = None,
) -> SeasonRules:
    """Normalize bootstrap configuration into a versioned season contract."""

    settings = bootstrap.get("game_settings") or {}
    scoring = ((bootstrap.get("game_config") or {}).get("scoring") or {})
    min_gw, max_gw = _effective_gameweeks(bootstrap)
    dc_rule_version, bps_rule_version = _regime_versions(season, bootstrap)
    max_extra = _safe_int(settings.get("max_extra_free_transfers"))
    max_free = 1 + max_extra if max_extra is not None else None
    chips = _normalized_chips(bootstrap)
    chip_rules_version = _chip_rules_version(season, chips)
    manifest_metadata = build_snapshot_metadata(
        bootstrap,
        season=season,
        source_url=source_url,
        retrieved_at=retrieved_at,
        cutoff_at=cutoff_at,
    )

    return SeasonRules(
        season=season,
        rules_version=(
            f"{season}-{RULES_SCHEMA_VERSION}-{chip_rules_version}-{bps_rule_version}"
        ),
        effective_from_gameweek=min_gw,
        effective_to_gameweek=max_gw,
        budget=(
            _safe_float(settings.get("squad_total_spend"))
            / (_safe_float(settings.get("ui_currency_multiplier")) or 10)
            if _safe_float(settings.get("squad_total_spend")) is not None
            else None
        ),
        squad_size=_safe_int(settings.get("squad_squadsize")),
        starting_xi_size=_safe_int(settings.get("squad_squadplay")),
        max_players_per_team=_safe_int(settings.get("squad_team_limit")),
        transfer_hit_cost=_safe_int(scoring.get("transfer_cost")) or DEFAULT_TRANSFER_HIT_COST,
        transfer_sell_on_fee=_safe_float(settings.get("transfers_sell_on_fee")),
        transfers_per_gameweek=1,
        max_extra_free_transfers=max_extra,
        max_free_transfers=max_free,
        position_limits=_position_limits(bootstrap),
        chips=chips,
        chip_rules_version=chip_rules_version,
        chip_reset_gameweek=_chip_reset_gameweek(chips),
        scoring=dict(scoring),
        dc_rule_version=dc_rule_version,
        bps_rule_version=bps_rule_version,
        source_url=source_url,
        retrieved_at=manifest_metadata["retrieved_at"],
        cutoff_at=manifest_metadata["cutoff_at"],
        payload_hash=manifest_metadata["payload_hash"],
    )


def save_immutable_snapshot(
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    root: Path = RAW_SNAPSHOT_DIR,
    artifact_name: str = "bootstrap",
) -> tuple[Path, Path]:
    """Save a content-addressed raw snapshot and adjacent metadata file.

    Existing content-addressed files are never overwritten.  A conflicting
    file at the same path raises instead of silently changing history.
    """

    season = str(metadata["season"])
    timestamp = str(metadata["retrieved_at"]).replace(":", "").replace("-", "")
    timestamp = timestamp.replace("+00", "").replace("Z", "")
    digest = str(metadata["payload_hash"])
    directory = root / season
    safe_name = "".join(
        character for character in artifact_name if character.isalnum() or character in {"-", "_"}
    )
    if not safe_name:
        raise ValueError("artifact_name must contain at least one safe character")
    snapshot_path = directory / f"{safe_name}-{timestamp}-{digest[:16]}.json"
    metadata_path = snapshot_path.with_suffix(".metadata.json")
    raw_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    metadata_text = json.dumps(dict(metadata), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    directory.mkdir(parents=True, exist_ok=True)
    if snapshot_path.exists() and snapshot_path.read_text(encoding="utf-8") != raw_text:
        raise FileExistsError(f"Immutable snapshot conflict: {snapshot_path}")
    if metadata_path.exists() and metadata_path.read_text(encoding="utf-8") != metadata_text:
        raise FileExistsError(f"Immutable metadata conflict: {metadata_path}")
    if not snapshot_path.exists():
        reusable = next(
            (
                candidate
                for candidate in sorted(directory.glob(f"{safe_name}-*-{digest[:16]}.json"))
                if candidate != snapshot_path
                and candidate.read_text(encoding="utf-8") == raw_text
            ),
            None,
        )
        if reusable is None:
            snapshot_path.write_text(raw_text, encoding="utf-8")
        else:
            try:
                os.link(reusable, snapshot_path)
            except OSError:
                snapshot_path.write_text(raw_text, encoding="utf-8")
    if not metadata_path.exists():
        metadata_path.write_text(metadata_text, encoding="utf-8")
    return snapshot_path, metadata_path


def save_rules_manifest(
    rules: SeasonRules,
    *,
    root: Path = RULE_MANIFEST_DIR,
) -> Path:
    """Persist the normalized manifest without changing its content."""

    path = (
        root
        / rules.season
        / f"{rules.rules_version}-{rules.payload_hash[:16]}.json"
    )
    content = json.dumps(rules.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != content:
        existing = json.loads(path.read_text(encoding="utf-8"))
        proposed = rules.to_dict()
        for volatile_key in ("retrieved_at", "cutoff_at"):
            existing.pop(volatile_key, None)
            proposed.pop(volatile_key, None)
        if existing != proposed:
            raise FileExistsError(f"Rules manifest conflict: {path}")
        return path
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def validate_bootstrap_onboarding(
    bootstrap: Mapping[str, Any],
    *,
    season: str,
) -> list[str]:
    """Return actionable onboarding errors for a bootstrap payload."""

    errors: list[str] = []
    teams = bootstrap.get("teams") or []
    elements = bootstrap.get("elements") or []
    positions = bootstrap.get("element_types") or []

    team_ids = [team.get("id") for team in teams if isinstance(team, Mapping)]
    player_ids = [player.get("id") for player in elements if isinstance(player, Mapping)]
    position_ids = [position.get("id") for position in positions if isinstance(position, Mapping)]

    for label, values in (("team", team_ids), ("player", player_ids), ("position", position_ids)):
        non_null = [value for value in values if value is not None]
        if len(non_null) != len(set(non_null)):
            errors.append(f"duplicate {label} IDs detected")

    team_names = {team.get("name") for team in teams if isinstance(team, Mapping)}
    for required_team in PROMOTED_TEAMS_BY_SEASON.get(season, ()):
        if required_team not in team_names:
            errors.append(f"missing required {season} team: {required_team}")
    for relegated_team in RELEGATED_TEAMS_BY_SEASON.get(season, ()):
        if relegated_team in team_names:
            errors.append(f"relegated team still present for {season}: {relegated_team}")
    team_id_set = set(team_ids)
    position_id_set = set(position_ids)
    for player in elements:
        if not isinstance(player, Mapping):
            continue
        if player.get("id") is None:
            errors.append("player missing id")
        if player.get("team") not in team_id_set:
            errors.append(f"player {player.get('id')} references unknown team {player.get('team')}")
        if player.get("element_type") not in position_id_set:
            errors.append(
                f"player {player.get('id')} references unknown position "
                f"{player.get('element_type')}"
            )
    return errors


def historical_regime(season: str) -> dict[str, str]:
    """Return explicit regimes for locally supported historical seasons.

    Future seasons must provide a loaded ``SeasonRules`` manifest instead of
    inheriting a season-name heuristic.
    """

    if season < "2025-26":
        return {"dc_rule_version": "pre_dc", "bps_rule_version": "bps_pre_2025_26"}
    if season == "2025-26":
        return {"dc_rule_version": "dc_v1", "bps_rule_version": "bps_v1_2025_26"}
    raise ValueError(
        f"No season-name regime exists for {season}; load the versioned rules manifest."
    )


def regime_from_rules(rules: SeasonRules) -> dict[str, str]:
    """Return DC/BPS regime labels from an explicit rules manifest."""

    return {
        "dc_rule_version": rules.dc_rule_version,
        "bps_rule_version": rules.bps_rule_version,
    }


def build_historical_season_rules(season: str) -> SeasonRules:
    """Build an explicit manifest for a supported pre-live season.

    Historical bootstrap payloads are not stored locally with the same rules
    metadata as the live API.  The manifest therefore records the stable FPL
    constraints and chip eras known to the project while marking the scoring
    payload as historical-contract metadata rather than pretending that a
    current bootstrap payload was observed in that season.
    """

    if season not in {"2023-24", "2024-25", "2025-26"}:
        raise ValueError(
            "Historical manifest helper only supports 2023-24, 2024-25, "
            f"and 2025-26: {season}"
        )

    def chip(name: str, number: int, start_event: int, stop_event: int) -> dict[str, Any]:
        return {
            "id": None,
            "name": name,
            "number": number,
            "start_event": start_event,
            "stop_event": stop_event,
            "chip_type": "historical_contract",
            "overrides": {},
            **_chip_behavior(name),
        }

    if season == "2025-26":
        chips = [
            chip("wildcard", 1, 2, 19),
            chip("wildcard", 2, 20, 38),
            chip("freehit", 1, 2, 19),
            chip("freehit", 2, 20, 38),
            chip("bboost", 1, 1, 19),
            chip("bboost", 2, 20, 38),
            chip("3xc", 1, 1, 19),
            chip("3xc", 2, 20, 38),
        ]
    else:
        chips = [
            chip("wildcard", 1, 2, 19),
            chip("wildcard", 2, 20, 38),
            chip("freehit", 1, 2, 38),
            chip("bboost", 1, 1, 38),
            chip("3xc", 1, 1, 38),
        ]
    if season == "2024-25":
        chips.append(chip("assistant_manager", 1, 24, 38))

    max_extra = 1 if season == "2023-24" else 4
    bootstrap = {
        "events": [{"id": 1}, {"id": 38}],
        "chips": chips,
        "element_types": [
            {
                "id": 1,
                "singular_name": "Goalkeeper",
                "singular_name_short": "GKP",
                "squad_select": 2,
                "squad_min_play": 1,
                "squad_max_play": 1,
            },
            {
                "id": 2,
                "singular_name": "Defender",
                "singular_name_short": "DEF",
                "squad_select": 5,
                "squad_min_play": 3,
                "squad_max_play": 5,
            },
            {
                "id": 3,
                "singular_name": "Midfielder",
                "singular_name_short": "MID",
                "squad_select": 5,
                "squad_min_play": 2,
                "squad_max_play": 5,
            },
            {
                "id": 4,
                "singular_name": "Forward",
                "singular_name_short": "FWD",
                "squad_select": 3,
                "squad_min_play": 1,
                "squad_max_play": 3,
            },
        ],
        "game_settings": {
            "squad_total_spend": 1000,
            "ui_currency_multiplier": 10,
            "squad_squadsize": 15,
            "squad_squadplay": 11,
            "squad_team_limit": 3,
            "max_extra_free_transfers": max_extra,
            "transfers_sell_on_fee": 0.5,
        },
        "game_config": {
            "scoring": {
                "status": "historical_contract_metadata",
            }
        },
    }
    return build_season_rules(
        bootstrap,
        season=season,
        source_url=HISTORICAL_RULE_SOURCE_URLS[season],
        retrieved_at=f"{season[:4]}-08-01T00:00:00Z",
        cutoff_at=f"{season[:4]}-08-01T00:00:00Z",
    )
