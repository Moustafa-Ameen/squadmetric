"""Explicit model assignments for separate FPL decision consumers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ProjectionConsumer = Literal["transfer", "captain", "chip", "lineup"]


@dataclass(frozen=True)
class ProjectionPortfolio:
    """Named model assignments kept separate from production routing.

    The portfolio is a contract for experiments. The benchmark still uses its
    existing single-model default unless an individual consumer override is
    supplied explicitly.
    """

    transfer_model: str = "Ridge Regression"
    captain_model: str = "Ridge Regression"
    chip_model: str = "Ridge Regression"
    lineup_model: str = "Ridge Regression"

    def model_for(self, consumer: ProjectionConsumer) -> str:
        if consumer == "transfer":
            return self.transfer_model
        if consumer == "captain":
            return self.captain_model
        if consumer == "chip":
            return self.chip_model
        if consumer == "lineup":
            return self.lineup_model
        raise ValueError(f"Unknown projection consumer: {consumer!r}")

    def as_dict(self) -> dict[str, str]:
        return asdict(self)
