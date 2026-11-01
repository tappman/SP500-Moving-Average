from datetime import date
import json
from zipfile import ZipFile
from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from trend_screener.cache import PriceCache
from trend_screener.calendar import history_start, latest_completed_session, sessions
from trend_screener.demo import DemoProvider, demo_universe
from trend_screener.engine import screen
from trend_screener.exports import excel_bytes, history_zip
from trend_screener.models import Group, MovingAverage, Rule, ScreenConfig
from trend_screener.presets import PresetStore, builtins
from trend_screener.providers import AliasedProvider, normalize_bars
from trend_screener.research import forward_returns
from trend_screener.universe import normalize_constituents, parse_tickers, provider_symbol


def test_calendar_holiday_weekend_and_intraday():
    assert latest_completed_session("2024-07-04 20:00:00Z") == date(2024, 7, 3)
    assert latest_completed_session("2024-07-08 17:00:00Z") == date(2024, 7, 5)
    assert latest_completed_session("2024-07-08 20:14:00Z") == date(2024, 7, 5)
    assert latest_completed_session("2024-07-08 20:15:00Z") == date(2024, 7, 8)
    assert latest_completed_session("2024-07-13 12:00:00Z") == date(2024, 7, 12)
    assert latest_completed_session("2024-07-15 23:00:00Z", requested=date(2024, 7, 6)) == date(2024, 7, 5)


def test_calendar_early_close():
    assert latest_completed_session("2024-11-29 18:14:00Z") == date(2024, 11, 27)
    assert latest_completed_session("2024-11-29 18:15:00Z") == date(2024, 11, 29)


def test_exact_warmup_count():
    end = date(2024, 1, 16)
    start = history_start(end, end, 1800)
    assert len(sessions(start, end)) >= 1800
    cfg = ScreenConfig(moving_averages=[MovingAverage("EMA", 300)],
                       rules=[Rule(ma="EMA300", method="accel_slope", lookback=100)])
    assert cfg.required_history() >= 1700


def test_cache_reuses_history_and_extends_only_missing(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    first = cache.get_many(["AAA", "BBB"], date(2024, 1, 2), date(2024, 1, 31), refresh_recent=False)
    assert len(fake_provider.calls) == 1
    assert first.metadata["AAA"]["last_success"]
    cache.get_many(["AAA", "BBB"], date(2024, 1, 2), date(2024, 1, 31), refresh_recent=False)
    assert len(fake_provider.calls) == 1
    cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 2, 5), refresh_recent=False)
    assert len(fake_provider.calls) == 2
    assert fake_provider.calls[-1][1] > date(2024, 1, 2)
    # Earlier data needs only an extension, with an overlap for adjustment checks.
    cache.get_many(["AAA"], date(2023, 12, 1), date(2024, 2, 5), refresh_recent=False)
    assert fake_provider.calls[-1][2] < date(2024, 2, 5)


def test_cache_refresh_policy_and_cache_only(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 1, 31))
    cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 1, 31))
    assert len(fake_provider.calls) == 1
    _, meta_path = cache._paths("AAA")
    meta = json.loads(meta_path.read_text())
    meta["last_success"] = "2020-01-01T00:00:00+00:00"
    meta_path.write_text(json.dumps(meta))
    cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 1, 31))
    assert len(fake_provider.calls) == 1  # Cache age alone no longer triggers a default refresh.
    cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 1, 31), refresh_recent=True)
    assert len(fake_provider.calls) == 2
    cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 1, 31), force=True, cache_only=True)
    assert len(fake_provider.calls) == 2


def test_cache_first_survives_restart_and_explicit_updates_bypass_recent_timestamp(tmp_path, fake_provider):
    start, end = date(2023, 1, 3), date(2024, 1, 31)
    cache = PriceCache(tmp_path, fake_provider)
    original = cache.get_many(["AAA"], start, end)
    assert len(original.downloads) == 1
    first_stamp = original.metadata["AAA"]["last_success"]
    saved = PriceCache(tmp_path, fake_provider).get_many(["AAA"], start, end)
    assert len(fake_provider.calls) == 1 and saved.downloads == []
    assert saved.metadata["AAA"]["last_success"] == first_stamp
    for _ in range(2):
        updated = cache.get_many(["AAA"], start, end, refresh_now=True)
        assert len(updated.downloads) == 1
        assert updated.downloads[0]["reason"] == "Explicit price update"
        assert fake_provider.calls[-1][1] == date(2024, 1, 10)  # Exactly the recent 21 calendar days.
        assert fake_provider.calls[-1][2] == end
    assert len(fake_provider.calls) == 3
    cache.get_many(["AAA"], start, end, refresh_now=True, retry_missing=True, cache_only=True)
    assert len(fake_provider.calls) == 3  # Cache-only still wins at the provider boundary.
    assert len(cache.get_many(["AAA"], start, end).frames["AAA"]) == len(original.frames["AAA"])


