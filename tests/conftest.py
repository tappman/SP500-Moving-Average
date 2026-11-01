from datetime import date

import numpy as np
import pandas as pd
import pytest

from trend_screener.calendar import sessions
from trend_screener.providers import DownloadBatch


def bars(values, start="2024-01-02"):
    idx = sessions(pd.Timestamp(start).date(), date(2030, 1, 1))[:len(values)]
    values = np.asarray(values, dtype=float)
    return pd.DataFrame({
        "open": values, "high": values * 1.01, "low": values * .99,
        "close": values, "adj_close": values, "volume": 1000.0,
    }, index=idx)


@pytest.fixture
def make_bars():
    return bars


class FakeProvider:
    name = "fake_v1"

    def __init__(self):
        self.calls = []
        self.factor = 1.0
        self.fail = False

    def download(self, tickers, start, end):
        self.calls.append((list(tickers), start, end))
        if self.fail:
            return DownloadBatch(errors={t: "Network unavailable" for t in tickers})
        idx = sessions(start, end)
        values = 100 + np.asarray((idx - pd.Timestamp("2020-01-01")).days) / 100
        frames = {}
        for ticker in tickers:
            frame = pd.DataFrame({
                "open": values, "high": values * 1.01, "low": values * .99,
                "close": values, "adj_close": values * self.factor, "volume": 1000.0,
            }, index=idx)
            frame.index.name = "date"
            frames[ticker] = frame
        return DownloadBatch(frames=frames)


@pytest.fixture
def fake_provider():
    return FakeProvider()
