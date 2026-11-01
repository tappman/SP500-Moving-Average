"""Reproducible headless screens using the same engine as the dashboard."""
import argparse
from datetime import date
from pathlib import Path

from .cache import PriceCache
from .calendar import history_start, latest_completed_session
from .demo import DemoProvider, demo_universe
from .engine import screen
from .models import ScreenConfig
from .presets import builtins
from .providers import AliasedProvider, YFinanceProvider
from .universe import UniverseService, custom_universe, parse_tickers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Use synthetic prices, never real quotes")
    parser.add_argument("--tickers", help="Comma/space-separated Yahoo tickers; default is current S&P 500")
    parser.add_argument("--date", type=date.fromisoformat, help="Historical screen date")
    parser.add_argument("--config", type=Path, help="Saved JSON configuration")
    parser.add_argument("--output", type=Path, default=Path("screen-results.csv"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".screener"))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    config = ScreenConfig.from_json(args.config.read_text()) if args.config else builtins()[0]
    end = latest_completed_session(requested=args.date)
    start = history_start(end, end, config.required_history())
    if args.tickers:
        universe = custom_universe(parse_tickers(args.tickers))
    elif args.demo:
        universe = demo_universe()
    else:
        snapshot = UniverseService(args.cache_dir / "universe").get()
        universe = snapshot.frame
        print(f"Current constituents retrieved: {snapshot.retrieved_at}; historical screens have survivorship bias.")
        if snapshot.warning:
            print(snapshot.warning)
    aliases = config.data_settings.get("ticker_aliases", {})
    universe["provider_ticker"] = universe.ticker.map(lambda t: aliases.get(t, t))
    provider = AliasedProvider(DemoProvider() if args.demo else YFinanceProvider(), aliases)
    data = PriceCache(args.cache_dir / "prices", provider).get_many(
        universe.ticker.tolist(), start, end, force=args.refresh,
        refresh_recent=not args.date,
    )
    run = screen(universe, data.frames, config, end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    run.table.to_csv(args.output, index=False)
    print(f"{'SYNTHETIC DEMO' if args.demo else 'Yahoo Finance'}; screen date {end}; {run.summary()}")
    if data.errors:
        print(f"Download/cache issues: {data.errors}")
    print(f"Saved {args.output.resolve()}")


if __name__ == "__main__":
    main()
