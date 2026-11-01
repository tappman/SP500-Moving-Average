"""Incremental Parquet cache with overlap refresh and adjustment-revision protection."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from filelock import FileLock
import numpy as np
import pandas as pd

from .calendar import sessions
from .providers import BAR_COLUMNS, PriceProvider


@dataclass
class CachedBatch:
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    metadata: dict[str, dict] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    downloads: list[dict] = field(default_factory=list)


def _revised(old: pd.DataFrame, new: pd.DataFrame) -> bool:
    common = old.index.intersection(new.index)
    if common.empty:
        return False
    for col in ("close", "adj_close"):
        a, b = old.loc[common, col], new.loc[common, col]
        valid = a.notna() & b.notna()
        if valid.any() and not np.allclose(a[valid], b[valid], rtol=1e-7, atol=1e-7):
            return True
    return False


class PriceCache:
    def __init__(self, directory: str | Path, provider: PriceProvider):
        self.directory = Path(directory) / provider.name
        self.directory.mkdir(parents=True, exist_ok=True)
        self.provider = provider

    def _paths(self, ticker):
        stem = hashlib.sha256(ticker.encode()).hexdigest()[:24]
        return self.directory / f"{stem}.parquet", self.directory / f"{stem}.json"

    def _read(self, ticker):
        path, meta_path = self._paths(ticker)
        if not path.exists() or not meta_path.exists():
            return pd.DataFrame(columns=BAR_COLUMNS, index=pd.DatetimeIndex([], name="date")), {}
        try:
            meta = json.loads(meta_path.read_text())
            if meta["ticker"] != ticker or meta["provider"] != self.provider.name:
                raise ValueError("Cache identity mismatch")
            frame = pd.read_parquet(path)
            if not set(BAR_COLUMNS) <= set(frame) or not isinstance(frame.index, pd.DatetimeIndex):
                raise ValueError("Invalid cache schema")
            return frame.sort_index(), meta
        except (ValueError, KeyError, OSError):
            return pd.DataFrame(columns=BAR_COLUMNS, index=pd.DatetimeIndex([], name="date")), {}

    def _write(self, ticker, frame, meta):
        path, meta_path = self._paths(ticker)
        tag = uuid4().hex
        temp = path.with_suffix(f".{tag}.parquet.tmp")
        temp_meta = meta_path.with_suffix(f".{tag}.json.tmp")
        frame.to_parquet(temp)
        temp_meta.write_text(json.dumps(meta, indent=2))
        temp.replace(path)
        temp_meta.replace(meta_path)

    def get_many(self, tickers: list[str], start: date, end: date, *,
                 refresh_recent: bool = False, force: bool = False, refresh_now: bool = False,
                 cache_only: bool = False, retry_missing: bool = False, progress=None) -> CachedBatch:
        if start > end:
            raise ValueError("History start must not be after end")
        # One writer per provider cache, across processes. Reads/writes are atomic.
        with FileLock(str(self.directory / "cache.lock"), timeout=300):
            return self._get_many(tickers, start, end, refresh_recent, force, cache_only, retry_missing, progress,
                                  refresh_now)

    def _get_many(self, tickers, start, end, refresh_recent, force, cache_only, retry_missing, progress,
                  refresh_now=False):
        result = CachedBatch()
        stored = {t: self._read(t) for t in dict.fromkeys(tickers)}
        plans = {}
        now = datetime.now(timezone.utc)
        for t, (frame, meta) in stored.items():
            spans = []
            if not meta or force:
                spans.append((min(start, date.fromisoformat(meta["coverage_start"])) if meta else start,
                              max(end, date.fromisoformat(meta["coverage_end"])) if meta else end))
            else:
                left, right = date.fromisoformat(meta["coverage_start"]), date.fromisoformat(meta["coverage_end"])
                if start < left:
                    spans.append((start, min(end, left + timedelta(days=14))))
                if end > right:
                    spans.append((max(start, right - timedelta(days=14)), end))
                stamp = datetime.fromisoformat(meta["last_success"])
                if refresh_now or (refresh_recent and (now - stamp).total_seconds() > 6 * 3600 and end <= right):
                    spans.append((max(start, end - timedelta(days=21)), end))
                if retry_missing and not frame.empty and frame.adj_close.notna().any():
                    first_valid = frame.adj_close.first_valid_index().date()
                    idx = sessions(max(start, first_valid), end)
                    missing = frame.adj_close.reindex(idx).isna()
                    if missing.any():
                        gaps = idx[missing]
                        spans.append((max(start, gaps[0].date() - timedelta(days=14)), gaps[-1].date()))
            if spans and not cache_only:
                # A single contiguous request per ticker avoids mixing partial adjustment vintages.
                span = (min(s[0] for s in spans), max(s[1] for s in spans))
                plans.setdefault(span, []).append(t)
        work = [(span, group[i:i + 40]) for span, group in plans.items() for i in range(0, len(group), 40)]
        completed, failed_batches = 0, 0
        total = sum(len(group) for _, group in work)
        for task_index, ((left, right), group) in enumerate(work):
            result.downloads.append({"tickers": list(group), "start": str(left), "end": str(right),
                                     "reason": "Full history refresh" if force else
                                     "Explicit price update" if refresh_now else "Missing history / requested refresh"})
            batch = self.provider.download(group, left, right)
            result.errors.update(batch.errors)
            failed_batches = failed_batches + 1 if not batch.frames else 0
            for t, fresh in batch.frames.items():
                old, meta = stored[t]
                coverage_start = min(left, date.fromisoformat(meta["coverage_start"])) if meta else left
                coverage_end = max(right, date.fromisoformat(meta["coverage_end"])) if meta else right
                if force:
                    # This request already covers the entire cached span, including revisions.
                    combined = fresh
                elif not old.empty and _revised(old, fresh):
                    result.warnings.append(f"{t}: adjusted/raw history changed; refreshing the full cached span.")
                    result.downloads.append({"tickers": [t], "start": str(coverage_start), "end": str(coverage_end),
                                             "reason": "Adjustment revision: refresh full cached span"})
                    full = self.provider.download([t], coverage_start, coverage_end)
                    if t not in full.frames:
                        result.errors[t] = "Adjustment revision detected; full refresh failed. Retained old cache."
                        continue
                    fresh = full.frames[t]
                    combined = fresh
                elif old.empty:
                    combined = fresh
                else:
                    # New complete bars override old bars; missing provider rows do not erase valid cache.
                    combined = fresh.combine_first(old).sort_index()
                stamp = datetime.now(timezone.utc).isoformat()
                updated = {
                    "ticker": t, "provider": self.provider.name, "schema_version": 1,
                    "coverage_start": coverage_start.isoformat(), "coverage_end": coverage_end.isoformat(),
                    "last_success": stamp, "last_price_date": combined["adj_close"].last_valid_index().date().isoformat(),
                    "price_policy": "Raw provider OHLC; separately adjusted close; no price forward-fill",
                }
                self._write(t, combined, updated)
                stored[t] = (combined, updated)
                result.errors.pop(t, None)
            completed += len(group)
            if progress:
                progress(completed, total)
            if failed_batches >= 2:
                for _, remaining in work[task_index + 1:]:
                    result.errors.update({t: "Stopped downloads after two entirely failed batches; retry later."
                                          for t in remaining})
                result.warnings.append("Network circuit breaker stopped further requests after two failed batches.")
                break
        expected = sessions(start, end)
        for t, (frame, meta) in stored.items():
            aligned = frame.reindex(expected)
            aligned.index.name = "date"
            result.frames[t] = aligned
            result.metadata[t] = meta
            if not aligned["adj_close"].notna().any():
                result.errors.setdefault(t, "No cached/downloaded prices in the requested period")
            elif pd.isna(aligned["adj_close"].iloc[-1]):
                result.errors.setdefault(t, "Missing price for the selected completed session; no stale-date substitution")
        return result
