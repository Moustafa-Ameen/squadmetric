"""Production feature gates for recommendation classes under validation."""

from __future__ import annotations

import os


def proactive_chip_recommendations_enabled() -> bool:
    """Keep chip calls off until owned-squad, season-long validation passes."""

    return os.getenv("FPL_ENABLE_PROACTIVE_CHIP_RECOMMENDATIONS", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
