"""Cache-policy regressions through the actual dashboard's buttons and widget reruns."""
from datetime import date
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from trend_screener import dashboard
from trend_screener.cache import PriceCache
from trend_screener.presets import builtins


@pytest.fixture
def live_app(tmp_path, monkeypatch, fake_provider):
    monkeypatch.setenv("SCREENER_HOME", str(tmp_path))
    monkeypatch.setattr(dashboard, "YFinanceProvider", lambda: fake_provider)
    monkeypatch.setattr(dashboard, "latest_completed_session", lambda **kwargs: date(2024, 1, 16))
    config = builtins()[0]
    config.data_settings = {"source": "Live Yahoo Finance", "universe_mode": "Custom tickers",
                            "tickers": "AAA, BBB", "time_mode": "Latest completed session", "period": "1 year"}
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    app.session_state["draft"], app.session_state["editor_version"] = config, 0
    app.run()
    assert not app.exception and not app.error
    return app


def test_same_run_aged_cache_and_reopened_dashboard_never_refetch_existing_prices(live_app, fake_provider):
    app = live_app
    app.button(key="run_screen").click().run()
    assert not app.error and len(fake_provider.calls) == 1
    cache = PriceCache(Path(os.environ["SCREENER_HOME"]) / "prices", fake_provider)
    for ticker in ("AAA", "BBB", "SPY"):
        _, path = cache._paths(ticker)
        meta = json.loads(path.read_text())
        meta["last_success"] = "2020-01-01T00:00:00+00:00"
        path.write_text(json.dumps(meta))
    app.session_state["data_loaded_at"] = 0
    app.button(key="run_screen").click().run()
    assert len(fake_provider.calls) == 1
    assert app.session_state["run_price_activity"]["downloads"] == []
    assert any("No price downloads" in c.value for c in app.caption)
    # Force a disk-cache read; changing the cache-only setting must not mean refresh.
    app.checkbox(key="v0_cache_only").check().run()
    assert app.button(key="update_prices").disabled
    app.button(key="run_screen").click().run()
    app.checkbox(key="v0_cache_only").uncheck().run()
    app.button(key="run_screen").click().run()
    assert len(fake_provider.calls) == 1 and not app.exception and not app.error
    config = app.session_state["draft"]
    reopened = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    reopened.session_state["draft"], reopened.session_state["editor_version"] = config, 0
    reopened.run().button(key="run_screen").click().run()
    assert not reopened.exception and not reopened.error
    assert len(fake_provider.calls) == 1
    assert reopened.session_state["run_price_activity"]["source"] == "Local price cache"
    assert reopened.session_state["run_price_activity"]["downloads"] == []


@pytest.mark.parametrize("scope", ["Recent prices + missing dates", "Full price history"])
def test_update_button_downloads_explicitly_but_next_normal_run_does_not(live_app, fake_provider, scope):
    app = live_app
    app.button(key="run_screen").click().run()
    start, end = fake_provider.calls[0][1:]
    app.selectbox(key="v0_price_update_scope").select(scope).run()
    app.button(key="update_prices").click().run()
    assert not app.exception and not app.error
    assert len(fake_provider.calls) == 2
    expected_start = start if scope == "Full price history" else (pd.Timestamp(end) - pd.Timedelta(days=21)).date()
    assert fake_provider.calls[-1][1:] == (expected_start, end)
    assert app.session_state["run_price_activity"]["symbols_requested"] == 3
    assert app.session_state["run_settings"]["refresh_now"]
    # Updating is a one-click action even when Full price history remains selected.
    app.button(key="run_screen").click().run()
    assert len(fake_provider.calls) == 2
    assert app.session_state["run_price_activity"]["downloads"] == []
    assert not app.session_state["run_settings"]["force"]


def test_longer_requested_history_fetches_only_the_older_extension(live_app, fake_provider):
    app = live_app
    app.button(key="run_screen").click().run()
    first_start, first_end = fake_provider.calls[0][1:]
    app.selectbox(key="v0_period").select("2 years").run()
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert len(fake_provider.calls) == 2
    assert fake_provider.calls[-1][1] < first_start
    assert fake_provider.calls[-1][2] < first_end  # An overlap near the old start, not all saved history.


def test_full_ma_names_in_editor_and_rule_selection_preserve_saved_codes(live_app):
    app = live_app
    editor = next(frame for frame in app.dataframe if {"kind", "period", "enabled", "show"} <= set(frame.value.columns))
    assert editor.value.kind.str.contains("Simple moving average").all()
    assert "Exponential moving average" in editor.proto.columns
    options = app.selectbox(key="v0_rule_slope_20_ma").options
    assert any("Simple moving average" in label for label in options)
    assert all(ma.kind == "SMA" for ma in app.session_state["draft"].moving_averages)
    # Simulate a full-name row supplied by the data editor and verify canonical JSON/calculation keys.
    app.session_state["v0_ma_base"] = pd.DataFrame([
        {"kind": "EMA — Exponential moving average", "period": 20, "enabled": True, "show": True}])
    app.run()
    assert not app.exception
    assert app.session_state["draft"].moving_averages[0].kind == "EMA"
    assert app.session_state["draft"].moving_averages[0].key == "EMA20"


@pytest.mark.parametrize("method", ["relative", "cross_up", "cross_down", "separation_change"])
def test_relationship_settings_are_explained_and_latest_only_lookback_is_clear(live_app, method):
    app = live_app
    app.button(key="v0_add_relationship").click().run()
    rule = app.session_state["draft"].rules[-1]
    prefix = f"v0_rule_{rule.id}_"
    app.selectbox(key=prefix + "method").select(method).run()
    assert not app.exception and not app.error
    controls = [*app.number_input, *app.selectbox, *app.checkbox, *app.text_input, *app.button]
    assert all(w.proto.help for w in controls if w.key and w.key.startswith(prefix))
    lookback = app.number_input(key=prefix + "lookback")
    assert lookback.disabled == (method == "relative")
    if method == "relative":
        assert lookback.value == 1 and "Latest observation" in lookback.proto.help
