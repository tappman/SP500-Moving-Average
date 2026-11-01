"""Concentration and aligned, daily-rebalanced hypothetical basket analytics."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .calendar import sessions
from .risk import RiskReport, RiskSettings, numeric_prices, risk_report


@dataclass
class PortfolioReport:
    weights: pd.DataFrame
    sectors: pd.DataFrame
    correlations: pd.DataFrame
    equity: pd.DataFrame
    risk: RiskReport
    concentration: dict


def analyze_portfolio(prices, weights: dict[str, float], universe: pd.DataFrame,
                      screen_date, lookback: int, settings: RiskSettings,
                      benchmark=None) -> PortfolioReport:
    """Weights are fractions of total NAV; remainder is cash at assumed RF rate.

    All positive-weight stocks require the same complete N+1 close window.
    There is no pairwise deletion or filling of missing stock returns.
    """
    settings.validate()
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 2:
        raise ValueError("Portfolio lookback must be at least two daily returns")
    if not weights or any(not np.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError("Portfolio weights must be nonnegative and finite")
    if sum(weights.values()) > 1 + 1e-10:
        raise ValueError("Total stock weights cannot exceed 100%")
    weights = {t: float(w) for t, w in weights.items() if w > 0}
    if not weights:
        raise ValueError("Give at least one stock a positive weight")
    span = max(60, lookback * 2 + 30)
    idx = sessions((pd.Timestamp(screen_date) - pd.Timedelta(days=span)).date(), screen_date)[-(lookback + 1):]
    if len(idx) != lookback + 1:
        raise ValueError("Not enough calendar sessions for the portfolio window")
    series, missing = {}, []
    for ticker in weights:
        frame = prices.get(ticker)
        p = numeric_prices(frame.adj_close).reindex(idx) if frame is not None and "adj_close" in frame else pd.Series(np.nan, index=idx)
        if p.isna().any():
            missing.append(f"{ticker} ({int(p.notna().sum())}/{lookback + 1} closes)")
        series[ticker] = p
    if missing:
        raise ValueError("Portfolio window is incomplete: " + "; ".join(missing))
    close = pd.DataFrame(series)
    returns = (close / close.shift(1) - 1).iloc[1:]
    w = pd.Series(weights).reindex(returns.columns)
    cash = max(0.0, 1 - w.sum())
    basket = returns @ w + cash * settings.daily_rate(settings.risk_free_pct)
    equity = pd.Series(np.r_[1.0, np.cumprod(1 + basket.to_numpy())], index=idx)
    bm = numeric_prices(benchmark).reindex(idx) if benchmark is not None else None
    report = risk_report(equity, bm, lookback, settings)
    nav = pd.DataFrame({"portfolio": equity})
    if bm is not None and bm.notna().all():
        nav["benchmark"] = bm / bm.iloc[0]
    nav["drawdown_pct"] = 100 * (equity / equity.cummax() - 1)
    cov = returns.cov()
    variance = float(w @ cov @ w)
    contributions = w * (cov @ w) / variance if variance > 1e-24 else pd.Series(np.nan, index=w.index)
    metadata = universe.drop_duplicates("ticker").set_index("ticker")
    table = pd.DataFrame({"ticker": w.index, "weight_pct": 100 * w.to_numpy(),
                          "volatility_ann_pct": returns.std(ddof=1).to_numpy() * math.sqrt(settings.annualization) * 100,
                          "variance_contribution_pct": contributions.to_numpy() * 100})
    table["sector"] = table.ticker.map(metadata.sector.to_dict() if "sector" in metadata else {}).fillna("Unspecified")
    sectors = table.groupby("sector", as_index=False).weight_pct.sum()
    if cash > 1e-12:
        sectors = pd.concat([sectors, pd.DataFrame([{"sector": "Cash", "weight_pct": cash * 100}])], ignore_index=True)
    normalized = w / w.sum()
    hhi = float(np.sum(normalized**2))
    vol = math.sqrt(max(0.0, variance))
    concentration = {"stock_weight_pct": 100 * w.sum(), "cash_weight_pct": 100 * cash,
                     "largest_position_pct": 100 * w.max(), "stock_hhi": hhi,
                     "effective_stock_holdings": 1 / hhi,
                     "diversification_ratio": float(w @ returns.std(ddof=1)) / vol if vol > 1e-12 else math.nan}
    return PortfolioReport(table, sectors, returns.corr(), nav, report, concentration)
