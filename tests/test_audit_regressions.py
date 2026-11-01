from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from trend_screener.cache import CachedBatch, PriceCache
from trend_screener.engine import screen
from trend_screener.presets import builtins
from trend_screener.rules import compare
from trend_screener.studies import StudyEngine
from trend_screener.universe import custom_universe
from trend_screener.models import MovingAverage, Rule, ScreenConfig


@pytest.mark.parametrize("revision", [False, True])
def test_incomplete_full_refresh_never_erases_saved_history(tmp_path, fake_provider, monkeypatch, revision):
    cache = PriceCache(tmp_path, fake_provider)
    first, last = date(2023, 1, 3), date(2024, 1, 31)
    original = cache.get_many(["AAA"], first, last)
    bars, metadata = cache._read("AAA")
    download = fake_provider.download
    def partial(tickers, start, end):
        batch = download(tickers, start, end)
        batch.frames = {t: f.iloc[-5:] for t, f in batch.frames.items()}
        return batch
    monkeypatch.setattr(fake_provider, "download", partial)
    if revision:
        fake_provider.factor = .8
    updated = cache.get_many(["AAA"], first, last, force=not revision, refresh_now=revision)
    pd.testing.assert_frame_equal(cache._read("AAA")[0], bars)
    assert cache._read("AAA")[1]["last_success"] == metadata["last_success"]
    pd.testing.assert_frame_equal(updated.frames["AAA"], original.frames["AAA"])
    assert "AAA" in updated.errors and "incomplete" in updated.errors["AAA"].lower()
    exported = updated.annotate_results(pd.DataFrame({"ticker": ["AAA"]}))
    assert "incomplete" in exported.price_data_issue.iloc[0].lower()
    assert exported.last_price_download_utc.iloc[0] == metadata["last_success"]


def test_partial_update_never_splices_fields_from_different_rows(tmp_path, fake_provider, monkeypatch):
    cache = PriceCache(tmp_path, fake_provider)
    start, end = date(2024, 1, 2), date(2024, 1, 31)
    original = cache.get_many(["AAA"], start, end).frames["AAA"]
    download = fake_provider.download
    def partial(tickers, first, last):
        batch = download(tickers, first, last)
        for frame in batch.frames.values():
            frame["adj_close"] = np.nan
            frame.loc[frame.index[-1], "adj_close"] = original.adj_close.iloc[-1]
            frame["open"] *= .95
        return batch
    monkeypatch.setattr(fake_provider, "download", partial)
    updated = cache.get_many(["AAA"], start, end, refresh_now=True)
    assert updated.frames["AAA"].loc[original.index[-2], "open"] == original.open.iloc[-2]


