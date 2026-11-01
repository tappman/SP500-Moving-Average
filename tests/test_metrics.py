import math

import numpy as np
import pandas as pd
import pytest

from trend_screener.metrics import (
    InsufficientData, crossover, pct_acceleration, regression,
    slope_acceleration, trend_metrics, turning_up, window,
)
from trend_screener.models import Rule
from trend_screener.rules import evaluate_rule


def evaluated(values, method, lookback, **kwargs):
    return evaluate_rule(pd.DataFrame({"SMA20": values}, index=pd.bdate_range("2024-01-01", periods=len(values))),
                         Rule(ma="SMA20", method=method, lookback=lookback, **kwargs))


@pytest.mark.parametrize("values,strict,slope_up", [
    ([100, 101, 102, 103, 104], True, True),
    ([100, 102, 101, 103, 104], False, True),
    ([104, 103, 102, 101, 100], False, False),
    ([100, 100, 100, 100, 100], False, False),
])
def test_up_down_flat_and_dips(values, strict, slope_up):
    assert trend_metrics(values)["strict"] is strict
    assert (regression(values).slope > 0) == slope_up
    assert evaluated(values, "strict", 4, operator="==", threshold=1).passed is strict
    assert evaluated(values, "normalized_slope", 5).passed is slope_up


def test_positive_endpoint_negative_slope():
    values = [10, 100, 90, 80, 70, 11]
    assert evaluated(values, "net_increase", 5).passed
    assert not evaluated(values, "slope", 6).passed
    assert regression(values).slope < 0


def test_negative_endpoint_positive_slope():
    values = [100, 10, 20, 30, 40, 99]
    assert not evaluated(values, "net_increase", 5).passed
    assert evaluated(values, "slope", 6).passed
    assert trend_metrics(values)["pct_change"] < 0


def test_regression_closed_form_and_normalization():
    fit = regression([100, 102, 104, 106])
    assert fit.slope == pytest.approx(2)
    assert fit.intercept == pytest.approx(100)
    assert fit.normalized_slope == pytest.approx(200 / 103)
    assert fit.r2 == pytest.approx(1)
    assert regression([1000, 1020, 1040, 1060]).normalized_slope == pytest.approx(fit.normalized_slope)


def test_flat_r2_undefined_but_zero_slope_valid():
    fit = regression([5, 5, 5])
    assert fit.slope == 0
    assert math.isnan(fit.r2)
    slope = evaluated([5, 5, 5], "slope", 3)
    assert slope.valid and not slope.passed
    assert not evaluated([5, 5, 5], "r2", 3, threshold=.8).valid
    assert not evaluated([5, 5, 5], "slope", 3, min_r2=.5).valid


def test_observations_versus_transitions():
    values = [50, 100, 101, 102]
    assert window(values, 3).tolist() == [100, 101, 102]
    net = evaluated(values, "pct_change", 3)
    slope = evaluated(values, "slope", 3)
    assert net.metrics["observations"] == 4
    assert net.value == pytest.approx(104)
    assert slope.value == pytest.approx(1)
    assert slope.metrics["observations"] == 3
    assert evaluated([100, 101, 102], "slope", 3).valid
    assert not evaluated([100, 101, 102], "pct_change", 3).valid


def test_smoothness_metrics():
    m = trend_metrics([100, 110, 99, 108, 109, 109, 110])
    assert m["positive_count"] == 4
    assert m["negative_count"] == 1
    assert m["flat_count"] == 1
    assert m["positive_pct"] == pytest.approx(100 * 4 / 6)
    assert m["max_drawdown_pct"] == pytest.approx(10)
    assert m["longest_streak"] == 2


def test_mostly_increasing_and_combined_filter():
    y = [100, 101, 102, 103, 102.9, 104, 105, 106, 107, 106.9, 108]
    assert evaluated(y, "positive_count", 10, operator=">=", threshold=8).passed
    assert evaluated(y, "positive_pct", 10, operator=">=", threshold=80).passed
    assert evaluated(y, "normalized_slope", 11, min_positive_pct=80).passed
    assert not evaluated(y, "normalized_slope", 11, min_positive_pct=90).passed


@pytest.mark.parametrize("y", [[100, np.nan, 102], [100, np.inf, 102], [100, 0, 102], [100, -1, 102]])
def test_missing_or_invalid_never_pass(y):
    result = evaluated(y, "slope", 3, operator="!=", threshold=0)
    assert not result.valid and not result.passed and result.state is None


def test_insufficient_data():
    assert not evaluated([100, 101], "slope", 10).valid
    with pytest.raises(InsufficientData):
        regression([100])


def test_exact_minimum_and_maximum_percentage():
    y = [100, 101, 102]
    assert evaluated(y, "pct_change", 2, operator=">=", threshold=1.99).passed
    assert evaluated(y, "pct_change", 2, operator="<=", threshold=2.01).passed
    assert evaluated(y, "pct_change", 2, operator="<=", threshold=2.0).passed
    assert evaluated(y, "pct_change", 2, operator="==", threshold=2.0).passed
    assert not evaluated(y, "net_increase", 2, operator="<", threshold=0).passed


def test_acceleration_percent_windows_share_boundary():
    m = pct_acceleration([100, 100.5, 101, 102, 104], 2)
    assert m["previous_change"] == pytest.approx(1)
    assert m["current_change"] == pytest.approx(300 / 101)
    assert m["accel_pct"] == pytest.approx(300 / 101 - 1)


def test_acceleration_slope_windows_do_not_overlap():
    m = slope_acceleration([100, 101, 102, 104, 106, 108], 3)
    assert m["previous_slope"] == pytest.approx(1)
    assert m["current_slope"] == pytest.approx(2)
    assert m["accel_slope"] == pytest.approx(200 / 106 - 100 / 101)
    result = evaluated([100, 101, 102, 104, 106, 108], "accel_slope", 3, positive_previous=True)
    assert result.passed


def test_acceleration_does_not_mean_upward_if_rates_negative():
    y = [110, 108, 106, 104, 103, 102]
    assert slope_acceleration(y, 3)["accel_slope"] > 0
    assert not evaluated(y, "accel_slope", 3).passed
    assert evaluated(y, "accel_slope", 3, positive_current=False).passed


def test_turning_up_and_confirmation():
    y = [8, 7, 6, 5, 4, 5, 6, 7]
    m = turning_up(y, 3, lag=3, confirmation=2)
    assert m["turn_up"] and m["confirmed_evaluations"] == 2
    assert m["previous_normalized_slope"] < 0 < m["current_normalized_slope"]
    assert not turning_up(y, 3, lag=3, confirmation=4)["turn_up"]
    assert evaluated(y, "turn_up", 3, operator="==", reversal_lag=3, confirmation=2).passed
    assert not turning_up([5, 5, 5, 5, 6, 7], 3, lag=3, allow_flat=False)["turn_up"]
    assert turning_up([5, 5, 5, 5, 6, 7], 3, lag=3, allow_flat=True)["turn_up"]


def test_bullish_bearish_and_equal_crossovers():
    assert crossover([9, 10, 11], [10, 10, 10], 2, "up")["cross_up"]
    assert crossover([11, 10, 9], [10, 10, 10], 2, "down")["cross_down"]
    assert not crossover([9, 10, 10], [10, 10, 10], 2, "up")["cross_up"]
    result = crossover([9, 11, 12, 13], [10, 10, 10, 10], 3, "up")
    assert result["sessions_since_crossover"] == 2
    assert not crossover([9, 11, 12, 13], [10, 10, 10, 10], 1, "up")["cross_up"]
