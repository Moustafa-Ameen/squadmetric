"""Public W2 projection metric contracts."""

from pydantic import BaseModel

PROJECTION_CONTRACT_VERSION = "w2-v1"

METRIC_DEFINITIONS = {
    "raw_xp": "Points-model expectation before live minutes and availability adjustment.",
    "expected_points": (
        "Decision-grade expectation after minutes, availability, rules, and role "
        "adjustments."
    ),
    "start_adjusted_xp": (
        "Explicit alias of expected_points for consumers comparing raw and adjusted "
        "projections."
    ),
    "captain_expected_points": "Expected_points with the normal captain multiplier applied.",
    "captaincy_score": "Decision ordering score; currently equal to expected_points.",
    "captain_rank_score": "Historical 0-1 ranking heuristic; not expected FPL points.",
    "transfer_rank_score": "Historical transfer ranking heuristic; not expected FPL points.",
    "horizon_xp": "Sum of decision-grade expected_points across the declared gameweek horizon.",
}


class ProjectionRecord(BaseModel):
    element_id: int
    name: str
    team: str
    position: str
    price: float
    raw_xp: float
    expected_points: float
    start_adjusted_xp: float
    captain_expected_points: float
    captaincy_score: float
    start_likelihood: float
    blank: bool
    double: bool
    gameweek: int
    season: str
    bootstrap_hash: str
    rules_version: str
    data_cutoff: str
    model: str
    portfolio_version: str
    projection_contract_version: str


class TransferProjectionRecord(ProjectionRecord):
    transfer_rank_score: float
    prior_source: str | None = None
