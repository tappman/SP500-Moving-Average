from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from trend_screener.engine import ScreenRun
from trend_screener.history import HistoryStore, definition_hash
from trend_screener.membership import MembershipHistory
from trend_screener.models import MovingAverage, Rule, ScreenConfig
from trend_screener.portfolio import analyze_portfolio
from trend_screener.risk import RiskSettings
from trend_screener.robustness import engine_slice, evaluate_frozen_holdout, robustness_trials
from trend_screener.studies import (
    BacktestSettings, StudyEngine, backtest, cohort_study, frozen_plan, parameter_neighbors,
)
from trend_screener.universe import custom_universe


def config():
    return ScreenConfig(moving_averages=[MovingAverage(period=1)],
                        rules=[Rule(id="rise", ma="SMA1", lookback=2)], risk=RiskSettings(enabled=False))


def market(make_bars, n=30):
    p = 100 * 1.01 ** np.arange(n)
    a = make_bars(p)
    # Raw bars are twice adjusted levels; each next open is the prior adjusted close.
    a["open"] = np.r_[p[0], p[:-1]] * 2
    a["close"] = p * 2
    b = make_bars(100 * .99 ** np.arange(n))
    return {"A": a, "B": b, "SPY": a.copy()}


def engine_for(prices, cfg=None, universe=None, **kwargs):
    idx = prices["A"].index
    return StudyEngine(prices, universe if universe is not None else custom_universe(["A", "B"]),
                       cfg or config(), idx[2].date(), idx[-1].date(), **kwargs)


def test_membership_boundaries_removed_members_and_persistence(tmp_path):
    text = "ticker,start_date,end_date,sector\nBRK.B,2023-01-01,2024-01-10,Finance\nNEW,2024-01-10,,Tech\n"
    m = MembershipHistory.from_csv(text, date(2023, 1, 1), date(2024, 12, 31), "Test source")
    assert m.at(date(2024, 1, 9)).ticker.tolist() == ["BRK-B"]
    assert m.at(date(2024, 1, 10)).ticker.tolist() == ["NEW"]
    assert set(m.universe(date(2024, 1, 9), date(2024, 1, 10)).ticker) == {"BRK-B", "NEW"}
    with pytest.raises(ValueError, match="covers"):
        m.at(date(2025, 1, 1))
    m.save(tmp_path)
    assert MembershipHistory.load(tmp_path).digest == m.digest


@pytest.mark.parametrize("rows", [
    "A,2024-01-01,2024-02-01\nA,2024-01-20,2024-03-01",
    "A,2024-01-01,\nA,2025-01-01,",
    "A,2024-01-01,2023-01-01",
    ",2024-01-01,",
    "A,bad,",
])
def test_membership_rejects_bad_intervals(rows):
    with pytest.raises(ValueError):
        MembershipHistory.from_csv("ticker,start_date,end_date\n" + rows,
                                   date(2023, 1, 1), date(2025, 12, 31), "Test")


def test_history_daily_changes_missing_is_separate_and_definition_is_stable(tmp_path):
    store, cfg = HistoryStore(tmp_path), config()
    def save(day, a, b, value=.1):
        table = pd.DataFrame([{"ticker": "A", "status": a, "rise.pass": a == "PASS", "rise.value": value},
                              {"ticker": "B", "status": b, "rise.pass": b == "PASS", "rise.value": .1}])
        return store.save_screen(ScreenRun(cfg, day, table))
    first = save(date(2024, 1, 2), "FAIL", "PASS")
    second = save(date(2024, 1, 3), "PASS", "INSUFFICIENT")
    prior, changes = store.compare(second)
    assert prior["id"] == first
    result = changes.set_index("ticker")
    assert result.loc["A", "change"] == "Newly qualifying"
    assert result.loc["B", "change"] == "Now unavailable"
    assert "FAIL → PASS" in result.loc["A", "changed_rules"]
    third = save(date(2024, 1, 3), "PASS", "FAIL")
    assert store.compare(third)[0]["id"] == first  # Same-day rerun is not another trading day.
    fourth = save(date(2024, 1, 4), "PASS", "FAIL")
    assert store.compare(fourth)[1].set_index("ticker").loc["A", "consecutive_saved_sessions"] == 2
    clone = ScreenConfig.from_dict(cfg.to_dict())
    clone.name = "Renamed"
    clone.moving_averages[0].show = False
    clone.risk.risk_free_pct = 4
    assert definition_hash(clone) == definition_hash(cfg)
    clone.rules[0].threshold = 2
    assert definition_hash(clone) != definition_hash(cfg)