def test_bad_metadata_recovery_cannot_shrink_history_to_the_requested_subset(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    start, end = date(2023, 1, 3), date(2024, 1, 31)
    cache.get_many(["AAA"], start, end)
    _, meta_path = cache._paths("AAA")
    meta_path.write_text("broken JSON")
    cache.get_many(["AAA"], date(2024, 1, 2), end)
    assert fake_provider.calls[-1][1:] == (start, end)
    assert cache._read("AAA")[0].index[0].date() == start


def test_missing_overlap_requires_full_vintage_check(tmp_path, fake_provider, monkeypatch):
    cache = PriceCache(tmp_path, fake_provider)
    first, last = date(2024, 1, 2), date(2024, 1, 31)
    cache.get_many(["AAA"], first, last)
    fake_provider.factor = .8
    original = fake_provider.download
    def no_overlap(tickers, start, end):
        batch = original(tickers, start, end)
        if start != first:
            batch.frames = {t: f.loc[f.index > pd.Timestamp(last)] for t, f in batch.frames.items()}
        return batch
    monkeypatch.setattr(fake_provider, "download", no_overlap)
    cache.get_many(["AAA"], first, date(2024, 2, 5))
    saved = cache._read("AAA")[0]
    np.testing.assert_allclose(saved.adj_close / saved.close, .8)
    assert fake_provider.calls[-1][1:] == (first, date(2024, 2, 5))


@pytest.mark.parametrize("bad", [{"coverage_end": "not-a-date"}, {"last_success": "missing-timezone"},
                                {"coverage_start": None}, {"last_success": "2024-01-01T00:00:00"}])
def test_damaged_cache_metadata_is_recovered_without_stopping_other_tickers(tmp_path, fake_provider, bad):
    cache = PriceCache(tmp_path, fake_provider)
    start, end = date(2024, 1, 2), date(2024, 1, 31)
    cache.get_many(["AAA", "BBB"], start, end)
    _, path = cache._paths("AAA")
    meta = json.loads(path.read_text())
    meta.update(bad)
    path.write_text(json.dumps(meta))
    recovered = cache.get_many(["AAA", "BBB"], start, end)
    assert recovered.frames["AAA"].adj_close.notna().all()
    assert recovered.frames["BBB"].adj_close.notna().all()
    assert fake_provider.calls[-1][0] == ["AAA"]


def test_threshold_operators_agree_at_rounded_boundary_and_preserve_zero_direction():
    value = 100 * (102 / 100 - 1)
    assert compare(value, "==", 2)
    assert compare(value, ">=", 2) and compare(value, "<=", 2)
    assert not compare(value, ">", 2) and not compare(value, "<", 2)
    assert not compare(value, "!=", 2)
    assert compare(1e-12, ">", 0) and not compare(1e-12, "==", 0)
    assert compare(-1e-12, "<", 0) and not compare(-1e-12, "==", 0)


def test_benchmark_update_issues_are_exported_even_when_stock_update_succeeds():
    batch = CachedBatch(errors={"SPY": "Incomplete benchmark refresh; retained cache"},
                        metadata={"AAA": {"last_success": "2026-11-01T00:00:00+00:00"},
                                  "SPY": {"last_success": "2026-10-30T00:00:00+00:00"}})
    table = batch.annotate_results(pd.DataFrame({"ticker": ["AAA"]}), "SPY")
    assert table.price_data_issue.iloc[0] == ""
    assert "benchmark refresh" in table.benchmark_data_issue.iloc[0]
    assert table.benchmark_last_download_utc.iloc[0] < table.last_price_download_utc.iloc[0]


def test_relationship_first_preset_ranks_by_actual_trend_rule(make_bars):
    frame = make_bars(np.linspace(50, 150, 400))
    cfg = builtins()[1]
    cfg.risk.enabled = False
    end = frame.index[-1].date()
    run = screen(custom_universe(["AAA"]), {"AAA": frame}, cfg, end)
    slope = run.table["slope_20.normalized_slope"].iloc[0]
    assert run.table.rank_normalized_slope.iloc[0] == pytest.approx(slope)
    study = StudyEngine({"AAA": frame}, custom_universe(["AAA"]), cfg, frame.index[-20].date(), end)
    assert study.signals(frame.index[-1]).rank_normalized_slope.iloc[0] == pytest.approx(slope)


def test_failed_update_clears_progress_and_preserves_applied_screen(tmp_path, monkeypatch):
    from trend_screener.demo import DemoProvider
    monkeypatch.setenv("SCREENER_HOME", str(tmp_path))
    cfg = builtins()[0]
    cfg.data_settings = {"source": "Synthetic demo (offline)", "time_mode": "Historical date",
                         "requested_date": "2024-01-16"}
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    app.session_state["draft"], app.session_state["editor_version"] = cfg, 0
    app.run().button(key="run_screen").click().run()
    applied = app.session_state["run"]
    def failed(*args, **kwargs):
        raise RuntimeError("Simulated provider outage")
    monkeypatch.setattr(DemoProvider, "download", failed)
    app.button(key="update_prices").click().run()
    assert not app.exception and app.error
    assert app.session_state["run"] is applied
    assert not app.get("progress")
    app.button(key="study_load").click().run()
    assert not app.exception and app.error
    assert app.session_state["run"] is applied
    assert not app.get("progress")


def test_incomplete_update_warns_and_exports_retained_data_issue(tmp_path, monkeypatch):
    from trend_screener.demo import DemoProvider
    monkeypatch.setenv("SCREENER_HOME", str(tmp_path))
    cfg = builtins()[0]
    cfg.data_settings = {"source": "Synthetic demo (offline)", "time_mode": "Historical date",
                         "requested_date": "2024-01-16"}
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    app.session_state["draft"], app.session_state["editor_version"] = cfg, 0
    app.run().button(key="run_screen").click().run()
    old = app.session_state["run"].table.copy()
    original = DemoProvider.download
    def partial(provider, tickers, start, end):
        batch = original(provider, tickers, start, end)
        batch.frames = {t: f.iloc[-2:] for t, f in batch.frames.items()}
        return batch
    monkeypatch.setattr(DemoProvider, "download", partial)
    app.selectbox(key="v0_price_update_scope").select("Full price history").run()
    app.button(key="update_prices").click().run()
    assert not app.exception and not app.error
    assert any("Price-data issues" in warning.value for warning in app.warning)
    updated = app.session_state["run"].table
    assert updated.price_data_issue.str.contains("Incomplete").all()
    pd.testing.assert_series_equal(old.latest_adjusted_price, updated.latest_adjusted_price)
    pd.testing.assert_series_equal(old.last_price_download_utc, updated.last_price_download_utc)


@pytest.mark.parametrize("kind", ["SMA", "EMA"])
def test_future_price_mutation_does_not_change_screen_risk_or_historical_signals(make_bars, kind):
    rng = np.random.default_rng(4927)
    frame = make_bars(100 * np.exp(np.cumsum(rng.normal(.001, .02, 350))))
    bm = make_bars(100 * np.exp(np.cumsum(rng.normal(.0005, .01, 350))))
    cfg = ScreenConfig(moving_averages=[MovingAverage(kind, 37)],
                       rules=[Rule(ma=f"{kind}37", lookback=20)])
    cut = frame.index[300]
    prices = {"AAA": frame, "SPY": bm}
    changed = {t: f.copy() for t, f in prices.items()}
    for f in changed.values():
        f.loc[f.index > cut, ["open", "high", "low", "close", "adj_close"]] *= 1000
    universe = custom_universe(["AAA"])
    before = screen(universe, prices, cfg, cut.date())
    after = screen(universe, changed, cfg, cut.date())
    pd.testing.assert_frame_equal(before.table, after.table)
    e1 = StudyEngine(prices, universe, cfg, frame.index[280].date(), frame.index[-1].date())
    e2 = StudyEngine(changed, universe, cfg, frame.index[280].date(), frame.index[-1].date())
    pd.testing.assert_frame_equal(e1.signals(cut), e2.signals(cut))
