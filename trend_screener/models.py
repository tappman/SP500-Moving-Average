"""Validated, serializable configuration shared by UI, CLI and screening engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import re
from datetime import date
from typing import Any
from uuid import uuid4

from .risk import RiskSettings


METHODS = {
    "normalized_slope": "Regression: normalized slope (% / session)",
    "slope": "Regression: raw slope (price / session)",
    "net_increase": "Net increase with minimum change (%)",
    "pct_change": "Net percentage change (%)",
    "strict": "Strictly increasing (true = 1)",
    "positive_count": "Positive transition count",
    "positive_pct": "Positive transitions (%)",
    "r2": "Regression R-squared",
    "negative_count": "Downward transition count",
    "max_drawdown_pct": "Maximum MA drawdown magnitude (%)",
    "longest_streak": "Longest rising streak (transitions)",
    "accel_pct": "Percentage-change acceleration (percentage points)",
    "accel_slope": "Normalized slope acceleration (percentage points / session)",
    "turn_up": "Slope turning up (true = 1)",
    "relative": "Price / MA or MA / MA difference (%)",
    "cross_up": "Bullish crossover within window (true = 1)",
    "cross_down": "Bearish crossover within window (true = 1)",
    "separation_change": "Change in absolute MA separation (percentage points)",
}
RELATION_METHODS = {"relative", "cross_up", "cross_down", "separation_change"}
REGRESSION_METHODS = {"slope", "normalized_slope", "r2", "accel_slope", "turn_up"}
BOOL_METHODS = {"strict", "turn_up", "cross_up", "cross_down"}
OPERATORS = (">", ">=", "<", "<=", "==", "!=")


def uid(prefix: str = "r") -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def positive_int(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")


@dataclass
class MovingAverage:
    kind: str = "SMA"
    period: int = 20
    enabled: bool = True
    show: bool = True

    @property
    def key(self) -> str:
        return f"{self.kind}{self.period}"

    def validate(self) -> None:
        if self.kind not in {"SMA", "EMA"}:
            raise ValueError("Moving average type must be SMA or EMA")
        positive_int(self.period, "Moving average period")
        if not isinstance(self.enabled, bool) or not isinstance(self.show, bool):
            raise ValueError("MA enabled and chart controls must be booleans")


@dataclass
class Group:
    id: str = "root"
    name: str = "All conditions"
    logic: str = "AND"
    parent: str = ""


@dataclass
class Rule:
    id: str = field(default_factory=uid)
    name: str = "MA20 rising"
    ma: str = "SMA20"
    method: str = "normalized_slope"
    lookback: int = 10
    operator: str = ">"
    threshold: float = 0.0
    enabled: bool = True
    group: str = "root"
    other: str = "SMA50"
    min_r2: float | None = None
    min_positive_pct: float | None = None
    reversal_lag: int = 5
    confirmation: int = 1
    allow_flat: bool = True
    positive_current: bool = True
    positive_previous: bool = False

    @property
    def observation_count(self) -> int:
        if self.method == "accel_pct":
            return 2 * self.lookback + 1
        if self.method == "accel_slope":
            return 2 * self.lookback
        if self.method == "turn_up":
            return self.lookback + max(self.reversal_lag, self.confirmation - 1)
        if self.method in REGRESSION_METHODS:
            return self.lookback
        if self.method == "relative":
            return 1
        return self.lookback + 1


@dataclass
class ScreenConfig:
    name: str = "All Moving Averages Rising"
    moving_averages: list[MovingAverage] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    groups: list[Group] = field(default_factory=lambda: [Group()])
    price_source: str = "adj_close"
    return_kind: str = "simple"
    data_settings: dict = field(default_factory=dict)
    risk: RiskSettings = field(default_factory=RiskSettings)
    schema_version: int = 1

    def validate(self, require_rules: bool = True) -> None:
        self.risk.validate()
        if self.schema_version != 1:
            raise ValueError("Unsupported configuration schema version")
        if self.price_source not in {"adj_close", "close"}:
            raise ValueError("Price source must be adj_close or close")
        if self.return_kind not in {"simple", "log"}:
            raise ValueError("Returns must be simple or log")
        if not isinstance(self.data_settings, dict):
            raise ValueError("Data settings must be a JSON object")
        for name in ("requested_date", "custom_start", "custom_end"):
            if name in self.data_settings:
                date.fromisoformat(self.data_settings[name])
        choices = {
            "source": {"Live Yahoo Finance", "Synthetic demo (offline)"},
            "universe_mode": {"S&P 500 (current constituents)", "Sector", "Custom tickers", "Single stock",
                              "S&P 500 index", "Historical membership CSV"},
            "time_mode": {"Latest completed session", "Historical date"},
            "period": {"3 months", "6 months", "1 year", "2 years", "3 years", "5 years", "10 years", "Custom dates"},
        }
        for name, allowed in choices.items():
            if name in self.data_settings and self.data_settings[name] not in allowed:
                raise ValueError(f"Invalid data setting: {name}")
        if "ticker_aliases" in self.data_settings:
            aliases = self.data_settings["ticker_aliases"]
            if not isinstance(aliases, dict) or any(
                not isinstance(k, str) or not isinstance(v, str)
                or not re.fullmatch(r"[\^A-Z0-9][A-Z0-9^=_-]{0,24}", k)
                or not re.fullmatch(r"[\^A-Z0-9][A-Z0-9^=_-]{0,24}", v) for k, v in aliases.items()
            ):
                raise ValueError("Ticker aliases must map valid uppercase ticker symbols")
        keys = set()
        for ma in self.moving_averages:
            ma.validate()
            if ma.key in keys:
                raise ValueError(f"Duplicate moving average: {ma.key}")
            keys.add(ma.key)
        active_keys = {ma.key for ma in self.moving_averages if ma.enabled}
        groups = {g.id: g for g in self.groups}
        if len(groups) != len(self.groups) or "root" not in groups:
            raise ValueError("Groups need unique IDs and one root group")
        if groups["root"].parent:
            raise ValueError("Root group cannot have a parent")
        for g in self.groups:
            if not isinstance(g.id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", g.id):
                raise ValueError("Group IDs must contain letters, numbers, hyphens or underscores")
            if g.logic not in {"AND", "OR"}:
                raise ValueError("Group logic must be AND or OR")
            seen = {g.id}
            parent = g.parent
            while parent:
                if parent in seen or parent not in groups:
                    raise ValueError("Rule groups contain a cycle or unknown parent")
                seen.add(parent)
                parent = groups[parent].parent
            if "root" not in seen:
                raise ValueError("Every group must descend from root")
        ids = set()
        for rule in self.rules:
            if not isinstance(rule.id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", rule.id):
                raise ValueError("Rule IDs must contain letters, numbers, hyphens or underscores")
            if rule.id in ids:
                raise ValueError("Rule IDs must be unique")
            ids.add(rule.id)
            if not isinstance(rule.enabled, bool):
                raise ValueError("Rule enabled must be a boolean")
            if rule.group not in groups:
                raise ValueError(f"Unknown group for {rule.name}")
            if rule.method not in METHODS or rule.operator not in OPERATORS:
                raise ValueError(f"Unknown method or operator for {rule.name}")
            positive_int(rule.lookback, "Lookback")
            positive_int(rule.reversal_lag, "Reversal lag")
            positive_int(rule.confirmation, "Confirmation count")
            if rule.method in REGRESSION_METHODS and rule.lookback < 2:
                raise ValueError("Regression requires at least 2 observations")
            if rule.method == "turn_up" and rule.confirmation > rule.reversal_lag:
                raise ValueError("Turning-up confirmation must not exceed reversal lag")
            if isinstance(rule.threshold, bool) or not isinstance(rule.threshold, (int, float)):
                raise ValueError("Threshold must be numeric")
            if not math.isfinite(rule.threshold):
                raise ValueError("Threshold must be finite")
            if rule.method == "turn_up" and rule.threshold < 0:
                raise ValueError("Minimum turning-up normalized slope must be nonnegative")
            if any(not isinstance(getattr(rule, name), bool) for name in
                   ("allow_flat", "positive_current", "positive_previous")):
                raise ValueError("Rule options must be booleans")
            if rule.min_r2 is not None and not 0 <= rule.min_r2 <= 1:
                raise ValueError("R-squared threshold must be between 0 and 1")
            if rule.min_positive_pct is not None and not 0 <= rule.min_positive_pct <= 100:
                raise ValueError("Positive transition percentage must be between 0 and 100")
            if rule.enabled:
                allowed = active_keys | ({"PRICE"} if rule.method in RELATION_METHODS else set())
                if rule.ma not in allowed:
                    raise ValueError(f"{rule.name}: choose an enabled moving average")
                if rule.method in RELATION_METHODS and rule.other not in active_keys:
                    raise ValueError(f"{rule.name}: choose an enabled comparison moving average")
                if rule.method in RELATION_METHODS and rule.ma == rule.other:
                    raise ValueError("Compare two different series")
        if require_rules and not any(r.enabled for r in self.rules):
            raise ValueError("Enable at least one rule before running a screen")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, allow_nan=False)

    @classmethod
    def from_dict(cls, data: dict, *, require_rules: bool = False) -> ScreenConfig:
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object")
        try:
            obj = cls(**{
                **data,
                "moving_averages": [MovingAverage(**m) for m in data.get("moving_averages", [])],
                "rules": [Rule(**r) for r in data.get("rules", [])],
                "groups": [Group(**g) for g in data.get("groups", [asdict(Group())])],
                "risk": RiskSettings(**data.get("risk", {})),
            })
            obj.validate(require_rules=require_rules)
        except (TypeError, KeyError, AttributeError, RecursionError) as exc:
            raise ValueError(f"Invalid configuration structure: {exc}") from exc
        return obj

    @classmethod
    def from_json(cls, value: str) -> ScreenConfig:
        try:
            return cls.from_dict(json.loads(value))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

    def required_history(self) -> int:
        """Conservative session count, including EMA burn-in and all dependent windows."""
        longest = max((r.observation_count for r in self.rules if r.enabled), default=21)
        period = max((m.period * (5 if m.kind == "EMA" else 1)
                      for m in self.moving_averages if m.enabled), default=1)
        performance = max(self.risk.lookbacks, default=0) + 1 if self.risk.enabled else 0
        return max(21, period + longest + 5, performance)
