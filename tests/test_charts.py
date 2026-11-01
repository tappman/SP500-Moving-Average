from datetime import date

import numpy as np

from trend_screener.charts import information_panel, price_chart
from trend_screener.indicators import add_indicators
from trend_screener.models import MovingAverage, Rule, ScreenConfig
from trend_screener.rules import evaluate_rule


def test_regression_chart_highlights_exact_observation_window(make_bars):
    config = ScreenConfig(moving_averages=[MovingAverage(period=1)],
                          rules=[Rule(id="trend", ma="SMA1", lookback=10)])
    frame = add_indicators(make_bars(np.arange(100, 140)), config.moving_averages)
    rule = config.rules[0]
    result = evaluate_rule(frame, rule)
    fig = price_chart(frame, "TEST", config, date(2024, 1, 1), rule, result)
    fit = next(t for t in fig.data if t.name == "Current fitted trend")
    segment = next(t for t in fig.data if t.name == "Analyzed: SMA1")
    assert len(segment.x) == len(fit.x) == 10
    assert segment.x[0] == frame.index[-10]
    assert segment.x[-1] == frame.index[-1]
    np.testing.assert_allclose(fit.y, np.arange(130, 140))
    assert fig.layout.shapes[0].x0 == frame.index[-10]
    panel = information_panel(rule, result).set_index("Metric")["Value"]
    assert panel["Start MA value"] == "130"
    assert panel["End MA value"] == "139"
    assert panel["Raw slope / session"] == "1"
    assert panel["Final result"] == "PASS"
    assert "NaN" not in fig.to_json()


def test_net_and_strict_charts_use_one_more_observation(make_bars):
    config = ScreenConfig(moving_averages=[MovingAverage(period=1)])
    frame = add_indicators(make_bars(np.arange(100, 140)), config.moving_averages)
    for method in ("pct_change", "strict"):
        rule = Rule(ma="SMA1", method=method, lookback=10)
        result = evaluate_rule(frame, rule)
        fig = price_chart(frame, "TEST", config, date(2024, 1, 1), rule, result)
        segment = next(t for t in fig.data if t.name == "Analyzed: SMA1")
        transitions = next(t for t in fig.data if t.name == "Daily transitions")
        assert len(segment.x) == 11
        assert len(transitions.x) == 10
        assert segment.x[0] == frame.index[-11]


def test_slope_acceleration_shows_both_nonoverlapping_regressions(make_bars):
    config = ScreenConfig(moving_averages=[MovingAverage(period=1)])
    frame = add_indicators(make_bars(np.arange(100, 140)), config.moving_averages)
    rule = Rule(ma="SMA1", method="accel_slope", lookback=5)
    result = evaluate_rule(frame, rule)
    fig = price_chart(frame, "TEST", config, date(2024, 1, 1), rule, result)
    previous = next(t for t in fig.data if t.name == "Previous fitted trend")
    current = next(t for t in fig.data if t.name == "Current fitted trend")
    assert len(previous.x) == len(current.x) == 5
    assert max(previous.x) < min(current.x)
