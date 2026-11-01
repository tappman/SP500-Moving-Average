"""Causal risk/return analytics on complete, date-aligned adjusted-price windows.

All input data is daily. Each N-return window consumes exactly N+1 closes.
Annual rates in settings use percent units; computed ratio inputs use fractions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re

import numpy as np
import pandas as pd


RISK_METRICS = {
    "sharpe": "Sharpe (annualized)",
    "sharpe_daily": "Sharpe (daily, unannualized)",
    "sortino": "Sortino (annualized)",
    "beta": "Beta vs benchmark",
    "alpha_ann_pct": "Regression alpha (annualized %)",
    "alpha_daily_pct": "Regression alpha (daily %)",
    "volatility_ann_pct": "Volatility (annualized %)",
    "downside_deviation_ann_pct": "Downside deviation (annualized %)",
    "max_drawdown_pct": "Maximum drawdown magnitude (%)",
    "calmar": "Calmar (CAGR / max drawdown)",
    "information_ratio": "Information ratio (annualized)",
    "tracking_error_ann_pct": "Tracking error (annualized %)",
    "correlation": "Correlation with benchmark",
    "regression_r2": "Return-regression R-squared",
    "total_return_pct": "Total adjusted return (%)",
    "cagr_pct": "CAGR (% per assumed trading year)",
    "mean_return_ann_pct": "Mean return (annualized arithmetic %)",
    "benchmark_return_pct": "Benchmark total return (%)",
    "active_return_pp": "Total return minus benchmark (pp)",
    "positive_days_pct": "Positive daily returns (%)",
}
DEFAULT_RISK_METRICS = [
    "sharpe", "sortino", "beta", "alpha_ann_pct",
    "volatility_ann_pct", "max_drawdown_pct", "cagr_pct",
]
BENCHMARK_METRICS = {
    "beta", "alpha_ann_pct", "alpha_daily_pct", "information_ratio",
    "tracking_error_ann_pct", "correlation", "regression_r2",
    "benchmark_return_pct", "active_return_pp",
}
# Treat rounding noise around a constant daily return as a zero denominator.
DENOMINATOR_TOLERANCE = 1e-12


@dataclass
class RiskSettings:
    enabled: bool = True
    lookbacks: list[int] = field(default_factory=lambda: [63, 126, 252])
    benchmark: str = "SPY"
    risk_free_pct: float = 0.0
    annualization: int = 252
    sortino_target: str = "risk_free"
    target_return_pct: float = 0.0
    metrics: list[str] = field(default_factory=lambda: DEFAULT_RISK_METRICS.copy())

    def validate(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("Risk analytics enabled must be a boolean")
        if (not isinstance(self.lookbacks, list)
                or any(isinstance(n, bool) or not isinstance(n, int) or n < 2 for n in self.lookbacks)
                or len(set(self.lookbacks)) != len(self.lookbacks)):
            raise ValueError("Performance lookbacks must be unique integers of at least 2 daily returns")
        if self.enabled and not self.lookbacks:
            raise ValueError("Choose at least one performance lookback")
        if (not isinstance(self.annualization, int) or isinstance(self.annualization, bool)
                or not 1 <= self.annualization <= 366):
            raise ValueError("Trading sessions per year must be an integer between 1 and 366")
        for label, rate in (("Risk-free rate", self.risk_free_pct), ("Sortino target", self.target_return_pct)):
            if (isinstance(rate, bool) or not isinstance(rate, (int, float))
                    or not math.isfinite(rate) or rate <= -100):
                raise ValueError(f"{label} must be finite and greater than -100% per year")
            daily_rate = np.expm1(np.log1p(rate / 100) / self.annualization)
            if not np.isfinite(daily_rate):
                raise ValueError(f"{label} produces an unsupported daily rate")
        if self.sortino_target not in {"risk_free", "custom"}:
            raise ValueError("Sortino target must be risk_free or custom")
        if (not isinstance(self.benchmark, str)
                or not re.fullmatch(r"[\^A-Z0-9][A-Z0-9^=_-]{0,24}", self.benchmark)):
            raise ValueError("Choose a valid uppercase benchmark ticker")
        if (not isinstance(self.metrics, list)
                or any(not isinstance(m, str) or m not in RISK_METRICS for m in self.metrics)
                or len(set(self.metrics)) != len(self.metrics)):
            raise ValueError("Choose unique, supported risk/return metrics")
        if self.enabled and not self.metrics:
            raise ValueError("Choose at least one risk/return metric to display")

    @property
    def target_pct(self) -> float:
        return self.risk_free_pct if self.sortino_target == "risk_free" else self.target_return_pct

    def daily_rate(self, annual_pct: float) -> float:
        return float(np.expm1(np.log1p(annual_pct / 100) / self.annualization))

    def signature(self) -> tuple:
        # Visible-column choices do not change the calculations.
        return (tuple(self.lookbacks), self.benchmark, self.risk_free_pct,
                self.annualization, self.sortino_target, self.target_return_pct)


@dataclass
class RiskReport:
    values: dict[str, float]
    requested_returns: int
    available_returns: int = 0
    benchmark_returns: int = 0
    start_date: str = ""
    end_date: str = ""
    status: str = "Stock history unavailable"
    notes: list[str] = field(default_factory=list)

    def table_columns(self) -> dict:
        prefix = f"risk_{self.requested_returns}_"
        return {
            **{prefix + key: value for key, value in self.values.items()},
            prefix + "return_observations": self.available_returns,
            prefix + "benchmark_observations": self.benchmark_returns,
            prefix + "start_date": self.start_date,
            prefix + "end_date": self.end_date,
            prefix + "status": self.status,
            prefix + "notes": " | ".join(self.notes),
        }


def numeric_prices(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce").astype(float)
    return values.where(np.isfinite(values) & (values > 0))


def simple_returns(prices: pd.Series) -> pd.Series:
    p = numeric_prices(prices)
    # Division by a shifted series never skips an absent observation.
    return p / p.shift(1) - 1


def _std(values) -> float:
    return float(np.std(values, ddof=1))


def _ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(denominator) or denominator <= DENOMINATOR_TOLERANCE:
        return math.nan
    return float(numerator / denominator)


def risk_report(prices: pd.Series, benchmark: pd.Series | None,
                lookback: int, settings: RiskSettings) -> RiskReport:
    """Analyze the exact final N transitions without dropping missing returns.

    Callers align the index to expected NYSE sessions and clip at the screen date.
    Benchmark observations are reindexed to those SAME dates, never joined by position.
    """
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 2:
        raise ValueError("Risk lookback must contain at least 2 daily returns")
    values = {m: math.nan for m in RISK_METRICS}
    report = RiskReport(values, lookback)
    prices = numeric_prices(prices)
    sample = prices.iloc[-(lookback + 1):]
    if len(sample):
        report.start_date = pd.Timestamp(sample.index[0]).date().isoformat()
        report.end_date = pd.Timestamp(sample.index[-1]).date().isoformat()
    returns = simple_returns(sample).iloc[1:]
    report.available_returns = int(returns.notna().sum())
    if len(sample) != lookback + 1 or sample.isna().any():
        report.notes.append(f"Need {lookback + 1} consecutive adjusted closes; "
                            f"have {report.available_returns} valid daily returns in the requested tail.")
        return report
    r = returns.to_numpy()
    a = settings.annualization
    rf = settings.daily_rate(settings.risk_free_pct)
    target = settings.daily_rate(settings.target_pct)
    excess = r - rf
    target_excess = r - target
    std = _std(excess)
    downside = float(np.sqrt(np.mean(np.minimum(target_excess, 0)**2)))
    total = float(sample.iloc[-1] / sample.iloc[0] - 1)
    cagr = float(np.expm1(np.log(sample.iloc[-1] / sample.iloc[0]) * a / lookback))
    drawdown = float((1 - sample / sample.cummax()).max())
    values.update({
        "sharpe_daily": _ratio(float(excess.mean()), std),
        "sharpe": _ratio(float(excess.mean()) * math.sqrt(a), std),
        "sortino": _ratio(float(target_excess.mean()) * math.sqrt(a), downside),
        "volatility_ann_pct": 100 * _std(r) * math.sqrt(a),
        "downside_deviation_ann_pct": 100 * downside * math.sqrt(a),
        "total_return_pct": 100 * total,
        "cagr_pct": 100 * cagr,
        "mean_return_ann_pct": 100 * a * float(r.mean()),
        "max_drawdown_pct": 100 * drawdown,
        "calmar": _ratio(cagr, drawdown),
        "positive_days_pct": 100 * float(np.mean(r > 0)),
    })
    report.status = "Stock metrics available; benchmark unavailable"
    if std <= DENOMINATOR_TOLERANCE:
        report.notes.append("Sharpe undefined: daily excess-return volatility is zero.")
    if downside <= DENOMINATOR_TOLERANCE:
        report.notes.append("Sortino undefined: no downside deviation below the selected target.")
    if drawdown <= DENOMINATOR_TOLERANCE:
        report.notes.append("Calmar undefined: maximum drawdown is zero.")
    if benchmark is None or benchmark.empty:
        report.notes.append("Benchmark history unavailable; benchmark-dependent metrics are blank.")
        return report
    bm = numeric_prices(benchmark).reindex(sample.index)
    bm_returns = simple_returns(bm).iloc[1:]
    report.benchmark_returns = int(bm_returns.notna().sum())
    if len(bm) != lookback + 1 or bm.isna().any():
        report.notes.append("Benchmark needs complete adjusted closes on every stock-window date; "
                            "missing dates are not dropped or filled.")
        return report
    b = bm_returns.to_numpy()
    x, y = b - rf, excess
    active = r - b
    tracking = _std(active)
    values["tracking_error_ann_pct"] = 100 * tracking * math.sqrt(a)
    values["information_ratio"] = _ratio(float(active.mean()) * math.sqrt(a), tracking)
    values["benchmark_return_pct"] = float(100 * (bm.iloc[-1] / bm.iloc[0] - 1))
    values["active_return_pp"] = values["total_return_pct"] - values["benchmark_return_pct"]
    report.status = "Stock and benchmark metrics available"
    if tracking <= DENOMINATOR_TOLERANCE:
        report.notes.append("Information ratio undefined: tracking-error volatility is zero.")
    xstd, ystd = _std(x), _std(y)
    if xstd <= DENOMINATOR_TOLERANCE:
        report.notes.append("Beta and alpha undefined: benchmark daily-return variance is zero.")
        return report
    # OLS of excess stock returns on excess benchmark returns, with an intercept.
    xc, yc = x - x.mean(), y - y.mean()
    beta = float(np.dot(xc, yc) / np.dot(xc, xc))
    alpha_daily = float(y.mean() - beta * x.mean())
    values["beta"] = beta
    values["alpha_daily_pct"] = 100 * alpha_daily
    values["alpha_ann_pct"] = 100 * a * alpha_daily
    if ystd > DENOMINATOR_TOLERANCE:
        correlation = float(np.clip(np.dot(xc, yc) / np.sqrt(np.dot(xc, xc) * np.dot(yc, yc)), -1, 1))
        values["correlation"] = correlation
        values["regression_r2"] = correlation**2
    else:
        report.notes.append("Return-regression R-squared/correlation undefined for constant stock returns.")
    return report


def reports_for_stock(prices: pd.Series, benchmark: pd.Series | None,
                      settings: RiskSettings) -> dict[int, RiskReport]:
    return {n: risk_report(prices, benchmark, n, settings) for n in settings.lookbacks}


def rolling_metrics(prices: pd.Series, benchmark: pd.Series | None,
                    lookback: int, settings: RiskSettings) -> pd.DataFrame:
    """Vectorized full-window rolling ratios; gaps are never skipped."""
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 2:
        raise ValueError("Risk lookback must contain at least 2 daily returns")
    r = simple_returns(prices)
    a = settings.annualization
    rf = settings.daily_rate(settings.risk_free_pct)
    excess = r - rf
    mean = excess.rolling(lookback, min_periods=lookback).mean()
    std = excess.rolling(lookback, min_periods=lookback).std(ddof=1)
    target_excess = r - settings.daily_rate(settings.target_pct)
    downside = (target_excess.clip(upper=0)**2).rolling(lookback, min_periods=lookback).mean().pow(.5)
    result = pd.DataFrame(index=prices.index)
    result["sharpe"] = mean * math.sqrt(a) / std.where(std > DENOMINATOR_TOLERANCE)
    result["sortino"] = (target_excess.rolling(lookback, min_periods=lookback).mean() * math.sqrt(a)
                         / downside.where(downside > DENOMINATOR_TOLERANCE))
    result["volatility_ann_pct"] = std * math.sqrt(a) * 100
    if benchmark is None:
        b = pd.Series(np.nan, index=prices.index)
    else:
        b = simple_returns(numeric_prices(benchmark).reindex(prices.index))
    bx = b - rf
    cov = excess.rolling(lookback, min_periods=lookback).cov(bx, ddof=1)
    bvar = bx.rolling(lookback, min_periods=lookback).var(ddof=1)
    result["beta"] = cov / bvar.where(bvar > DENOMINATOR_TOLERANCE**2)
    result["alpha_ann_pct"] = 100 * a * (
        mean - result["beta"] * bx.rolling(lookback, min_periods=lookback).mean())
    return result.replace([np.inf, -np.inf], np.nan)


def risk_column_label(column: str) -> str:
    match = re.fullmatch(r"risk_(\d+)_(.+)", column)
    if match and match[2] in RISK_METRICS:
        return f"{RISK_METRICS[match[2]]} · {match[1]} sessions"
    return column
