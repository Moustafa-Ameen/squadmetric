"""Production feature gates for recommendation classes under validation."""

from __future__ import annotations

import os


def proactive_chip_recommendations_enabled() -> bool:
    """Offer timed chip advice, labelled experimental, unless switched off by env."""

    return os.getenv("FPL_ENABLE_PROACTIVE_CHIP_RECOMMENDATIONS", "true").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
