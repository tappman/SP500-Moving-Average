"""Independent closed-form cases for risk ratios and excess-return regressions."""
from dataclasses import replace
from io import BytesIO
import json
import math
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

from trend_screener.engine import screen
from trend_screener.exports import excel_bytes, history_zip
from trend_screener.models import MovingAverage, Rule, ScreenConfig
from trend_screener.risk import RISK_METRICS, RiskSettings, risk_report, rolling_metrics
from trend_screener.universe import custom_universe


def price_series(returns, dates=None):
    closes = np.r_[100.0, 100 * np.cumprod(1 + np.asarray(returns))]
    if dates is None:
        dates = pd.bdate_range("2024-01-02", periods=len(closes))
    return pd.Series(closes, index=dates)


def test_sharpe_sortino_drawdown_and_cagr_closed_form():
    p = price_series([-.02, .01, .03, .02])
    report = risk_report(p, None, 4, RiskSettings(annualization=4))
    v = report.values
    # Mean = .01; sum of squared deviations from mean = .0014.
    assert v["sharpe_daily"] == pytest.approx(.01 / math.sqrt(.0014 / 3))
    assert v["sharpe"] == pytest.approx(.02 / math.sqrt(.0014 / 3))
    # Downside RMS uses ALL 4 observations: sqrt(.02²/4) = .01.
    assert v["sortino"] == pytest.approx(2)
    assert v["downside_deviation_ann_pct"] == pytest.approx(2)
    assert v["total_return_pct"] == pytest.approx(3.988388)
    assert v["cagr_pct"] == pytest.approx(3.988388)
    assert v["max_drawdown_pct"] == pytest.approx(2)
    assert v["calmar"] == pytest.approx(1.994194)
    assert v["mean_return_ann_pct"] == pytest.approx(4)
    assert v["positive_days_pct"] == 75
    assert report.available_returns == 4


def test_effective_annual_risk_free_rate_is_converted_before_sharpe():
    settings = RiskSettings(annualization=4, risk_free_pct=100 * (1.01**4 - 1))
    assert settings.daily_rate(settings.risk_free_pct) == pytest.approx(.01)
    v = risk_report(price_series([-.02, .01, .03, .02]), None, 4, settings).values
    assert v["sharpe"] == pytest.approx(0, abs=1e-12)
    assert v["sortino"] == pytest.approx(0, abs=1e-12)


def test_sortino_custom_target_changes_both_numerator_and_downside():
    settings = RiskSettings(annualization=4, sortino_target="custom",
                            target_return_pct=100 * (1.005**4 - 1))
    v = risk_report(price_series([-.02, .01, .03, .02]), None, 4, settings).values
    # Target-adjusted mean .005; downside RMS .025/2 = .0125.
    assert v["sortino"] == pytest.approx(.8)
    assert v["sharpe"] == pytest.approx(.02 / math.sqrt(.0014 / 3))


def test_beta_and_excess_alpha_known_linear_relationship():
    b = np.array([-.01, 0, .01, .02, -.02, .005])
    rf = .001
    r = rf + .002 + 1.5 * (b - rf)
    settings = RiskSettings(risk_free_pct=100 * ((1 + rf)**252 - 1))
    stock, benchmark = price_series(r), price_series(b)
    # Reverse the benchmark index: positional comparisons would be wrong.
    report = risk_report(stock, benchmark.iloc[::-1], 6, settings)
    assert report.values["beta"] == pytest.approx(1.5)
    assert report.values["alpha_daily_pct"] == pytest.approx(.2)
    assert report.values["alpha_ann_pct"] == pytest.approx(50.4)
    assert report.values["correlation"] == pytest.approx(1)
    assert report.values["regression_r2"] == pytest.approx(1)
    assert report.benchmark_returns == 6


def test_negative_beta_and_no_forced_positive_alpha():
    b = np.array([-.02, .01, .03, -.01])
    r = -.75 * b - .001
    v = risk_report(price_series(r), price_series(b), 4, RiskSettings()).values
    assert v["beta"] == pytest.approx(-.75)
    assert v["alpha_ann_pct"] == pytest.approx(-25.2)
    assert v["correlation"] == pytest.approx(-1)
    assert v["regression_r2"] == pytest.approx(1)


def test_identical_asset_and_benchmark():
    p = price_series([-.02, .01, .03, .02])
    v = risk_report(p, p, 4, RiskSettings()).values
    assert v["beta"] == pytest.approx(1)
    assert v["alpha_ann_pct"] == pytest.approx(0, abs=1e-12)
    assert v["tracking_error_ann_pct"] == pytest.approx(0)
    assert math.isnan(v["information_ratio"])
    assert v["active_return_pp"] == pytest.approx(0)


