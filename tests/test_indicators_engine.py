from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from trend_screener.engine import screen
from trend_screener.indicators import add_indicators, daily_returns, moving_average
from trend_screener.models import Group, MovingAverage, Rule, ScreenConfig
from trend_screener.rules import RuleResult, combine, evaluate_rule
from trend_screener.universe import custom_universe


def config_for(rules, **kwargs):
    return ScreenConfig(moving_averages=[MovingAverage(period=1)], rules=rules, **kwargs)


def test_arbitrary_sma_and_warmup():
    values = pd.Series(np.arange(1, 501, dtype=float))
    for n in (1, 7, 13, 37, 63, 127, 250, 300):
        ma = moving_average(values, MovingAverage(period=n))
        assert ma.iloc[:n-1].isna().all()
        assert ma.iloc[n-1] == pytest.approx((n + 1) / 2)
        assert ma.iloc[-1] == pytest.approx(500 - (n-1) / 2)


def test_ema_formula_and_reset_after_gap():
    values = pd.Series([10, 12, 14, np.nan, 16, 18, 20])
    ma = moving_average(values, MovingAverage("EMA", 3))
    assert ma.iloc[:2].isna().all()
    assert ma.iloc[2] == pytest.approx(12.5)
    assert ma.iloc[3:6].isna().all()
    assert ma.iloc[6] == pytest.approx(18.5)
    assert moving_average(values, MovingAverage(period=3)).iloc[3:6].isna().all()


def test_returns_simple_log_and_missing():
    p = pd.Series([100, 110, 121, np.nan, 133.1])
    assert daily_returns(p).iloc[1] == pytest.approx(.1)
    assert daily_returns(p, "log").iloc[1] == pytest.approx(np.log(1.1))
    assert daily_returns(p, periods=2).iloc[2] == pytest.approx(.21)
    assert daily_returns(p, periods=2).iloc[-1:].isna().all()
    assert daily_returns(p).iloc[-1:].isna().all()


def test_adjusted_and_unadjusted_never_mixed(make_bars):
    frame = make_bars([100, 110, 120])
    frame["adj_close"] = [50, 55, 60]
    result = add_indicators(frame, [MovingAverage(period=1)], "adj_close")
    assert result["SMA1"].iloc[-1] == 60
    assert result["close"].iloc[-1] == 120
    unadjusted = add_indicators(frame, [MovingAverage(period=1)], "close")
    assert unadjusted["SMA1"].iloc[-1] == 120
    assert result.return_1d.iloc[-1] == unadjusted.return_1d.iloc[-1]


def test_nested_and_or_and_unavailable():
    rules = [Rule(id="a", ma="SMA1"), Rule(id="b", ma="SMA1", group="alternative"),
             Rule(id="c", ma="SMA1", group="alternative")]
    cfg = config_for(rules, groups=[Group(), Group("alternative", "Either branch", "OR", "root")])
    cfg.validate()
    outcomes = {"a": RuleResult("a", passed=True), "b": RuleResult("b", passed=False),
                "c": RuleResult("c", passed=True)}
    assert combine(cfg, outcomes) is True
    outcomes["a"].passed = False
    assert combine(cfg, outcomes) is False
    outcomes["a"].valid = False
    assert combine(cfg, outcomes) is None
    cfg.groups[0].logic = "OR"
    assert combine(cfg, outcomes) is True
    outcomes["c"].passed = False
    assert combine(cfg, outcomes) is None


def test_disabled_rules_and_empty_groups_ignored():
    cfg = config_for([Rule(id="a", ma="SMA1"), Rule(id="b", ma="SMA1", enabled=False)],
                     groups=[Group(), Group("empty", "Unused", "OR", "root")])
    assert combine(cfg, {"a": RuleResult("a", passed=True)}) is True


def test_relationships_and_separation():
    frame = pd.DataFrame({"SMA5": [9, 10, 12], "SMA20": [10, 10, 10], "PRICE": [8, 9, 13]})
    assert evaluate_rule(frame, Rule(ma="SMA5", other="SMA20", method="relative")).passed
    assert evaluate_rule(frame, Rule(ma="PRICE", other="SMA20", method="relative")).passed
    assert evaluate_rule(frame, Rule(ma="SMA5", other="SMA20", method="cross_up",
                                     lookback=2, operator="==", threshold=1)).passed
    separation = evaluate_rule(frame, Rule(ma="SMA5", other="SMA20", method="separation_change",
                                           lookback=2))
    assert separation.value == pytest.approx(10)


def test_history_is_clipped_before_any_indicator(make_bars):
    values = np.r_[np.arange(100, 160), [1e8] * 20]
    frame = make_bars(values)
    end = frame.index[59].date()
    cfg = config_for([Rule(id="r", ma="SMA1", lookback=10)])
    run = screen(custom_universe(["TEST"]), {"TEST": frame}, cfg, end)
    assert run.table.iloc[0].passed
    assert run.frames["TEST"].index.max().date() == end
    changed = frame.copy()
    changed.iloc[60:] = .001
    rerun = screen(custom_universe(["TEST"]), {"TEST": changed}, cfg, end)
    pd.testing.assert_frame_equal(run.table, rerun.table)


def test_missing_session_not_skipped(make_bars):
    frame = make_bars(np.arange(100, 130))
    end = frame.index[-1].date()
    frame = frame.drop(frame.index[-2])
    cfg = config_for([Rule(id="r", ma="SMA1", lookback=5)])
    run = screen(custom_universe(["TEST"]), {"TEST": frame}, cfg, end)
    assert run.table.iloc[0].status == "INSUFFICIENT"
    assert not run.table.iloc[0].passed


def test_missing_latest_session_no_stale_substitution(make_bars):
    frame = make_bars(np.arange(100, 130))
    end = frame.index[-1].date()
    cfg = config_for([Rule(id="r", ma="SMA1", lookback=5)])
    run = screen(custom_universe(["TEST"]), {"TEST": frame.iloc[:-1]}, cfg, end)
    assert run.table.iloc[0].status == "INSUFFICIENT"
    assert pd.isna(run.table.iloc[0].latest_adjusted_price)


def test_empty_and_short_stocks_insufficient(make_bars):
    frame = make_bars([100, 101])
    cfg = ScreenConfig(moving_averages=[MovingAverage(period=300)],
                       rules=[Rule(ma="SMA300", lookback=20)])
    run = screen(custom_universe(["SHORT", "EMPTY"]), {"SHORT": frame}, cfg, frame.index[-1].date())
    assert run.summary()["insufficient"] == 2
    assert run.summary()["passing"] == 0


def test_indicator_cache_reuses_but_invalidates_changed_prices(make_bars):
    frame = make_bars(np.arange(100, 130))
    cfg = config_for([Rule(id="r", ma="SMA1", lookback=5)])
    cache = {}
    universe = custom_universe(["TEST"])
    end = frame.index[-1].date()
    screen(universe, {"TEST": frame}, cfg, end, indicator_cache=cache)
    assert len(cache) == 1
    cfg.rules[0] = replace(cfg.rules[0], threshold=1e6)
    run = screen(universe, {"TEST": frame}, cfg, end, indicator_cache=cache)
    assert len(cache) == 1 and not run.table.iloc[0].passed
    frame.loc[frame.index[-1], "adj_close"] = 1
    run = screen(universe, {"TEST": frame}, cfg, end, indicator_cache=cache)
    assert len(cache) == 2
    assert run.frames["TEST"]["SMA1"].iloc[-1] == 1
