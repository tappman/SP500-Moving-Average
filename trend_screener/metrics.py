"""Small independently testable mathematical definitions, in percentage units."""
from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.stats import linregress


class InsufficientData(ValueError):
    pass


def window(values, observations: int, offset: int = 0) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if observations < 1 or offset < 0 or len(a) < observations + offset:
        raise InsufficientData(f"Need {observations + offset} observations; have {len(a)}")
    stop = len(a) - offset
    a = a[stop - observations:stop]
    if not np.all(np.isfinite(a)):
        raise InsufficientData("Analyzed window contains missing or non-finite observations")
    if np.any(a <= 0):
        raise InsufficientData("Moving average / price values must be positive")
    return a


@dataclass
class Regression:
    slope: float
    normalized_slope: float
    r2: float
    intercept: float
    observations: int

    def to_dict(self):
        return asdict(self)


def regression(values) -> Regression:
    y = np.asarray(values, dtype=float)
    if len(y) < 2:
        raise InsufficientData("Regression requires at least 2 observations")
    y = window(y, len(y))
    if np.ptp(y) == 0:
        # A constant line has zero slope. R² is undefined, deliberately NaN.
        return Regression(0.0, 0.0, math.nan, float(y[0]), len(y))
    fit = linregress(np.arange(len(y), dtype=float), y)
    return Regression(float(fit.slope), float(100 * fit.slope / y.mean()),
                      float(np.clip(fit.rvalue**2, 0, 1)), float(fit.intercept), len(y))


def trend_metrics(values, regression_observations: int | None = None) -> dict:
    """Metrics for exactly these observations; counts refer to len(values)-1 transitions."""
    y = window(values, len(values))
    changes = np.diff(y)
    positive = changes > 0
    negative = changes < 0
    best = current = 0
    for up in positive:
        current = current + 1 if up else 0
        best = max(best, current)
    peaks = np.maximum.accumulate(y)
    result = {
        "start": float(y[0]), "end": float(y[-1]),
        "pct_change": float(100 * (y[-1] / y[0] - 1)),
        "observations": len(y), "transitions": len(changes),
        "positive_count": int(positive.sum()), "negative_count": int(negative.sum()),
        "flat_count": int((changes == 0).sum()),
        "positive_pct": float(100 * positive.mean()) if len(changes) else math.nan,
        "strict": bool(len(changes) and positive.all()),
        "max_drawdown_pct": float(100 * np.max(1 - y / peaks)),
        "longest_streak": best,
    }
    n = regression_observations if regression_observations is not None else len(y)
    if n >= 2:
        result.update(regression(window(y, n)).to_dict())
        result["observations"] = len(y)
    return result


def pct_acceleration(values, transitions: int) -> dict:
    y = window(values, 2 * transitions + 1)
    previous = 100 * (y[transitions] / y[0] - 1)
    current = 100 * (y[-1] / y[transitions] - 1)
    return {"previous_change": float(previous), "current_change": float(current),
            "accel_pct": float(current - previous)}


def slope_acceleration(values, observations: int) -> dict:
    y = window(values, 2 * observations)
    previous = regression(y[:observations])
    current = regression(y[observations:])
    return {"previous_slope": previous.slope, "current_slope": current.slope,
            "previous_normalized_slope": previous.normalized_slope,
            "current_normalized_slope": current.normalized_slope,
            "previous_r2": previous.r2, "current_r2": current.r2,
            "accel_slope": current.normalized_slope - previous.normalized_slope}


def turning_up(values, observations: int, lag: int, confirmation: int = 1,
               minimum_slope: float = 0.0, allow_flat: bool = True) -> dict:
    previous = regression(window(values, observations, lag))
    recent = [regression(window(values, observations, k)) for k in range(confirmation)]
    was_down = previous.normalized_slope <= 0 if allow_flat else previous.normalized_slope < 0
    confirmed = all(r.normalized_slope > minimum_slope for r in recent)
    return {
        "turn_up": bool(was_down and confirmed),
        "previous_normalized_slope": previous.normalized_slope,
        "current_normalized_slope": recent[0].normalized_slope,
        "previous_slope": previous.slope, "current_slope": recent[0].slope,
        "confirmed_evaluations": confirmation if confirmed else 0,
    }


def crossover(left, right, transitions: int, direction: str) -> dict:
    a, b = window(left, transitions + 1), window(right, transitions + 1)
    diff = a - b
    if direction == "up":
        crosses = (diff[:-1] <= 0) & (diff[1:] > 0)
    elif direction == "down":
        crosses = (diff[:-1] >= 0) & (diff[1:] < 0)
    else:
        raise ValueError("Crossover direction must be up or down")
    positions = np.flatnonzero(crosses)
    return {"cross_up" if direction == "up" else "cross_down": bool(len(positions)),
            "crossovers": int(len(positions)),
            "sessions_since_crossover": int(transitions - 1 - positions[-1]) if len(positions) else None}
