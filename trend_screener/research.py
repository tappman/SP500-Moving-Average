"""Separate ex-post outcomes. This module is never consulted by the rule engine."""
from datetime import date

import numpy as np
import pandas as pd

from .calendar import sessions


def forward_returns(prices: dict[str, pd.DataFrame], screen_date: date,
                    end_date: date, horizons=(5, 20, 60)) -> pd.DataFrame:
    idx = sessions(screen_date, end_date)
    if idx.empty or idx[0].date() != screen_date:
        raise ValueError("The starting date must be a completed trading session")
    rows = []
    for ticker, frame in prices.items():
        p = frame["adj_close"].reindex(idx)
        row = {"ticker": ticker, "screen_date": str(screen_date)}
        for n in horizons:
            sample = p.iloc[:n + 1]
            if len(sample) == n + 1 and np.isfinite(sample).all() and (sample > 0).all():
                row[f"forward_{n}d_return_pct"] = float(100 * (sample.iloc[-1] / sample.iloc[0] - 1))
            else:
                row[f"forward_{n}d_return_pct"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)
