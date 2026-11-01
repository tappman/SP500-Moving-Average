"""Causal indicators; missing sessions are never filled or silently skipped."""
import numpy as np
import pandas as pd

from .models import MovingAverage


def daily_returns(adjusted_close: pd.Series, kind: str = "simple", periods: int = 1) -> pd.Series:
    if kind not in {"simple", "log"} or periods < 1:
        raise ValueError("Use simple/log returns and a positive period")
    numeric = pd.to_numeric(adjusted_close, errors="coerce").astype(float)
    safe = numeric.where(np.isfinite(numeric) & (numeric > 0))
    ratio = safe / safe.shift(periods)
    # An internal missing session also invalidates a multi-session return.
    complete = safe.rolling(periods + 1, min_periods=periods + 1).count().eq(periods + 1)
    result = np.log(ratio) if kind == "log" else ratio - 1
    return result.where(complete)


def moving_average(price: pd.Series, ma: MovingAverage) -> pd.Series:
    ma.validate()
    numeric = pd.to_numeric(price, errors="coerce").astype(float)
    safe = numeric.where(np.isfinite(numeric) & (numeric > 0))
    if ma.kind == "SMA":
        return safe.rolling(ma.period, min_periods=ma.period).mean().rename(ma.key)
    # Reset an EMA after every missing observation. EWM otherwise bridges NaNs.
    block = safe.isna().cumsum()
    result = safe.groupby(block, group_keys=False).transform(
        lambda s: s.ewm(span=ma.period, adjust=False, min_periods=ma.period).mean()
    )
    return result.where(safe.notna()).rename(ma.key)


def add_indicators(frame: pd.DataFrame, averages: list[MovingAverage],
                   price_source: str = "adj_close", return_kind: str = "simple") -> pd.DataFrame:
    result = frame.copy()
    for column in ("open", "high", "low", "close", "adj_close", "volume"):
        result[column] = (pd.to_numeric(result[column], errors="coerce").astype(float)
                          if column in result else np.nan)
    result["PRICE"] = result[price_source]
    for ma in averages:
        if ma.enabled:
            result[ma.key] = moving_average(result["PRICE"], ma)
    for n in (1, 5, 20):
        result[f"return_{n}d"] = daily_returns(result["adj_close"], return_kind, n)
    return result