def test_explicit_full_update_redownloads_cached_span_once(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    cache.get_many(["AAA"], date(2023, 1, 3), date(2024, 1, 31))
    fake_provider.factor = .9  # Revised adjusted prices must not cause a duplicate full-span request.
    updated = cache.get_many(["AAA"], date(2023, 6, 1), date(2024, 1, 31), force=True)
    assert fake_provider.calls[-1][1:] == (date(2023, 1, 3), date(2024, 1, 31))
    assert updated.downloads[0]["reason"] == "Full history refresh"
    cache.get_many(["AAA"], date(2023, 6, 1), date(2024, 1, 31))
    assert len(fake_provider.calls) == 2


def test_retry_gaps_does_not_redownload_complete_tickers(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    cache.get_many(["AAA", "BBB"], date(2024, 1, 2), date(2024, 1, 31))
    frame, meta = cache._read("AAA")
    frame.loc[pd.Timestamp("2024-01-16"), :] = np.nan
    cache._write("AAA", frame, meta)
    result = cache.get_many(["AAA", "BBB"], date(2024, 1, 2), date(2024, 1, 31),
                            refresh_recent=False, retry_missing=True)
    assert fake_provider.calls[-1][0] == ["AAA"]
    assert pd.notna(result.frames["AAA"].loc["2024-01-16", "adj_close"])


def test_corporate_action_revision_refreshes_all_cached_history(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    original = cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 1, 31), refresh_recent=False)
    old_price = original.frames["AAA"].adj_close.iloc[0]
    fake_provider.factor = .8
    revised = cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 2, 5), refresh_recent=False)
    assert len(fake_provider.calls) == 3
    assert fake_provider.calls[-1][1:] == (date(2024, 1, 2), date(2024, 2, 5))
    assert revised.frames["AAA"].adj_close.iloc[0] == pytest.approx(.8 * old_price)
    assert revised.warnings


def test_network_failure_retains_cache_and_reports_missing_latest(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    first = cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 1, 31), refresh_recent=False)
    fake_provider.fail = True
    second = cache.get_many(["AAA"], date(2024, 1, 2), date(2024, 2, 5), refresh_recent=False)
    assert second.errors["AAA"]
    assert second.metadata["AAA"]["last_success"] == first.metadata["AAA"]["last_success"]
    assert pd.isna(second.frames["AAA"].adj_close.iloc[-1])
    pd.testing.assert_series_equal(first.frames["AAA"].adj_close,
                                    second.frames["AAA"].loc[:"2024-01-31", "adj_close"])