def test_experiment_ledger_preserves_frozen_copy(tmp_path):
    store = HistoryStore(tmp_path)
    plan = {"config": config().to_dict()}
    identifier = store.record_experiment("freeze", plan)
    plan["config"]["rules"][0]["threshold"] = 999
    assert store.experiment(identifier)["plan"]["config"]["rules"][0]["threshold"] == 0
    store.complete_experiment(identifier, {"test": "completed"})
    assert store.experiment(identifier)["result"] == {"test": "completed"}


def test_signals_are_causal_and_use_dated_membership(make_bars):
    prices = market(make_bars)
    engine = engine_for(prices)
    day = engine.dates[2]
    original = engine.signals(day)
    prices["A"].loc[prices["A"].index > day, "adj_close"] = 1
    changed = engine_for(prices)
    pd.testing.assert_frame_equal(changed.signals(day), original)
    cutoff = str(engine.dates[4].date())
    m = MembershipHistory.from_csv(f"ticker,start_date,end_date\nA,2020-01-01,{cutoff}\nB,{cutoff},\n",
                                   engine.start, engine.end, "Synthetic")
    historical = engine_for(prices, membership=m)
    assert historical.signals(engine.dates[0]).ticker.tolist() == ["A"]
    assert historical.signals(engine.dates[4]).ticker.tolist() == ["B"]


def test_next_open_cohort_uses_adjusted_open_costs_and_exact_horizon(make_bars):
    e = engine_for(market(make_bars))
    day = e.dates[0]
    assert e.outcome("A", day, 5, 0)[0] == pytest.approx(100 * (1.01**5 - 1))
    assert e.outcome("A", day, 5, 10)[0] == pytest.approx(100 * (1.01**5 * .999 / 1.001 - 1))
    assert np.isnan(e.outcome("A", e.dates[-2], 5)[0])
    result = cohort_study(e, horizons=(5,), every=5, cost_bps=0)
    assert result.summary.available_outcomes.iloc[0] > 0
    assert (result.by_date.qualifier_minus_nonqualifier_pp.dropna() > 0).all()
    assert result.by_date.qualifier_minus_benchmark_pp.dropna().abs().max() < 1e-10
    assert set(result.observations.status) == {"PASS", "FAIL"}


def test_cohort_missing_closes_and_unknown_signals_do_not_become_zero(make_bars):
    prices = market(make_bars)
    prices["A"].loc[prices["A"].index[5], "adj_close"] = np.nan
    e = engine_for(prices)
    value, why = e.outcome("A", e.dates[0], 5)
    assert np.isnan(value) and "Missing" in why
    assert e.signals(prices["A"].index[5]).set_index("ticker").loc["A", "status"] == "INSUFFICIENT"


@pytest.mark.parametrize("threshold", [-1000.0, 1000.0])
def test_cohort_handles_dates_without_qualifiers_or_controls(make_bars, threshold):
    cfg = config()
    cfg.rules[0].threshold = threshold
    result = cohort_study(engine_for(market(make_bars), cfg), horizons=(5,), every=5)
    assert len(result.summary) == 1
    assert result.by_date.sector_matched_count.eq(0).all()
    assert result.by_date.sector_matched_excess_pp.isna().all()