def test_tracking_error_and_information_ratio_closed_form():
    b = np.array([-.02, .01, .03, .02])
    v = risk_report(price_series(2 * b), price_series(b), 4, RiskSettings(annualization=4)).values
    assert v["tracking_error_ann_pct"] == pytest.approx(200 * math.sqrt(.0014 / 3))
    assert v["information_ratio"] == pytest.approx(.02 / math.sqrt(.0014 / 3))
    assert v["beta"] == pytest.approx(2)


@pytest.mark.parametrize("returns", [[0, 0, 0, 0], [.01, .01, .01, .01]])
def test_zero_volatility_never_returns_infinite_sharpe(returns):
    p = price_series(returns)
    report = risk_report(p, p, 4, RiskSettings())
    for name in ("sharpe", "sharpe_daily", "sortino", "beta", "alpha_ann_pct",
                 "calmar", "information_ratio"):
        assert math.isnan(report.values[name]), name
    assert not any(np.isinf(v) for v in report.values.values())


def test_flat_stock_against_variable_benchmark_has_zero_beta_and_undefined_r2():
    v = risk_report(price_series([0, 0, 0, 0]), price_series([-.02, .01, .03, .02]),
                    4, RiskSettings()).values
    assert v["beta"] == pytest.approx(0)
    assert v["alpha_ann_pct"] == pytest.approx(0)
    assert math.isnan(v["regression_r2"])
    assert math.isnan(v["correlation"])


def test_all_losses_give_negative_sharpe_sortino_and_calmar():
    v = risk_report(price_series([-.02, -.01, -.03, -.04]), None, 4, RiskSettings()).values
    assert all(v[m] < 0 for m in ("sharpe", "sortino", "calmar", "cagr_pct"))
    assert v["positive_days_pct"] == 0


@pytest.mark.parametrize("missing", [0, 2, 4])
def test_stock_gap_makes_entire_requested_window_unavailable(missing):
    p = price_series([-.02, .01, .03, .02])
    p.iloc[missing] = np.nan
    report = risk_report(p, None, 4, RiskSettings())
    assert report.available_returns < 4
    assert all(math.isnan(v) for v in report.values.values())
    assert report.notes


def test_insufficient_history_and_nonfinite_prices():
    p = price_series([.01, .02])
    assert all(math.isnan(v) for v in risk_report(p, None, 4, RiskSettings()).values.values())
    for invalid in (np.inf, -1, 0, "bad"):
        p = price_series([.01, .02, -.01, .01]).astype(object)
        p.iloc[1] = invalid
        assert math.isnan(risk_report(p, None, 4, RiskSettings()).values["sharpe"])


def test_missing_benchmark_does_not_erase_stock_only_metrics():
    p = price_series([-.02, .01, .03, .02])
    b = p.copy()
    b.iloc[2] = np.nan
    report = risk_report(p, b, 4, RiskSettings())
    assert np.isfinite(report.values["sharpe"])
    assert np.isfinite(report.values["max_drawdown_pct"])
    assert math.isnan(report.values["beta"])
    assert math.isnan(report.values["alpha_ann_pct"])
    assert "benchmark unavailable" in report.status


def test_last_window_has_exactly_n_returns_n_plus_one_closes():
    p = price_series([.5, -.5, -.02, .01, .03, .02])
    report = risk_report(p, None, 4, RiskSettings(annualization=4))
    assert report.values["total_return_pct"] == pytest.approx(3.988388)
    assert report.available_returns == 4
    assert report.start_date == str(p.index[-5].date())
    assert report.end_date == str(p.index[-1].date())


def test_rolling_metrics_equal_final_scalar_estimates_and_keep_gaps():
    b = np.array([-.02, .01, .03, .02, -.01, .005, .012, -.008])
    p, bm = price_series(.0005 + 1.2 * b), price_series(b)
    settings = RiskSettings(risk_free_pct=3.0)
    rolling = rolling_metrics(p, bm, 4, settings)
    scalar = risk_report(p, bm, 4, settings)
    for m in ("sharpe", "sortino", "beta", "alpha_ann_pct", "volatility_ann_pct"):
        assert rolling[m].iloc[-1] == pytest.approx(scalar.values[m])
        assert rolling[m].iloc[:4].isna().all()
    p.iloc[-2] = np.nan
    assert rolling_metrics(p, bm, 4, settings).iloc[-1].isna().all()


@pytest.mark.parametrize("kwargs", [
    {"lookbacks": [0]}, {"lookbacks": [1]}, {"lookbacks": [True]}, {"lookbacks": [2.5]},
    {"lookbacks": [63, 63]}, {"lookbacks": []}, {"risk_free_pct": -100},
    {"target_return_pct": float("nan")}, {"annualization": 0}, {"annualization": 367},
    {"benchmark": "../bad"}, {"metrics": ["made_up"]}, {"metrics": []},
])
def test_risk_settings_validation(kwargs):
    with pytest.raises(ValueError):
        RiskSettings(**kwargs).validate()


