"""Causal screen orchestration and wide, exportable results."""
from dataclasses import dataclass, field
from datetime import date
import hashlib
import math

import pandas as pd

from .calendar import sessions
from .indicators import add_indicators
from .models import ScreenConfig
from .rules import RuleResult, combine, evaluate_rule


@dataclass
class ScreenRun:
    config: ScreenConfig
    screen_date: date
    table: pd.DataFrame
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    evaluations: dict[str, dict[str, RuleResult]] = field(default_factory=dict)

    @property
    def passing(self) -> pd.DataFrame:
        return self.table[self.table["passed"]].copy()

    def summary(self) -> dict:
        total = len(self.table)
        return {
            "requested": total,
            "analyzed": int(self.table.status.isin(["PASS", "FAIL"]).sum()),
            "insufficient": int(self.table.status.eq("INSUFFICIENT").sum()),
            "passing": int(self.table.passed.sum()),
            "passing_pct": float(100 * self.table.passed.sum() / total) if total else 0.0,
        }


def screen(universe: pd.DataFrame, prices: dict[str, pd.DataFrame], config: ScreenConfig,
           screen_date: date, *, indicator_cache: dict | None = None, progress=None) -> ScreenRun:
    config.validate()
    active_rules = [r for r in config.rules if r.enabled]
    run = ScreenRun(config, screen_date, pd.DataFrame())
    rows = []
    enabled_mas = [m for m in config.moving_averages if m.enabled]
    signature = (str(screen_date), config.price_source, config.return_kind,
                 tuple((m.kind, m.period) for m in enabled_mas))
    for i, company in enumerate(universe.to_dict("records")):
        ticker = company["ticker"]
        frame = prices.get(ticker)
        # The input may contain future rows: clip BEFORE computing any indicator.
        if frame is None or frame.empty:
            frame = pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"],
                                 index=pd.DatetimeIndex([], name="date"), dtype=float)
        frame = frame.loc[frame.index <= pd.Timestamp(screen_date)].copy()
        if not frame.empty:
            frame = frame.reindex(sessions(frame.index[0].date(), screen_date))
        frame.index.name = "date"
        fingerprint = hashlib.blake2b(pd.util.hash_pandas_object(frame, index=True).values.tobytes(),
                                     digest_size=16).digest()
        key = (ticker, signature, fingerprint)
        prepared = indicator_cache.get(key) if indicator_cache is not None else None
        if prepared is None:
            prepared = add_indicators(frame, enabled_mas, config.price_source, config.return_kind)
            if indicator_cache is not None:
                indicator_cache[key] = prepared
        evaluations = {r.id: evaluate_rule(prepared, r) for r in active_rules}
        state = combine(config, evaluations)
        row = {
            **company, "latest_adjusted_price": math.nan, "latest_date": "",
            "screen_date": screen_date.isoformat(),
            "daily_return_pct": math.nan, "return_5d_pct": math.nan, "return_20d_pct": math.nan,
            "rules_passed": sum(e.passed for e in evaluations.values()),
            "rules_total": len(evaluations), "rules_unavailable": sum(not e.valid for e in evaluations.values()),
            "status": "PASS" if state is True else ("FAIL" if state is False else "INSUFFICIENT"),
            "passed": state is True,
        }
        if not prepared.empty:
            row["latest_adjusted_price"] = prepared.adj_close.iloc[-1]
            last_date = prepared.adj_close.last_valid_index()
            row["latest_date"] = last_date.date().isoformat() if last_date is not None else ""
            for n, name in ((1, "daily_return_pct"), (5, "return_5d_pct"), (20, "return_20d_pct")):
                row[name] = float(100 * prepared[f"return_{n}d"].iloc[-1])
            for ma in enabled_mas:
                row[ma.key] = float(prepared[ma.key].iloc[-1])
        for r in active_rules:
            evaluation = evaluations[r.id]
            prefix = r.id
            row[f"{prefix}.pass"] = evaluation.passed
            row[f"{prefix}.value"] = evaluation.value
            row[f"{prefix}.reason"] = evaluation.reason
            for metric, value in evaluation.metrics.items():
                if isinstance(value, (int, float, bool)) or value is None:
                    row[f"{prefix}.{metric}"] = value
        primary = next((evaluations[r.id].metrics for r in active_rules
                        if r.ma != "PRICE" and evaluations[r.id].valid), {})
        for metric in ("normalized_slope", "pct_change", "r2", "longest_streak"):
            row[f"rank_{metric}"] = primary.get(metric, math.nan)
        row["data_notes"] = " | ".join(f"{r.name}: {evaluations[r.id].reason}" for r in active_rules
                                     if not evaluations[r.id].valid)
        rows.append(row)
        run.frames[ticker], run.evaluations[ticker] = prepared, evaluations
        if progress and ((i + 1) % 10 == 0 or i + 1 == len(universe)):
            progress(i + 1, len(universe))
    run.table = pd.DataFrame(rows)
    if run.table.empty:
        raise ValueError("Choose at least one ticker")
    return run
