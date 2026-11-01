"""Deterministic synthetic prices. No demo value is a real market quote."""
from datetime import date
import hashlib

import numpy as np
import pandas as pd

from .calendar import sessions
from .providers import DownloadBatch


def demo_universe(count: int = 24) -> pd.DataFrame:
    sectors = ["Technology", "Health Care", "Industrials", "Financials"]
    return pd.DataFrame([{
        "ticker": f"DEMO{i:03d}", "symbol": f"DEMO{i:03d}",
        "company": f"Synthetic Company {i:03d}", "sector": sectors[(i-1) % 4],
        "industry": "Synthetic research data",
    } for i in range(1, count + 1)])


class DemoProvider:
    name = "synthetic_v1"

    def download(self, tickers: list[str], start: date, end: date) -> DownloadBatch:
        idx = sessions(start, end)
        t = np.asarray((idx - pd.Timestamp("2000-01-01")).days, dtype=float)
        result = DownloadBatch()
        for symbol in tickers:
            seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
            phase = (seed % 628) / 100
            base = 30 + seed % 220
            price = base * np.exp(
                0.00004 * t + 0.12 * np.sin(t / 85 + phase)
                + 0.025 * np.sin(t / 12 + phase) + 0.004 * np.sin(t / 2.1 + phase)
            )
            raw = price / 0.92
            frame = pd.DataFrame({
                "open": raw * 0.999, "high": raw * 1.012, "low": raw * 0.988,
                "close": raw, "adj_close": price, "volume": (1e6 + seed % 500000) * np.ones(len(t)),
            }, index=idx)
            frame.index.name = "date"
            result.frames[symbol] = frame
        return result