def test_old_presets_load_and_risk_settings_roundtrip():
    old = {"moving_averages": [{"kind": "SMA", "period": 20}]}
    cfg = ScreenConfig.from_dict(old)
    assert cfg.risk.lookbacks == [63, 126, 252]
    cfg.risk = RiskSettings(lookbacks=[7, 37, 127], benchmark="QQQ", risk_free_pct=4.5,
                            sortino_target="custom", target_return_pct=2.0)
    assert ScreenConfig.from_json(cfg.to_json()).risk == cfg.risk
    assert cfg.required_history() >= 128
    cfg.risk.lookbacks = [504]
    assert cfg.required_history() >= 505
    cfg.risk.enabled = False
    assert cfg.required_history() < 505


def test_historical_risk_metrics_never_use_future_stock_or_benchmark_prices(make_bars):
    r = np.tile([-.02, .01, .03, .02], 20)
    stock = make_bars(100 * np.cumprod(1 + r))
    benchmark = make_bars(100 * np.cumprod(1 + r / 2))
    end = stock.index[39].date()
    cfg = ScreenConfig(moving_averages=[MovingAverage(period=1)],
                       rules=[Rule(ma="SMA1", lookback=4)],
                       risk=RiskSettings(lookbacks=[4, 20]))
    u = custom_universe(["TEST"])
    run = screen(u, {"TEST": stock, "SPY": benchmark}, cfg, end)
    changed_s, changed_b = stock.copy(), benchmark.copy()
    changed_s.iloc[40:] = 1e10
    changed_b.iloc[40:] = .0001
    rerun = screen(u, {"TEST": changed_s, "SPY": changed_b}, cfg, end)
    pd.testing.assert_frame_equal(run.table, rerun.table)
    assert run.benchmark.index.max().date() == end
    assert run.risk_reports["TEST"][20].available_returns == 20


def test_risk_ignores_ma_price_basis_and_log_display_and_exports_benchmark(make_bars):
    stock = make_bars(100 * np.cumprod(1 + np.tile([-.02, .01, .03, .02], 10)))
    stock["close"] *= 3
    bm = make_bars(100 * np.cumprod(1 + np.tile([-.01, .005, .015, .01], 10)))
    cfg = ScreenConfig(moving_averages=[MovingAverage(period=1)],
                       rules=[Rule(ma="SMA1", lookback=4)], risk=RiskSettings(lookbacks=[4]))
    end = stock.index[-1].date()
    u = custom_universe(["TEST"])
    run = screen(u, {"TEST": stock, "SPY": bm}, cfg, end)
    other = replace(cfg, return_kind="log", price_source="close")
    rerun = screen(u, {"TEST": stock, "SPY": bm}, other, end)
    pd.testing.assert_frame_equal(run.table.filter(like="risk_"), rerun.table.filter(like="risk_"))
    with ZipFile(BytesIO(history_zip(run))) as archive:
        assert "benchmark_SPY.csv" in archive.namelist()
        assert "risk_4_sharpe" in pd.read_csv(archive.open("screen_results.csv"))
        assert json.loads(archive.read("configuration.json"))["risk"]["risk_free_pct"] == 0
    assert "risk_4_beta" in pd.read_excel(BytesIO(excel_bytes(run.table)))


def test_risk_cache_reuses_parameters_but_invalidates_rf_benchmark_and_prices(make_bars):
    p = make_bars(100 * np.cumprod(1 + np.tile([-.02, .01, .03, .02], 10)))
    cfg = ScreenConfig(moving_averages=[MovingAverage(period=1)],
                       rules=[Rule(ma="SMA1", lookback=4)], risk=RiskSettings(lookbacks=[4]))
    u, cache = custom_universe(["TEST"]), {}
    end = p.index[-1].date()
    screen(u, {"TEST": p, "SPY": p}, cfg, end, risk_cache=cache)
    cfg.rules[0].threshold = 100
    screen(u, {"TEST": p, "SPY": p}, cfg, end, risk_cache=cache)
    assert len(cache) == 1
    cfg.risk.risk_free_pct = 5
    screen(u, {"TEST": p, "SPY": p}, cfg, end, risk_cache=cache)
    assert len(cache) == 2
    changed = p.copy()
    changed.loc[changed.index[-1], "adj_close"] *= 1.1
    screen(u, {"TEST": p, "SPY": changed}, cfg, end, risk_cache=cache)
    assert len(cache) == 3
    cfg.risk.enabled = False
    disabled = screen(u, {"TEST": p}, cfg, end)
    assert not disabled.risk_reports and not any(c.startswith("risk_") for c in disabled.table)
    assert set(RISK_METRICS) <= set(next(iter(cache.values()))[4].values)