def test_cohort_reports_empty_historical_universe_dates(make_bars):
    e = engine_for(market(make_bars))
    starts = e.dates[-3].date()
    membership = MembershipHistory.from_csv(
        f"ticker,start_date,end_date\nA,{starts},\n", e.start, e.end, "Late membership")
    e = engine_for(e.prices, membership=membership)
    result = cohort_study(e, horizons=(5,), every=100)
    assert result.observations.empty
    assert result.summary.signal_dates.iloc[0] == 1
    assert result.summary.dates_with_empty_universe.iloc[0] == 1


def test_backtest_next_open_hold_costs_nav_and_benchmark(make_bars):
    e = engine_for(market(make_bars, 10))
    settings = BacktestSettings(max_positions=1, holding_sessions=3, review_every=100,
                                commission_bps=10, slippage_bps=20, exit_on_fail=False)
    result = backtest(e, settings)
    trade = result.trades.iloc[0]
    assert trade.signal_date == e.dates[0] and trade.entry_date == e.dates[1]
    assert trade.exit_date == e.dates[3]
    expected = 1.01**3 * (.998 * .999) / (1.002 * 1.001)
    assert result.equity.equity.iloc[-1] == pytest.approx(100000 * expected)
    assert trade.net_return_pct == pytest.approx(100 * (expected - 1))
    assert result.trades.total_cost.sum() > 0 and result.equity.cash.min() >= -1e-8
    assert result.report.values["total_return_pct"] == pytest.approx(100 * (expected - 1))


def test_backtest_missing_held_price_aborts_and_bad_entry_is_canceled(make_bars):
    p = market(make_bars, 15)
    p["A"].loc[p["A"].index[5], "adj_close"] = np.nan
    with pytest.raises(ValueError, match="Held position A"):
        backtest(engine_for(p), BacktestSettings(max_positions=1, holding_sessions=20))
    p = market(make_bars, 15)
    p["A"].loc[p["A"].index[3], "open"] = np.nan
    result = backtest(engine_for(p), BacktestSettings(max_positions=1, review_every=100))
    assert result.trades.empty and result.orders.status.tolist() == ["CANCELED"]


def test_fail_exit_waits_for_next_open_and_forced_end_costs(make_bars):
    p = market(make_bars, 12)
    p["A"].loc[p["A"].index[5]:, "adj_close"] = 20
    e = engine_for(p)
    result = backtest(e, BacktestSettings(max_positions=1, review_every=1, holding_sessions=20))
    first = result.trades.iloc[0]
    assert first.exit_date == p["A"].index[6]
    assert first.exit_at == "adj_open"
    result = backtest(engine_for(market(make_bars, 12)), BacktestSettings(holding_sessions=100))
    assert result.trades.reason.iloc[-1] == "Study end"
    assert result.equity.positions.iloc[-1] == 0


def test_neighbors_and_freeze_keep_base_immutable(make_bars):
    e = engine_for(market(make_bars))
    cfg = e.config
    variants = parameter_neighbors(cfg, "SMA1", "rise")
    assert len(variants) == 5
    assert variants[1][1] is None  # Period zero is skipped, not silently clamped.
    assert variants[2][1].rules[0].ma == "SMA2"
    assert cfg.moving_averages[0].period == 1
    plan = frozen_plan(cfg, BacktestSettings(), e, e.dates[10].date())
    cfg.rules[0].threshold = 99
    assert plan["config"]["rules"][0]["threshold"] == 0


def test_holdout_uses_frozen_rules_records_trials_and_rejects_changed_prices(make_bars, tmp_path):
    e, store = engine_for(market(make_bars, 50)), HistoryStore(tmp_path)
    split = e.dates[25].date()
    settings = BacktestSettings(max_positions=1, holding_sessions=5)
    plan = frozen_plan(e.config, settings, e, split)
    frozen = store.record_experiment("frozen_holdout", plan)
    e.config.rules[0].threshold = 10000
    identifier, result = evaluate_frozen_holdout(store, frozen, e)
    assert len(result.trades) > 0  # Mutable live config fails; the frozen copy still passes.
    assert result.trades.signal_date.min().date() > split
    assert store.experiment(identifier)["plan"]["frozen_plan_id"] == frozen
    e.fingerprint = "changed"
    with pytest.raises(ValueError, match="differ"):
        evaluate_frozen_holdout(store, frozen, e)


