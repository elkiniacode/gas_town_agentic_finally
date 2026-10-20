"""Response rounding (API_CONTRACT.md §Conventions): money/prices/percentages 2 dp, quantities 4 dp.

``+ 0.0`` turns ``-0.0`` into ``0.0`` so a tiny negative never renders as ``-0.0``.
"""

import math


def round2(value: float) -> float:
    return round(value, 2) + 0.0


def round4(value: float) -> float:
    return round(value, 4) + 0.0


def pct(numerator: float, denominator: float) -> float:
    """``numerator / denominator × 100`` in percentage points, 2 dp; 0 when undefined."""
    if denominator == 0 or not math.isfinite(denominator):
        return 0.0
    return round2(numerator / denominator * 100)


def format_quantity(quantity: float) -> str:
    """A quantity for error messages: 4 dp with trailing zeros stripped (``2.5``, ``5``, ``0``)."""
    text = f"{round4(quantity):.4f}".rstrip("0").rstrip(".")
    return text or "0"
