"""Rule evaluation and three-valued nested boolean logic."""
from dataclasses import dataclass, field
import math
import operator

import pandas as pd

from .metrics import (
    InsufficientData, crossover, pct_acceleration, slope_acceleration,
    trend_metrics, turning_up, window,
)
from .models import REGRESSION_METHODS, RELATION_METHODS, Rule, ScreenConfig

COMPARISONS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
               "==": operator.eq, "!=": operator.ne}


def compare(value: float, op: str, threshold: float) -> bool:
    # Treat rounded nonzero boundaries consistently across all six operators.
    # Zero remains exact so a genuinely tiny upward/downward slope keeps its direction.
    equal = math.isclose(value, threshold, rel_tol=1e-10, abs_tol=0.0)
    if op == "==":
        return equal
    if op == "!=":
        return not equal
    if equal:
        return op in {">=", "<="}
    return COMPARISONS[op](value, threshold) or (equal and op in {">=", "<="})


def primary_metrics(config, results):
    candidates = [r for r in config.rules if r.enabled and r.ma != "PRICE"]
    candidates.sort(key=lambda r: r.method in RELATION_METHODS)
    return next((results[r.id].metrics for r in candidates if results[r.id].valid
                 and "normalized_slope" in results[r.id].metrics), {})


@dataclass
class RuleResult:
    rule_id: str
    passed: bool = False
    valid: bool = True
    value: float | None = None
    reason: str = ""
    metrics: dict = field(default_factory=dict)
    window_start: pd.Timestamp | None = None
    window_end: pd.Timestamp | None = None

    @property
    def state(self) -> bool | None:
        return self.passed if self.valid else None


def evaluate_rule(frame: pd.DataFrame, rule: Rule) -> RuleResult:
    result = RuleResult(rule.id)
    try:
        series = frame[rule.ma]
        full = window(series, rule.observation_count)
        n = rule.lookback
        # For acceleration/reversal also report the latest component's metrics.
        if rule.method in {"accel_pct"}:
            analyzed = full[-(n + 1):]
        elif rule.method in {"accel_slope", "turn_up"}:
            analyzed = full[-n:]
        else:
            analyzed = full
        metrics = trend_metrics(analyzed)
        method = rule.method
        if method == "net_increase":
            metrics["net_increase"] = metrics["pct_change"]
        elif method == "accel_pct":
            metrics.update(pct_acceleration(full, n))
        elif method == "accel_slope":
            metrics.update(slope_acceleration(full, n))
        elif method == "turn_up":
            # threshold is a minimum normalized slope, with a separate boolean condition.
            metrics.update(turning_up(full, n, rule.reversal_lag, rule.confirmation,
                                      rule.threshold, rule.allow_flat))
        elif method in RELATION_METHODS:
            other = window(frame[rule.other], rule.observation_count)
            separation = 100 * (full / other - 1)
            metrics["relative"] = float(separation[-1])
            metrics["other_start"] = float(other[0])
            metrics["other_end"] = float(other[-1])
            if method == "separation_change":
                metrics["separation_change"] = float(abs(separation[-1]) - abs(separation[0]))
            elif method in {"cross_up", "cross_down"}:
                metrics.update(crossover(full, other, n, "up" if method == "cross_up" else "down"))
        value = float(metrics[method])
        result.metrics = metrics
        result.value = value
        result.window_start = frame.index[-rule.observation_count]
        result.window_end = frame.index[-1]
        if not math.isfinite(value):
            raise InsufficientData("Requested metric is undefined (for example, R-squared for a flat line)")
        passed = compare(value, rule.operator, 1.0 if method == "turn_up" else rule.threshold)
        if method == "net_increase":
            passed = passed and metrics["end"] > metrics["start"]
        if rule.min_r2 is not None:
            r2 = metrics.get("r2", math.nan)
            if not math.isfinite(r2):
                raise InsufficientData("R-squared is undefined for this window")
            passed = passed and r2 >= rule.min_r2
        if rule.min_positive_pct is not None:
            pct = metrics["positive_pct"]
            if not math.isfinite(pct):
                raise InsufficientData("No daily transitions for consistency filter")
            passed = passed and pct >= rule.min_positive_pct
        if method in {"accel_pct", "accel_slope"}:
            current_key = "current_change" if method == "accel_pct" else "current_normalized_slope"
            previous_key = "previous_change" if method == "accel_pct" else "previous_normalized_slope"
            if rule.positive_current:
                passed = passed and metrics[current_key] > 0
            if rule.positive_previous:
                passed = passed and metrics[previous_key] > 0
        result.passed = bool(passed)
        result.reason = f"{value:.8g} {rule.operator} {1 if method == 'turn_up' else rule.threshold:g}"
    except (InsufficientData, KeyError, IndexError) as exc:
        result.valid, result.passed, result.reason = False, False, str(exc)
    return result


def combine(config: ScreenConfig, results: dict[str, RuleResult]) -> bool | None:
    """Unknown never becomes true. In OR groups an independently passing rule can suffice."""
    groups = {g.id: g for g in config.groups}

    def visit(group_id):
        states = [results[r.id].state for r in config.rules if r.enabled and r.group == group_id]
        for group in config.groups:
            if group.parent == group_id:
                populated, state = visit(group.id)
                if populated:
                    states.append(state)
        if not states:
            return False, None  # Empty groups are ignored.
        if groups[group_id].logic == "AND":
            state = False if False in states else (None if None in states else True)
        else:
            state = True if True in states else (None if None in states else False)
        return True, state

    return visit("root")[1]


def window_description(rule: Rule) -> str:
    n = rule.lookback
    if rule.method == "relative":
        return "Latest completed session"
    if rule.method == "accel_slope":
        return f"Two consecutive non-overlapping windows of {n} observations ({2*n} total)"
    if rule.method == "accel_pct":
        return f"Two {n}-transition windows sharing their boundary ({2*n+1} observations)"
    if rule.method == "turn_up":
        return (f"{n}-observation regression now and {rule.reversal_lag} sessions ago; "
                f"{rule.confirmation} positive evaluations")
    if rule.method in REGRESSION_METHODS:
        return f"{n} observations, {n-1} transitions"
    return f"{n} daily transitions, {n+1} observations"