def test_completely_unavailable_cached_ticker_does_not_interrupt_screen(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    fake_provider.fail = True
    batch = cache.get_many(["MISSING"], date(2024, 1, 2), date(2024, 1, 31), refresh_recent=False)
    # An empty cache schema reindexed onto sessions has object-typed NaNs.
    assert batch.frames["MISSING"].adj_close.isna().all()
    from trend_screener.universe import custom_universe
    run = screen(custom_universe(["MISSING"]), batch.frames, builtins()[0], date(2024, 1, 31))
    assert run.summary()["insufficient"] == 1
    assert run.summary()["passing"] == 0


def test_network_circuit_breaker_finishes_large_failed_universe(tmp_path, fake_provider):
    fake_provider.fail = True
    tickers = [f"T{i}" for i in range(120)]
    batch = PriceCache(tmp_path, fake_provider).get_many(
        tickers, date(2024, 1, 2), date(2024, 1, 31), refresh_recent=False)
    assert len(fake_provider.calls) == 2
    assert len(batch.errors) == len(batch.frames) == 120
    from trend_screener.universe import custom_universe
    run = screen(custom_universe(tickers), batch.frames, builtins()[0], date(2024, 1, 31))
    assert run.summary()["insufficient"] == 120 and run.passing.empty


def test_normalizer_requires_adj_close_and_handles_auto_adjust_explicitly():
    raw = pd.DataFrame({"Open": [100], "High": [101], "Low": [99], "Close": [100],
                        "Volume": [10]}, index=pd.to_datetime(["2024-01-02"]))
    with pytest.raises(ValueError, match="separate Adj Close"):
        normalize_bars(raw)
    adjusted = normalize_bars(raw, auto_adjusted=True)
    assert adjusted.adj_close.iloc[0] == 100
    assert adjusted[["open", "high", "low", "close"]].isna().all().all()
    raw["Adj Close"] = 90
    separate = normalize_bars(raw)
    assert separate.close.iloc[0] == 100 and separate.adj_close.iloc[0] == 90


def test_duplicate_and_bad_ohlc_rejected_or_marked_missing():
    raw = pd.DataFrame({"Open": [100], "High": [90], "Low": [95], "Close": [100],
                        "Adj Close": [100], "Volume": [10]}, index=pd.to_datetime(["2024-01-02"]))
    assert normalize_bars(raw).isna().all().all()
    with pytest.raises(ValueError, match="duplicate"):
        normalize_bars(pd.concat([raw, raw]))


def test_ticker_format_and_universe_schema():
    assert provider_symbol("brk.b") == "BRK-B"
    assert parse_tickers("aapl, MSFT brk.b; AAPL") == ["AAPL", "MSFT", "BRK-B"]
    for invalid in ["../../file", "AAPL;rm", "", "A B"]:
        with pytest.raises(ValueError):
            provider_symbol(invalid)
    raw = pd.DataFrame({"Symbol": [f"T{i}" for i in range(503)], "Security": "Company",
                        "GICS Sector": "Technology", "GICS Sub-Industry": "Software"})
    assert len(normalize_constituents(raw)) == 503
    with pytest.raises(ValueError):
        normalize_constituents(raw.iloc[:3])


def test_explicit_ticker_aliases_preserve_display_identity(fake_provider):
    provider = AliasedProvider(fake_provider, {"FB": "META"})
    batch = provider.download(["FB", "META", "AAPL"], date(2024, 1, 2), date(2024, 1, 31))
    assert fake_provider.calls[-1][0] == ["META", "AAPL"]
    assert set(batch.frames) == {"FB", "META", "AAPL"}
    pd.testing.assert_frame_equal(batch.frames["FB"], batch.frames["META"])
    assert provider.name != fake_provider.name  # Distinct cache scope after changing symbol routing.


def test_all_builtin_presets_and_json_roundtrip(tmp_path):
    store = PresetStore(tmp_path)
    for cfg in builtins():
        cfg.validate()
        assert ScreenConfig.from_json(cfg.to_json()).to_dict() == cfg.to_dict()
        store.save(cfg)
    assert len(store.list()) == 5
    old = builtins()[0].name
    store.rename(old, "Renamed")
    assert old not in store.list() and "Renamed" in store.list()
    store.delete("Renamed")
    assert len(store.list()) == 4


@pytest.mark.parametrize("ma", [MovingAverage(period=0), MovingAverage(period=-3),
                               MovingAverage(period=2.5), MovingAverage(period=True), MovingAverage("BAD", 5)])
def test_ma_validation(ma):
    with pytest.raises(ValueError):
        ma.validate()


def test_config_validation_cycles_refs_and_no_rules():
    cfg = builtins()[0]
    cfg.groups.extend([Group("a", "A", parent="b"), Group("b", "B", parent="a")])
    with pytest.raises(ValueError, match="cycle"):
        cfg.validate()
    cfg = builtins()[0]
    cfg.rules[0].ma = "SMA37"
    with pytest.raises(ValueError, match="enabled"):
        cfg.validate()
    cfg = builtins()[0]
    for r in cfg.rules:
        r.enabled = False
    with pytest.raises(ValueError, match="at least"):
        cfg.validate()
    with pytest.raises(ValueError):
        ScreenConfig.from_json('{"schema_version": 999}')
    with pytest.raises(ValueError):
        ScreenConfig.from_json('{"data_settings":{"requested_date":"bad"}}')


def test_history_and_excel_exports_are_readable_and_causal():
    end = date(2024, 1, 16)
    universe = demo_universe(3)
    data = DemoProvider().download(universe.ticker.tolist(), date(2023, 1, 1), end)
    run = screen(universe, data.frames, builtins()[0], end)
    with ZipFile(BytesIO(history_zip(run))) as archive:
        assert "configuration.json" in archive.namelist()
        frame = pd.read_csv(archive.open("DEMO001.csv"))
        assert frame["date"].max() == str(end)
        assert {"adj_close", "close", "SMA5", "SMA20", "SMA50"} <= set(frame)
    excel = pd.read_excel(BytesIO(excel_bytes(run.table)))
    assert excel.ticker.tolist() == universe.ticker.tolist()


def test_forward_returns_separate_and_exact(make_bars):
    frame = make_bars(np.arange(100, 180))
    start = frame.index[0].date()
    result = forward_returns({"TEST": frame}, start, frame.index[-1].date())
    assert result.forward_5d_return_pct.iloc[0] == pytest.approx(5)
    assert result.forward_20d_return_pct.iloc[0] == pytest.approx(20)
    assert result.forward_60d_return_pct.iloc[0] == pytest.approx(60)
    unavailable = forward_returns({"TEST": frame.iloc[:10]}, start, frame.index[-1].date())
    assert pd.isna(unavailable.forward_20d_return_pct.iloc[0])
