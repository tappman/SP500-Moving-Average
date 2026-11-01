"""Editable built-ins plus atomic on-disk JSON preset persistence."""
from dataclasses import replace
import hashlib
from pathlib import Path

from .models import MovingAverage, Rule, ScreenConfig


def builtins() -> list[ScreenConfig]:
    def ma(*periods):
        return [MovingAverage(period=n) for n in periods]

    def slope(p, n):
        return Rule(id=f"slope_{p}", name=f"MA{p} slope positive", ma=f"SMA{p}", lookback=n)

    def relation(a, b, name):
        return Rule(id=f"above_{a}_{b}", name=name, ma=a, other=b, method="relative", lookback=1)

    return [
        ScreenConfig(name="All Moving Averages Rising", moving_averages=ma(5, 20, 50),
                     rules=[slope(5, 5), slope(20, 10), slope(50, 20)]),
        ScreenConfig(name="Strong Bullish Alignment", moving_averages=ma(5, 20, 50, 200),
                     rules=[relation("SMA5", "SMA20", "MA5 above MA20"),
                            relation("SMA20", "SMA50", "MA20 above MA50"),
                            relation("SMA50", "SMA200", "MA50 above MA200"),
                            slope(20, 10), slope(50, 20),
                            relation("PRICE", "SMA20", "Price above MA20")]),
        ScreenConfig(name="Smoothly Rising MA20", moving_averages=ma(20),
                     rules=[replace(slope(20, 15), min_r2=0.8, min_positive_pct=80.0)]),
        ScreenConfig(name="Moving Average Turning Up", moving_averages=ma(20),
                     rules=[Rule(id="turn_20", name="MA20 turning up", ma="SMA20", method="turn_up",
                                 lookback=10, operator="==", threshold=0.0, allow_flat=False),
                            relation("PRICE", "SMA20", "Price above MA20")]),
        ScreenConfig(name="Accelerating Upward Trend", moving_averages=ma(5, 20),
                     rules=[slope(5, 5), slope(20, 10),
                            Rule(id="accel_20", name="MA20 slope accelerating", ma="SMA20",
                                 method="accel_slope", lookback=10, positive_previous=True),
                            relation("SMA5", "SMA20", "MA5 above MA20")]),
    ]


class PresetStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Enter a preset name")
        return self.directory / (hashlib.sha256(name.strip().encode()).hexdigest()[:24] + ".json")

    def save(self, config: ScreenConfig) -> None:
        config.validate()
        path = self._path(config.name)
        temp = path.with_suffix(".tmp")
        temp.write_text(config.to_json(), encoding="utf-8")
        temp.replace(path)

    def list(self) -> dict[str, ScreenConfig]:
        configs = {}
        for path in sorted(self.directory.glob("*.json")):
            try:
                config = ScreenConfig.from_json(path.read_text(encoding="utf-8"))
                configs[config.name] = config
            except ValueError:
                continue
        return configs

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def rename(self, old_name: str, new_name: str) -> None:
        existing = self.list()
        if old_name not in existing:
            raise ValueError("Preset no longer exists")
        if new_name.strip() != old_name and new_name.strip() in existing:
            raise ValueError("A preset with that name already exists")
        config = replace(existing[old_name], name=new_name.strip())
        self.save(config)
        if old_name != config.name:
            self.delete(old_name)
