"""Causal historical signals, next-open cohorts and a cost-aware long-only simulator.

This is daily-bar research, not an execution model or a point-in-time price database.
Adjusted open = raw open * adjusted close / raw close (same day's adjustment factor).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date
import hashlib
import math

import numpy as np
import pandas as pd

from .calendar import sessions
from .indicators import add_indicators
from .membership import MembershipHistory
from .models import ScreenConfig
from .risk import RiskReport, RiskSettings, numeric_prices, risk_report
from .rules import combine, evaluate_rule

RANKINGS = {
    "rank_normalized_slope": "Normalized MA slope",
    "rank_pct_change": "MA percentage change",
    "rank_r2": "MA regression R²",
    "rank_longest_streak": "MA rising streak",
    "return_20d_pct": "20-session stock return",
    "ticker": "Ticker (alphabetical)",
}


class StudyEngine:
    """Precompute causal indicators once; a signal only sees rows through its date."""
    def __init__(self, prices: dict[str, pd.DataFrame], universe: pd.DataFrame,
                 config: ScreenConfig, start: date, end: date,
                 membership: MembershipHistory | None = None):
        config.validate()
        if start > end:
            raise ValueError("Study start must precede its end")
        self.config = ScreenConfig.from_dict(config.to_dict())
        self.config.risk.enabled = False  # Risk ratios describe outcomes; never signal inputs.
        self.universe = universe.copy()
        if self.universe.ticker.duplicated().any():
            raise ValueError("Study universe must contain unique tickers")
        self.membership = membership
        if membership:
            membership.require_coverage(start, end)
        self.start, self.end = start, end
        self.dates = sessions(start, end)
        if len(self.dates) < 2:
            raise ValueError("A study needs at least two completed NYSE sessions")
        first = min([pd.Timestamp(start), *[f.index.min() for f in prices.values() if not f.empty]])
        self.index = sessions(first.date(), end)
        self.prices, self.prepared, self._signals = {}, {}, {}
        fingerprint = hashlib.sha256()
        for ticker in sorted(prices):
            frame = prices[ticker].loc[:pd.Timestamp(end)].reindex(self.index).copy()
            for col in ("open", "high", "low", "close", "adj_close", "volume"):
                frame[col] = (pd.to_numeric(frame[col], errors="coerce").astype(float)
                              if col in frame else np.nan)
            self.prices[ticker] = frame
            fingerprint.update(ticker.encode())
            fingerprint.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
            if ticker in set(universe.ticker):
                self.prepared[ticker] = add_indicators(
                    frame, self.config.moving_averages, config.price_source, "simple")
        self.fingerprint = fingerprint.hexdigest()

    def universe_at(self, day):
        return self.membership.at(pd.Timestamp(day).date()) if self.membership else self.universe

    def signals(self, day) -> pd.DataFrame:
        day = pd.Timestamp(day).normalize()
        if day not in self.dates:
            raise ValueError("Signal date is outside the study's NYSE sessions")
        if day in self._signals:
            return self._signals[day].copy()
        rows, rules = [], [r for r in self.config.rules if r.enabled]
        for company in self.universe_at(day).to_dict("records"):
            ticker = company["ticker"]
            frame = self.prepared.get(ticker)
            if frame is None:
                frame = add_indicators(pd.DataFrame(index=self.index), self.config.moving_averages,
                                       self.config.price_source, "simple")
            past = frame.loc[:day]
            results = {r.id: evaluate_rule(past, r) for r in rules}
            result = combine(self.config, results)
            # A tradable close is required even for an independently decidable OR rule.
            valid_close = not past.empty and pd.notna(numeric_prices(past.adj_close).iloc[-1])
            state = "INSUFFICIENT" if result is None or not valid_close else ("PASS" if result else "FAIL")
            primary = next((results[r.id].metrics for r in rules if r.ma != "PRICE" and results[r.id].valid), {})
            rows.append({**company, "signal_date": str(day.date()), "status": state,
                         "rules_passed": sum(e.passed for e in results.values()),
                         "return_20d_pct": float(past.return_20d.iloc[-1] * 100) if not past.empty else np.nan,
                         **{f"rank_{m}": primary.get(m, np.nan) for m in
                            ("normalized_slope", "pct_change", "r2", "longest_streak")}})
        table = pd.DataFrame(rows, columns=list(dict.fromkeys([
            *self.universe.columns, "signal_date", "status", "rules_passed", "return_20d_pct",
            "rank_normalized_slope", "rank_pct_change", "rank_r2", "rank_longest_streak"])))
        self._signals[day] = table
        return table.copy()

    def price(self, ticker, day, field="adj_close") -> float:
        frame = self.prices.get(ticker)
        if frame is None or pd.Timestamp(day) not in frame.index:
            return math.nan
        row = frame.loc[pd.Timestamp(day)]
        value = row.adj_close
        if field == "adj_open":
            if not all(np.isfinite(row.get(c, np.nan)) and row[c] > 0 for c in ("open", "close", "adj_close")):
                return math.nan
            value = row.open * row.adj_close / row.close
        return float(value) if np.isfinite(value) and value > 0 else math.nan

    def outcome(self, ticker, signal_date, horizon: int, cost_bps=0.0):
        """N full holding sessions, next session open through Nth session close."""
        if horizon < 1:
            raise ValueError("Outcome horizon must be positive")
        if not 0 <= cost_bps < 10000:
            raise ValueError("Per-side outcome costs must be in [0, 10000) bps")
        i = self.dates.get_loc(pd.Timestamp(signal_date))
        if i + horizon >= len(self.dates):
            return math.nan, "Incomplete horizon"
        period = self.dates[i + 1:i + horizon + 1]
        entry = self.price(ticker, period[0], "adj_open")
        closes = [self.price(ticker, d) for d in period]
        if not np.isfinite(entry) or not np.isfinite(closes).all():
            return math.nan, "Missing entry open or holding-period close"
        cost = cost_bps / 10000
        return 100 * ((closes[-1] * (1 - cost)) / (entry * (1 + cost)) - 1), "Available"


def ranked_qualifiers(table, ranking):
    if ranking not in RANKINGS:
        raise ValueError("Choose a supported ranking metric")
    passing = table[table.status.eq("PASS")]
    return passing.sort_values([ranking, "ticker"] if ranking != "ticker" else ["ticker"],
                               ascending=[False, True] if ranking != "ticker" else [True],
                               na_position="last")


@dataclass
class CohortResult:
    observations: pd.DataFrame
    by_date: pd.DataFrame
    summary: pd.DataFrame


def cohort_study(engine: StudyEngine, *, horizons=(5, 20, 60), every=21,
                 benchmark="SPY", cost_bps=10.0, progress=None) -> CohortResult:
    if not horizons or any(not isinstance(n, int) or n < 1 for n in horizons) or every < 1:
        raise ValueError("Choose positive integer horizons and sampling interval")
    rows, benchmarks = [], {}
    sample_dates = engine.dates[:-1:every]
    for i, day in enumerate(sample_dates):
        signals = engine.signals(day)
        for horizon in sorted(set(horizons)):
            bm, _ = engine.outcome(benchmark, day, horizon, cost_bps)
            benchmarks[(day, horizon)] = bm
            for stock in signals.to_dict("records"):
                value, reason = engine.outcome(stock["ticker"], day, horizon, cost_bps)
                if stock["status"] == "INSUFFICIENT":
                    value, reason = math.nan, "Signal unavailable"
                rows.append({"signal_date": day, "ticker": stock["ticker"],
                             "sector": stock.get("sector", "Unspecified"), "status": stock["status"],
                             "horizon": horizon, "return_pct": value, "benchmark_pct": bm,
                             "outcome_status": reason})
        if progress:
            progress(i + 1, len(sample_dates))
    observations = pd.DataFrame(rows, columns=["signal_date", "ticker", "sector", "status", "horizon",
                                               "return_pct", "benchmark_pct", "outcome_status"])
    observations["return_pct"] = pd.to_numeric(observations.return_pct, errors="coerce").astype(float)
    daily = []
    groups = dict(tuple(observations.groupby(["signal_date", "horizon"])))
    empty = observations.iloc[:0]
    for day, horizon in benchmarks:
        group = groups.get((day, horizon), empty)
        selected, control = group[group.status.eq("PASS")], group[group.status.eq("FAIL")]
        valid, failed = selected.return_pct.dropna(), control.return_pct.dropna()
        # Match each observed selected stock to its sector's nonqualifier mean on that date.
        control_sector = control.groupby("sector").return_pct.mean()
        matched = selected.assign(control=selected.sector.map(control_sector)).dropna(subset=["return_pct", "control"])
        bm = benchmarks[(day, horizon)]
        daily.append({"signal_date": day, "horizon": horizon,
                      "universe_size": len(group),
                      "qualifiers": len(selected), "observed_qualifiers": len(valid),
                      "nonqualifiers": len(control), "observed_nonqualifiers": len(failed),
                      "unavailable_signals": int(group.status.eq("INSUFFICIENT").sum()),
                      "qualifier_mean_pct": valid.mean(), "qualifier_median_pct": valid.median(),
                      "nonqualifier_mean_pct": failed.mean(), "benchmark_pct": bm,
                      "qualifier_minus_nonqualifier_pp": valid.mean() - failed.mean(),
                      "qualifier_minus_benchmark_pp": valid.mean() - bm,
                      "sector_matched_excess_pp": (matched.return_pct - matched.control).mean() if len(matched) else math.nan,
                      "sector_matched_count": len(matched)})
    by_date = pd.DataFrame(daily)
    summary = []
    for horizon in sorted(set(horizons)):
        group = observations[observations.horizon.eq(horizon)]
        values = group.loc[group.status.eq("PASS"), "return_pct"].dropna()
        dates = by_date[by_date.horizon.eq(horizon)]
        requested = int(group.status.eq("PASS").sum())
        summary.append({"holding_sessions": horizon, "signal_dates": len(dates),
                        "dates_with_empty_universe": int(dates.universe_size.eq(0).sum()),
                        "dates_with_observed_qualifiers": int(dates.qualifier_mean_pct.notna().sum()),
                        "qualifier_observations": requested, "available_outcomes": len(values),
                        "coverage_pct": 100 * len(values) / requested if requested else math.nan,
                        "median_stock_outcome_pct": values.median(),
                        "stock_outcome_p10_pct": values.quantile(.1), "stock_outcome_p90_pct": values.quantile(.9),
                        "mean_of_date_means_pct": dates.qualifier_mean_pct.mean(),
                        "mean_vs_nonqualifier_pp": dates.qualifier_minus_nonqualifier_pp.mean(),
                        "mean_vs_benchmark_pp": dates.qualifier_minus_benchmark_pp.mean(),
                        "mean_sector_matched_excess_pp": dates.sector_matched_excess_pp.mean()})
    return CohortResult(observations, by_date, pd.DataFrame(summary))


@dataclass
class BacktestSettings:
    initial_cash: float = 100000.0
    max_positions: int = 10
    holding_sessions: int = 20
    review_every: int = 5
    ranking: str = "rank_normalized_slope"
    commission_bps: float = 5.0
    slippage_bps: float = 5.0
    exit_on_fail: bool = True
    cash_rate_pct: float = 0.0
    benchmark: str = "SPY"

    def validate(self):
        for label in ("max_positions", "holding_sessions", "review_every"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if not np.isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("Initial capital must be positive and finite")
        for c in (self.commission_bps, self.slippage_bps):
            if not np.isfinite(c) or not 0 <= c < 10000:
                raise ValueError("Commission and slippage must each be in [0, 10000) bps per side")
        if self.ranking not in RANKINGS or not isinstance(self.exit_on_fail, bool):
            raise ValueError("Invalid ranking or exit setting")
        RiskSettings(benchmark=self.benchmark, risk_free_pct=self.cash_rate_pct).validate()


@dataclass
class BacktestResult:
    equity: pd.DataFrame
    trades: pd.DataFrame
    orders: pd.DataFrame
    diagnostics: pd.DataFrame
    report: RiskReport
    settings: BacktestSettings
    notes: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def summary(self):
        return {**self.report.values, "trades": len(self.trades),
                "transaction_costs": float(self.trades.total_cost.sum()) if len(self.trades) else 0.0,
                "canceled_entries": int(self.orders.status.eq("CANCELED").sum()) if len(self.orders) else 0,
                "average_invested_pct": float(self.equity.invested_pct.iloc[1:].mean())}


def backtest(engine: StudyEngine, settings: BacktestSettings, risk: RiskSettings | None = None,
             progress=None) -> BacktestResult:
    """Vacancy-filling reviews; target new-position budget = previous-close NAV / slots.

    Holdings drift. No leverage/shorting. Fixed horizon exits use that day's close;
    optional failed-screen exits use the next open. Missing held prices abort the run.
    """
    settings.validate()
    risk = replace(risk or RiskSettings(), benchmark=settings.benchmark)
    risk.validate()
    dates, cash, held = engine.dates, settings.initial_cash, {}
    fee, slip = settings.commission_bps / 10000, settings.slippage_bps / 10000
    cash_daily = risk.daily_rate(settings.cash_rate_pct)
    trades, orders, diagnostic, equity = [], [], [], []
    pending_entries, pending_exits = [], []
    next_budget = 0.0

    def required(ticker, day, field):
        value = engine.price(ticker, day, field)
        if not np.isfinite(value):
            raise ValueError(f"Held position {ticker}: missing {field} on {day.date()}. "
                             "Backtest stopped; no synthetic liquidation or filled price was assumed.")
        return value

    def sell(ticker, day, field, reason):
        nonlocal cash
        position = held.pop(ticker)
        price = required(ticker, day, field)
        gross = position["quantity"] * price
        proceeds = gross * (1 - slip) * (1 - fee)
        cash += proceeds
        exit_cost = gross - proceeds
        trades.append({"ticker": ticker, "signal_date": position["signal_date"],
                       "entry_date": position["entry_date"], "exit_date": day,
                       "entry_adjusted_open": position["entry_price"], "exit_adjusted_price": price,
                       "exit_at": field, "reason": reason, "quantity": position["quantity"],
                       "entry_outlay": position["outlay"], "exit_proceeds": proceeds,
                       "total_cost": position["entry_cost"] + exit_cost,
                       "net_return_pct": 100 * (proceeds / position["outlay"] - 1)})

    for i, day in enumerate(dates):
        if i:
            cash *= 1 + cash_daily
            for ticker in list(held):
                required(ticker, day, "adj_open")
            for ticker in pending_exits:
                if ticker in held:
                    sell(ticker, day, "adj_open", "Failed screen or left membership at prior review")
            for ticker in pending_entries:
                if ticker in held or len(held) >= settings.max_positions:
                    continue
                price = engine.price(ticker, day, "adj_open")
                budget = min(cash, next_budget)
                if not np.isfinite(price):
                    orders.append({"signal_date": dates[i - 1], "date": day, "ticker": ticker,
                                   "status": "CANCELED", "reason": "Missing adjusted entry open"})
                    continue
                if budget <= 1e-8:
                    break
                quantity = budget / (price * (1 + slip) * (1 + fee))
                cash -= budget
                held[ticker] = {"quantity": quantity, "entry_price": price, "entry_date": day,
                                "signal_date": dates[i - 1], "outlay": budget,
                                "entry_cost": budget - quantity * price,
                                "due": i + settings.holding_sessions - 1}
                orders.append({"signal_date": dates[i - 1], "date": day, "ticker": ticker,
                               "status": "FILLED", "reason": "Next-open entry"})
            for ticker in list(held):
                required(ticker, day, "adj_close")
                if held[ticker]["due"] <= i or i == len(dates) - 1:
                    sell(ticker, day, "adj_close", "Holding period" if held[ticker]["due"] <= i else "Study end")
        invested = sum(p["quantity"] * required(t, day, "adj_close") for t, p in held.items())
        nav = cash + invested
        equity.append({"date": day, "equity": nav, "cash": cash, "positions": len(held),
                       "invested_pct": 100 * invested / nav})
        pending_entries, pending_exits = [], []
        if i < len(dates) - 1 and i % settings.review_every == 0:
            table = engine.signals(day)
            qualifiers = ranked_qualifiers(table, settings.ranking)
            passing = set(qualifiers.ticker)
            if settings.exit_on_fail:
                pending_exits = [t for t in held if t not in passing]
            pending_entries = [t for t in qualifiers.ticker if t not in held]
            next_budget = nav / settings.max_positions
            diagnostic.append({"signal_date": day, "requested": len(table), "qualifiers": len(qualifiers),
                               "unavailable": int(table.status.eq("INSUFFICIENT").sum()),
                               "planned_exits": len(pending_exits)})
        if progress:
            progress(i + 1, len(dates))
    curve = pd.DataFrame(equity).set_index("date")
    # Benchmark buys at the same first investable open and liquidates at study end.
    first_open = engine.price(settings.benchmark, dates[1], "adj_open")
    benchmark = pd.Series(np.nan, index=dates, dtype=float)
    notes = ["Daily bars and retrospective adjustment factors; no spread, tax, market-impact or capacity model.",
             "New positions use NAV / maximum positions; existing holdings drift; unfilled slots remain cash."]
    if np.isfinite(first_open):
        benchmark.iloc[0] = settings.initial_cash
        for i, day in enumerate(dates[1:], 1):
            close = engine.price(settings.benchmark, day)
            benchmark.iloc[i] = settings.initial_cash / ((1 + slip) * (1 + fee)) * close / first_open
        benchmark.iloc[-1] *= (1 - slip) * (1 - fee)
    if benchmark.isna().any():
        notes.append("Benchmark missing on one or more sessions; benchmark-dependent statistics are unavailable.")
    curve["benchmark"] = benchmark
    curve["drawdown_pct"] = 100 * (curve.equity / curve.equity.cummax() - 1)
    report = risk_report(curve.equity, benchmark, len(curve) - 1, risk)
    return BacktestResult(curve, pd.DataFrame(trades), pd.DataFrame(orders), pd.DataFrame(diagnostic),
                          report, settings, notes,
                          {"config": engine.config.to_dict(), "risk_settings": asdict(risk),
                           "data_fingerprint": engine.fingerprint, "start": str(engine.start), "end": str(engine.end),
                           "membership_source": engine.membership.source if engine.membership else "Fixed applied universe",
                           "membership_digest": engine.membership.digest if engine.membership else None})


def parameter_neighbors(config: ScreenConfig, ma_key: str, rule_id: str):
    """Small fixed one-at-a-time neighborhood; preserve the base and skipped variants."""
    variants = [("Base", ScreenConfig.from_dict(config.to_dict()), "")]
    for kind in ("MA period", "Rule lookback"):
        for delta in (-1, 1):
            candidate = ScreenConfig.from_dict(config.to_dict())
            label = f"{kind} {delta:+d}"
            try:
                if kind == "MA period":
                    ma = next(m for m in candidate.moving_averages if m.key == ma_key)
                    old = ma.key
                    ma.period += delta
                    for rule in candidate.rules:
                        if rule.ma == old:
                            rule.ma = ma.key
                        if rule.other == old:
                            rule.other = ma.key
                else:
                    next(r for r in candidate.rules if r.id == rule_id).lookback += delta
                candidate.validate()
                variants.append((label, candidate, ""))
            except (ValueError, StopIteration) as exc:
                variants.append((label, None, str(exc) or "Selected MA or rule is unavailable"))
    return variants


def frozen_plan(config, settings, engine, split: date, metadata=None):
    """A recorded user-declared split, not proof that historical data was unseen."""
    if not engine.start < split < engine.end:
        raise ValueError("Split must be inside the loaded study dates")
    return {"config": config.to_dict(), "backtest": asdict(settings), "start": str(engine.start),
            "split": str(split), "end": str(engine.end), "data_fingerprint": engine.fingerprint,
            "membership_digest": engine.membership.digest if engine.membership else None,
            "metadata": metadata or {}, "holdout_claim": "User-declared; prior human exposure cannot be verified"}
