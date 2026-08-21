"""Small, side-effect-free helpers for mileage entry calculations."""

from __future__ import annotations

import math
from typing import Any


def normalise_trip_miles(value: Any, round_trip: bool) -> tuple[float, float | None]:
    """Return (total claimed miles, original one-way miles when applicable)."""
    try:
        entered = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mileage must be a number") from exc
    if not math.isfinite(entered) or entered <= 0:
        raise ValueError("Mileage must be greater than zero")
    entered = round(entered, 1)
    return (round(entered * 2, 1), entered) if round_trip else (entered, None)
