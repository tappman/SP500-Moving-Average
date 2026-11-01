"""NYSE sessions including holidays, daylight saving and early closes."""
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd
import pandas_market_calendars as mcal


@lru_cache(maxsize=128)
def sessions(start: str | date, end: str | date) -> pd.DatetimeIndex:
    schedule = mcal.get_calendar("NYSE").schedule(start_date=start, end_date=end)
    return pd.DatetimeIndex(schedule.index).tz_localize(None).normalize()


def latest_completed_session(now=None, requested: date | None = None, delay_minutes: int = 15) -> date:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    local_day = now.tz_convert("America/New_York").date()
    end = min(requested, local_day) if requested else local_day
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=end - timedelta(days=35), end_date=end
    )
    eligible = schedule[schedule.market_close + pd.Timedelta(minutes=delay_minutes) <= now]
    if eligible.empty:
        raise ValueError("No completed trading session found")
    return eligible.index[-1].date()


def history_start(display_start: date, screen_date: date, required_sessions: int) -> date:
    # Get exact session counts rather than assume calendar days are trading days.
    span = max(40, int(required_sessions * 1.8) + 30)
    while True:
        earliest = date(1900, 1, 1)
        span = min(span, (screen_date - earliest).days)
        idx = sessions(screen_date - timedelta(days=span), screen_date)
        if len(idx) >= required_sessions:
            return min(display_start, idx[-required_sessions].date())
        if screen_date - timedelta(days=span) <= earliest:
            raise ValueError(f"Requested warm-up needs {required_sessions} sessions; "
                             "history before 1900 is unsupported. Reduce the MA period or lookback.")
        span *= 2
