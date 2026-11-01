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

    def annotate_results(self, table, benchmark=None):
        result = table.copy()
        result["price_data_issue"] = result.ticker.map(self.errors).astype("string").fillna("")
        result["last_price_download_utc"] = result.ticker.map(
            {t: meta.get("last_success", "") for t, meta in self.metadata.items()}).astype("string").fillna("")
        if benchmark:
            result["benchmark_data_issue"] = self.errors.get(benchmark, "")
            result["benchmark_last_download_utc"] = self.metadata.get(benchmark, {}).get("last_success", "")
        return result


PRICE_COLUMNS = BAR_COLUMNS[:-1]


def _price_frame(frame):
    if (not isinstance(frame, pd.DataFrame) or not set(BAR_COLUMNS) <= set(frame)
            or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.has_duplicates
            or frame.index.hasnans or frame.index.tz is not None
            or not frame.index.equals(frame.index.normalize())):
        raise ValueError("Invalid daily price-frame schema/index")
    frame = frame[BAR_COLUMNS].apply(pd.to_numeric, errors="coerce").astype(float).sort_index()
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame[PRICE_COLUMNS] = frame[PRICE_COLUMNS].where(frame[PRICE_COLUMNS] > 0)
    frame["volume"] = frame.volume.where(frame.volume >= 0)
    if not frame.adj_close.notna().any():
        raise ValueError("No valid adjusted prices in response")
    return frame


def _replacement_complete(old, fresh):
    """Never discard a previously usable price when replacing an adjustment vintage."""
    required = old[PRICE_COLUMNS].notna()
    available = fresh.reindex(old.index)[PRICE_COLUMNS].notna()
    return not (required & ~available).to_numpy().any()


def _has_overlap(old, fresh):
    common = old.index.intersection(fresh.index)
    return bool((old.loc[common, "adj_close"].notna() & fresh.loc[common, "adj_close"].notna()).any())


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
        if not path.exists():
            return pd.DataFrame(columns=BAR_COLUMNS, index=pd.DatetimeIndex([], name="date")), {}
        try:
            frame = _price_frame(pd.read_parquet(path))
        except (ValueError, TypeError, OSError):
            return pd.DataFrame(columns=BAR_COLUMNS, index=pd.DatetimeIndex([], name="date")), {}
        try:
            meta = json.loads(meta_path.read_text())
            if meta["ticker"] != ticker or meta["provider"] != self.provider.name or meta["schema_version"] != 1:
                raise ValueError("Cache identity mismatch")
            left, right = date.fromisoformat(meta["coverage_start"]), date.fromisoformat(meta["coverage_end"])
            stamp = datetime.fromisoformat(meta["last_success"])
            if (left > right or stamp.tzinfo is None or left > frame.index[0].date()
                    or right < frame.index[-1].date()):
                raise ValueError("Invalid cache coverage/update timestamp")
            return frame, meta
        except (ValueError, TypeError, KeyError, OSError):
            # Keep usable bars; reconstruct metadata by revalidating their FULL saved span.
            return frame, {}

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
                saved_start = date.fromisoformat(meta["coverage_start"]) if meta else (frame.index[0].date() if len(frame) else start)
                saved_end = date.fromisoformat(meta["coverage_end"]) if meta else (frame.index[-1].date() if len(frame) else end)
                spans.append((min(start, saved_start), max(end, saved_end)))
                if not meta and not frame.empty:
                    result.warnings.append(f"{t}: cache metadata is invalid/missing; saved bars retained. "
                                           "A permitted download will revalidate their full span.")
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
                try:
                    fresh = _price_frame(fresh).loc[str(left):str(right)]
                    if fresh.empty or not fresh.adj_close.notna().any():
                        raise ValueError("No valid prices in requested range")
                except (ValueError, TypeError, KeyError) as exc:
                    result.errors[t] = f"Invalid price response: {exc}. Retained old cache."
                    continue
                coverage_start = min(left, date.fromisoformat(meta["coverage_start"])) if meta else left
                coverage_end = max(right, date.fromisoformat(meta["coverage_end"])) if meta else right
                if force or not meta:
                    if not old.empty and not _replacement_complete(old, fresh):
                        result.errors[t] = "Incomplete full refresh; retained old cache and last successful update."
                        continue
                    combined = fresh
                elif not old.empty and (_revised(old, fresh) or not _has_overlap(old, fresh)):
                    reason = "Adjustment revision" if _has_overlap(old, fresh) else "Missing adjustment-check overlap"
                    result.warnings.append(f"{t}: {reason}; revalidating the full cached span.")
                    result.downloads.append({"tickers": [t], "start": str(coverage_start), "end": str(coverage_end),
                                             "reason": f"{reason}: refresh full cached span"})
                    full = self.provider.download([t], coverage_start, coverage_end)
                    if t not in full.frames:
                        result.errors[t] = "Adjustment revision detected; full refresh failed. Retained old cache."
                        continue
                    try:
                        fresh = _price_frame(full.frames[t]).loc[str(coverage_start):str(coverage_end)]
                        if not _replacement_complete(old, fresh):
                            raise ValueError("incomplete full price history")
                    except (ValueError, TypeError, KeyError) as exc:
                        result.errors[t] = f"Incomplete full refresh ({exc}); retained old cache."
                        continue
                    combined = fresh
                elif old.empty:
                    combined = fresh
                else:
                    # Replace whole rows, never splice missing cells across price vintages.
                    known = old.reindex(fresh.index)[PRICE_COLUMNS].notna()
                    usable = fresh.adj_close.notna() & ~(known & fresh[PRICE_COLUMNS].isna()).any(axis=1)
                    if not usable.any():
                        result.errors[t] = "Incomplete update rows; retained old cache."
                        continue
                    combined = old.reindex(old.index.union(fresh.index)).copy()
                    combined.loc[fresh.index[usable], BAR_COLUMNS] = fresh.loc[usable, BAR_COLUMNS]
                    combined = combined.sort_index()
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