def test_training_trials_never_include_holdout_and_all_candidates_are_recorded(make_bars, tmp_path):
    e, store = engine_for(market(make_bars, 60)), HistoryStore(tmp_path)
    split = e.dates[35].date()
    training = engine_slice(e, e.config, e.start, split)
    rows = robustness_trials(training, BacktestSettings(), "SMA1", "rise", store)
    assert len(rows) == 8 and len(store.list_experiments()) == 8
    assert rows.end.le(str(split)).all()
    assert rows.status.eq("SKIPPED").sum() == 2  # period 0 and regression lookback 1


def test_portfolio_correlations_and_variance_contributions_are_stock_to_stock(make_bars):
    changes = np.array([.01, -.02, .03, -.01, .02, -.03, .01, .02, -.01, .01])
    p = {"A": make_bars(100 * np.r_[1, np.cumprod(1 + changes)]),
         "B": make_bars(100 * np.r_[1, np.cumprod(1 - changes)])}
    result = analyze_portfolio(p, {"A": .6, "B": .4}, custom_universe(["A", "B"]),
                               p["A"].index[-1].date(), 10, RiskSettings())
    assert result.correlations.loc["A", "B"] == pytest.approx(-1)
    assert result.weights.variance_contribution_pct.sum() == pytest.approx(100)
    assert result.weights.set_index("ticker").loc["B", "variance_contribution_pct"] < 0


def test_portfolio_weighted_returns_concentration_and_sector_exposure(make_bars):
    p = market(make_bars)
    u = custom_universe(["A", "B"])
    u["sector"] = ["Tech", "Health"]
    end = p["A"].index[-1].date()
    r = analyze_portfolio(p, {"A": .5, "B": .25}, u, end, 10, RiskSettings(), p["SPY"].adj_close)
    expected = .5 * .01 + .25 * -.01
    assert r.equity.portfolio.iloc[-1] == pytest.approx((1 + expected)**10)
    assert r.concentration["cash_weight_pct"] == pytest.approx(25)
    assert r.concentration["effective_stock_holdings"] == pytest.approx(1 / ((2 / 3)**2 + (1 / 3)**2))
    assert r.sectors.weight_pct.sum() == pytest.approx(100)


def test_portfolio_requires_common_complete_window_but_ignores_zero_weight(make_bars):
    p = market(make_bars)
    end = p["A"].index[-1].date()
    p["B"].loc[p["B"].index[-4], "adj_close"] = np.nan
    with pytest.raises(ValueError, match="incomplete: B"):
        analyze_portfolio(p, {"A": .5, "B": .5}, custom_universe(["A", "B"]), end, 10, RiskSettings())
    result = analyze_portfolio(p, {"A": 1.0, "B": 0}, custom_universe(["A", "B"]), end, 10, RiskSettings())
    assert result.weights.ticker.tolist() == ["A"]
    with pytest.raises(ValueError, match="100%"):
        analyze_portfolio(p, {"A": 1.1}, custom_universe(["A"]), end, 10, RiskSettings())


def test_zero_cash_return_and_validation(make_bars):
    e = engine_for(market(make_bars))
    e.config.rules[0].threshold = 1000
    # Rebuild because the engine owns cached signals and the applied config.
    e = engine_for(market(make_bars), e.config)
    result = backtest(e, BacktestSettings(cash_rate_pct=0))
    assert result.equity.equity.eq(100000).all()
    assert np.isnan(result.report.values["sharpe"])
    with pytest.raises(ValueError):
        backtest(e, replace(BacktestSettings(), max_positions=0))
