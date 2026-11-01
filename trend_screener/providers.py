"""Provider contract: inclusive daily date range, raw OHLC and a separate adjusted close."""
from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
import json
import time
from typing import Protocol

import numpy as np
import pandas as pd

BAR_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


@dataclass
class DownloadBatch:
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class PriceProvider(Protocol):
    name: str

    def download(self, tickers: list[str], start: date, end: date) -> DownloadBatch: ...


class AliasedProvider:
    """Explicit symbol renames without automatically splicing different securities' histories."""

    def __init__(self, provider: PriceProvider, aliases: dict[str, str]):
        self.provider, self.aliases = provider, aliases
        digest = hashlib.sha256(json.dumps(aliases, sort_keys=True).encode()).hexdigest()[:12]
        self.name = f"{provider.name}_aliases_{digest}" if aliases else provider.name

    def download(self, tickers: list[str], start: date, end: date) -> DownloadBatch:
        routed = {ticker: self.aliases.get(ticker, ticker) for ticker in tickers}
        batch = self.provider.download(list(dict.fromkeys(routed.values())), start, end)
        result = DownloadBatch()
        for ticker, actual in routed.items():
            if actual in batch.frames:
                result.frames[ticker] = batch.frames[actual].copy()
            else:
                result.errors[ticker] = f"Provider symbol {actual}: {batch.errors.get(actual, 'No data returned')}"
        return result


def normalize_bars(raw: pd.DataFrame, auto_adjusted: bool = False) -> pd.DataFrame:
    result = raw.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Adj Close": "adj_close", "Volume": "volume",
    }).copy()
    if auto_adjusted:
        # Explicitly do NOT pretend auto-adjusted OHLC is unadjusted OHLC.
        result["adj_close"] = result["close"]
        for c in ("open", "high", "low", "close"):
            result[c] = np.nan
    if not set(BAR_COLUMNS) <= set(result):
        raise ValueError("Provider must supply raw OHLCV and separate Adj Close; no silent Close fallback")
    result = result[BAR_COLUMNS].apply(pd.to_numeric, errors="coerce")
    idx = pd.DatetimeIndex(pd.to_datetime(result.index))
    if idx.tz is not None:
        # Daily bars are dated in their exchange timezone; discard tz without shifting the session.
        idx = idx.tz_localize(None)
    result.index = idx.normalize()
    result.index.name = "date"
    if result.index.has_duplicates:
        raise ValueError("Provider returned duplicate daily sessions")
    result = result.sort_index().replace([np.inf, -np.inf], np.nan)
    for col in BAR_COLUMNS[:-1]:
        result[col] = result[col].where(result[col] > 0)
    result["volume"] = result["volume"].where(result["volume"] >= 0)
    if not auto_adjusted:
        valid_ohlc = (
            result["high"].ge(result[["open", "close", "low"]].max(axis=1))
            & result["low"].le(result[["open", "close", "high"]].min(axis=1))
            & result[["open", "high", "low", "close"]].notna().all(axis=1)
        )
        result.loc[~valid_ohlc, BAR_COLUMNS] = np.nan
    return result


class YFinanceProvider:
    name = "yahoo_raw_plus_adjusted_v1"

    def __init__(self, batch_size: int = 40, retries: int = 2, timeout: int = 12):
        self.batch_size, self.retries, self.timeout = batch_size, retries, timeout

    def download(self, tickers: list[str], start: date, end: date) -> DownloadBatch:
        import yfinance as yf

        output = DownloadBatch()
        for begin in range(0, len(tickers), self.batch_size):
            pending = tickers[begin:begin + self.batch_size]
            for attempt in range(self.retries + 1):
                if not pending:
                    break
                try:
                    raw = yf.download(
                        pending, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                        interval="1d", auto_adjust=False, back_adjust=False, actions=False,
                        group_by="ticker", multi_level_index=True, progress=False, keepna=True,
                        threads=min(4, len(pending)), timeout=self.timeout, repair=False,
                    )
                    failed = []
                    for ticker in pending:
                        try:
                            if raw is None or raw.empty:
                                raise ValueError("No price data returned")
                            if isinstance(raw.columns, pd.MultiIndex):
                                if ticker in raw.columns.get_level_values(0):
                                    single = raw[ticker]
                                else:
                                    single = raw.xs(ticker, axis=1, level=1)
                            else:
                                if len(pending) != 1:
                                    raise ValueError("Unexpected multi-ticker provider schema")
                                single = raw
                            single = normalize_bars(single)
                            single = single.loc[str(start):str(end)]
                            if not single["adj_close"].notna().any():
                                raise ValueError("No valid adjusted prices (unavailable ticker, rate limit or network failure)")
                            output.frames[ticker] = single
                            output.errors.pop(ticker, None)
                        except (KeyError, ValueError, TypeError) as exc:
                            output.errors[ticker] = str(exc)
                            failed.append(ticker)
                    pending = failed
                except Exception as exc:
                    # Network/client errors are isolated here; calculation errors are not swallowed.
                    output.errors.update({t: f"{type(exc).__name__}: {exc}" for t in pending})
                if pending and attempt < self.retries:
                    time.sleep(min(2**attempt, 4))
            # Recently listed/spun-off shares may fail a long multi-ticker history
            # download even when Yahoo supplies their current daily bars.
            # Retry only a small failed subset through the single-ticker API.
            # Never replace adjusted prices with unadjusted Close values.
            if 0 < len(pending) <= 8:
                recent_start = max(start, end - timedelta(days=210))
                for ticker in pending:
                    error = output.errors.get(ticker, "")
                    if any(mark in error.lower() for mark in
                           ("yf ratelimiterror", "yfratelimiterror", "too many requests",
                            "429 client error", "http error 429")):
                        continue
                    try:
                        history = yf.Ticker(ticker).history(
                            start=recent_start.isoformat(),
                            end=(end + timedelta(days=1)).isoformat(),
                            interval="1d", auto_adjust=False, actions=False,
                            repair=False,
                        )
                        if history is None or history.empty:
                            continue
                        recovered = normalize_bars(history).loc[str(start):str(end)]
                        if recovered["adj_close"].notna().any():
                            output.frames[ticker] = recovered
                            output.errors.pop(ticker, None)
                    except Exception:
                        # Preserve the original diagnostic if the backup request fails.
                        continue
            if begin + self.batch_size < len(tickers):
                time.sleep(0.15)
        return output
