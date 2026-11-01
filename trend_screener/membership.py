"""User-supplied historical membership intervals; no implied data-feed completeness."""
from __future__ import annotations

from datetime import date
from io import StringIO
import hashlib
import json
from pathlib import Path

import pandas as pd

from .universe import provider_symbol


class MembershipHistory:
    """Intervals are start-inclusive, end-exclusive. Blank end means still active."""
    def __init__(self, frame, coverage_start: date, coverage_end: date, source: str):
        if coverage_start > coverage_end:
            raise ValueError("Membership coverage start must precede its end")
        if not str(source).strip():
            raise ValueError("Describe the membership data source")
        if not {"ticker", "start_date", "end_date"} <= set(frame):
            raise ValueError("Membership CSV requires ticker, start_date and end_date")
        f = frame.copy()
        if f.ticker.isna().any() or f.ticker.astype(str).str.strip().eq("").any():
            raise ValueError("Every membership row needs a ticker")
        f["ticker"] = f.ticker.map(lambda x: provider_symbol(str(x)))
        if f.empty:
            raise ValueError("Membership CSV is empty")
        for col in ("start_date", "end_date"):
            raw = f[col].replace(r"^\s*$", pd.NA, regex=True)
            converted = pd.to_datetime(raw, errors="coerce", format="%Y-%m-%d")
            if (raw.notna() & converted.isna()).any() or (col == "start_date" and converted.isna().any()):
                raise ValueError(f"{col} must use YYYY-MM-DD; only end_date may be blank")
            f[col] = converted
        if ((f.end_date.notna()) & (f.end_date <= f.start_date)).any():
            raise ValueError("Membership interval end must be after start")
        for col, default in (("company", ""), ("sector", "Unspecified"), ("industry", "")):
            if col not in f:
                f[col] = default
            f[col] = f[col].fillna(default).astype(str)
        f.loc[f.company.eq(""), "company"] = f.ticker
        f = f[["ticker", "start_date", "end_date", "company", "sector", "industry"]]
        f = f.sort_values(["ticker", "start_date"]).reset_index(drop=True)
        for ticker, group in f.groupby("ticker"):
            ends, starts = group.end_date.tolist(), group.start_date.tolist()
            if any(pd.isna(end) or start < end for start, end in zip(starts[1:], ends[:-1])):
                raise ValueError(f"Overlapping membership intervals for {ticker}")
        self.frame, self.coverage_start, self.coverage_end, self.source = f, coverage_start, coverage_end, source
        self.digest = hashlib.sha256((self.to_csv() + str(coverage_start) + str(coverage_end)
                                     + source).encode()).hexdigest()

    @classmethod
    def from_csv(cls, text: str, coverage_start: date, coverage_end: date, source: str):
        return cls(pd.read_csv(StringIO(text), dtype=str), coverage_start, coverage_end, source)

    def require_coverage(self, start: date, end: date):
        if start < self.coverage_start or end > self.coverage_end:
            raise ValueError(f"Membership source covers {self.coverage_start} through {self.coverage_end}, "
                             f"not the requested {start} through {end}")

    def at(self, day: date) -> pd.DataFrame:
        self.require_coverage(day, day)
        t = pd.Timestamp(day)
        f = self.frame[self.frame.start_date.le(t) & (self.frame.end_date.isna() | self.frame.end_date.gt(t))]
        return f[["ticker", "company", "sector", "industry"]].assign(symbol=lambda x: x.ticker).reset_index(drop=True)

    def universe(self, start: date, end: date) -> pd.DataFrame:
        self.require_coverage(start, end)
        f = self.frame[self.frame.start_date.le(pd.Timestamp(end))
                       & (self.frame.end_date.isna() | self.frame.end_date.gt(pd.Timestamp(start)))]
        return f.drop_duplicates("ticker")[["ticker", "company", "sector", "industry"]].assign(
            symbol=lambda x: x.ticker).reset_index(drop=True)

    def to_csv(self):
        return self.frame.to_csv(index=False, date_format="%Y-%m-%d")

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        # One atomic JSON write preserves coverage/source together with the intervals.
        target = directory / "membership.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps({"csv": self.to_csv(), "coverage_start": str(self.coverage_start),
                                    "coverage_end": str(self.coverage_end), "source": self.source}))
        temp.replace(target)

    @classmethod
    def load(cls, directory):
        path = Path(directory) / "membership.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return cls.from_csv(data["csv"], date.fromisoformat(data["coverage_start"]),
                            date.fromisoformat(data["coverage_end"]), data["source"])
