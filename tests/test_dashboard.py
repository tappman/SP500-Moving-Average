"""Offline interaction tests using Streamlit's actual script and widget runtime."""
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from trend_screener.demo import DemoProvider
from trend_screener.presets import builtins


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SCREENER_HOME", str(tmp_path))
    config = builtins()[0]
    config.data_settings = {
        "source": "Synthetic demo (offline)", "time_mode": "Historical date",
        "requested_date": "2024-01-16", "period": "1 year",
    }
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    at.session_state["draft"] = config
    at.session_state["editor_version"] = 0
    at.run()
    assert not at.exception
    return at


def click_label(app, label):
    next(b for b in app.button if b.label == label).click().run()
    assert not app.exception


def test_dashboard_run_filter_changes_and_no_repeated_downloads(app, monkeypatch):
    calls = []
    original = DemoProvider.download
    def download(provider, tickers, start, end):
        calls.append((tickers, start, end))
        return original(provider, tickers, start, end)
    monkeypatch.setattr(DemoProvider, "download", download)
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run"].summary()["requested"] == 24
    first = app.session_state["run"]
    app.number_input(key="v0_rule_slope_20_threshold").set_value(1000000.0).run()
    assert app.session_state["run"] is first  # Apply button is meaningful.
    assert any("Draft settings have changed" in w.value for w in app.warning)
    app.button(key="run_screen").click().run()
    assert not app.exception
    assert app.session_state["run"].passing.empty
    assert len(calls) == 1


def test_duplicate_disable_remove_and_relationship(app):
    app.button(key="v0_rule_slope_20_duplicate").click().run()
    assert len(app.session_state["draft"].rules) == 4
    new = app.session_state["draft"].rules[-1]
    app.checkbox(key=f"v0_rule_{new.id}_enabled").uncheck().run()
    assert not new.enabled
    app.button(key=f"v0_rule_{new.id}_remove").click().run()
    assert len(app.session_state["draft"].rules) == 3
    app.button(key="v0_add_relationship").click().run()
    assert not app.exception
    relationship = app.session_state["draft"].rules[-1]
    assert relationship.ma == "PRICE" and relationship.method == "relative"
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error


@pytest.mark.parametrize("method", ["strict", "positive_pct", "accel_pct", "accel_slope", "turn_up",
                                    "max_drawdown_pct", "r2", "pct_change", "negative_count"])
def test_method_controls_run(app, method):
    app.selectbox(key="v0_rule_slope_20_method").select(method).run()
    assert not app.exception
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run"].config.rules[1].method == method


def test_preset_load_after_existing_run_invalidates_data_state_safely(app):
    app.button(key="run_screen").click().run()
    app.selectbox(key="preset_choice").select("Example · Strong Bullish Alignment").run()
    app.button(key="load_preset").click().run()
    assert not app.exception
    assert len(app.session_state["draft"].moving_averages) == 4
    assert len(app.session_state["draft"].rules) == 6
    # Preserve offline operation when loading an example that has default live settings.
    app.selectbox(key="v1_source").select("Synthetic demo (offline)").run()
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error


def test_nested_group_controls(app):
    next(t for t in app.text_input if t.label == "New group name").set_value("Either long trend")
    next(s for s in app.selectbox if s.label == "New group logic").select("OR")
    click_label(app, "Add nested group")
    cfg = app.session_state["draft"]
    assert len(cfg.groups) == 2
    group = cfg.groups[-1]
    app.selectbox(key="v0_rule_slope_20_group").select(group.id).run()
    app.selectbox(key="v0_rule_slope_50_group").select(group.id).run()
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run"].config.groups[-1].logic == "OR"


def test_quick_bearish_alignment_is_one_and_group(app):
    app.selectbox(key="v0_alignment_direction").select("Bearish").run()
    app.button(key="v0_add_alignment").click().run()
    assert not app.exception
    cfg = app.session_state["draft"]
    group = cfg.groups[-1]
    assert group.logic == "AND" and group.name == "Bearish alignment"
    rules = [r for r in cfg.rules if r.group == group.id]
    assert len(rules) == 2 and all(r.operator == "<" for r in rules)
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error


def test_grid_pagination_and_download_preparation(app):
    for period in (5, 20, 50):
        app.number_input(key=f"v0_rule_slope_{period}_threshold").set_value(-100.0)
    app.button(key="run_screen").click().run()
    assert app.session_state["run"].summary()["passing"] == 24
    app.selectbox(key="grid_size").select(20).run()
    app.toggle(key="grid_render").set_value(True).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 21  # One explorer, twenty grid charts.
    app.number_input(key="grid_page_2_20").set_value(2).run()
    assert len(app.get("plotly_chart")) == 5
    click_label(app, "Prepare Excel download")
    assert app.session_state["excel_download"].startswith(b"PK")
    click_label(app, "Prepare historical prices and MA archive")
    assert app.session_state["history_download"].startswith(b"PK")


def test_historical_and_separate_forward_outcomes(app):
    app.button(key="run_screen").click().run()
    assert app.session_state["run"].screen_date == date(2024, 1, 16)
    app.checkbox(key="enable_research").check().run()
    click_label(app, "Calculate 5 / 20 / 60-session forward returns")
    assert not app.error
    assert len(app.session_state["forward_table"]) > 0
    assert all(frame.index.max().date() == date(2024, 1, 16)
               for frame in app.session_state["run"].frames.values())
    assert not any("forward_" in c for c in app.session_state["run"].table.columns)


def test_custom_tickers_and_benchmark(app):
    app.selectbox(key="v0_universe").select("Custom tickers").run()
    app.text_area(key="v0_tickers").set_value("BRK.B, MSFT, AAPL").run()
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run"].table.ticker.tolist() == ["BRK-B", "MSFT", "AAPL"]
    app.selectbox(key="v0_universe").select("S&P 500 index").run()
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run"].table.ticker.tolist() == ["^DEMO500"]
