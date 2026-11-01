import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from trend_screener.builder import rename_references, sync_averages
from trend_screener.collections import StockGroups, apply_selection_edits
from trend_screener.models import Rule, ScreenConfig
from trend_screener.presets import builtins


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SCREENER_HOME", str(tmp_path))
    config = builtins()[0]
    config.data_settings = {"source": "Synthetic demo (offline)", "time_mode": "Historical date",
                            "requested_date": "2024-01-16", "period": "1 year"}
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    at.session_state["draft"], at.session_state["editor_version"] = config, 0
    at.run()
    assert not at.exception
    return at


def edit_table(app, predicate, *, edited=None, added=None, deleted=None):
    """Send the same serialized editing state that Streamlit's table frontend emits."""
    table = next(item for item in app.dataframe if predicate(item.value))
    states = app._tree.get_widget_states()
    widget = next((w for w in states.widgets if w.id == table.proto.id), None)
    if widget is None:
        widget = states.widgets.add()
        widget.id = table.proto.id
    widget.string_value = json.dumps({"edited_rows": edited or {}, "added_rows": added or [],
                                     "deleted_rows": deleted or []})
    app._run(states)
    assert not app.exception


def ma_table(frame):
    return {"kind", "period", "enabled", "show"} <= set(frame.columns)


def test_dependent_rules_pause_resume_and_preserve_manual_disabling():
    cfg = builtins()[0]
    cfg.rules[1].enabled = False
    cfg.rules.append(Rule(id="relationship", ma="PRICE", other="SMA5", method="relative"))
    cfg.moving_averages[0].enabled = False
    sync_averages(cfg, cfg.moving_averages)
    assert cfg.rules[0].paused_by_ma and not cfg.rules[0].enabled
    assert cfg.rules[-1].paused_by_ma and not cfg.rules[-1].enabled
    assert not cfg.rules[1].paused_by_ma
    cfg.validate()
    cfg.moving_averages[0].enabled = True
    sync_averages(cfg, cfg.moving_averages)
    assert cfg.rules[0].enabled and cfg.rules[-1].enabled
    assert not cfg.rules[1].enabled
    assert not cfg.rules[0].paused_by_ma
    assert ScreenConfig.from_json(cfg.to_json()).to_dict() == cfg.to_dict()


def test_names_replace_complete_tokens_without_corrupting_other_periods():
    rule = Rule(name="MA5 above SMA50; my trend", ma="SMA5", other="SMA50")
    rename_references(rule, {"SMA5": "EMA2"})
    assert rule.ma == "EMA2" and rule.other == "SMA50"
    assert rule.name == "EMA2 above SMA50; my trend"


def test_disabling_ma_in_table_no_longer_blocks_screen_and_reenables_rule(app):
    edit_table(app, ma_table, edited={0: {"enabled": False}})
    cfg = app.session_state["draft"]
    assert not cfg.moving_averages[0].enabled
    assert cfg.rules[0].paused_by_ma and not cfg.rules[0].enabled
    assert app.checkbox(key="v0_rule_slope_5_enabled").disabled
    assert not any("choose an enabled moving average" in w.value for w in app.warning)
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run"].table.rules_total.eq(2).all()
    edit_table(app, ma_table, edited={0: {"enabled": True}})
    assert app.session_state["draft"].rules[0].enabled
    assert not app.checkbox(key="v0_rule_slope_5_enabled").disabled


def test_renaming_type_period_and_adding_row_updates_rules_and_widget_state(app):
    edit_table(app, ma_table, edited={0: {"kind": "EMA — Exponential moving average", "period": 2}},
               added=[{"kind": "SMA — Simple moving average", "period": 37, "enabled": True, "show": True}])
    cfg = app.session_state["draft"]
    assert cfg.rules[0].ma == "EMA2" and cfg.rules[0].name == "EMA2 slope positive"
    assert app.selectbox(key="v0_rule_slope_5_ma").value == "EMA2"
    assert app.text_input(key="v0_rule_slope_5_name").value == "EMA2 slope positive"
    assert any(r.ma == "SMA37" and r.enabled for r in cfg.rules)
    assert any("EMA2" in panel.label and "Exponential" in panel.label for panel in app.expander)
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run"].table.rules_total.eq(4).all()


def test_deletion_and_edit_in_same_event_preserves_row_identity(app):
    edit_table(app, ma_table, deleted=[0], edited={1: {"period": 21}},
               added=[{"kind": "EMA — Exponential moving average", "period": 7, "enabled": True, "show": True}])
    cfg = app.session_state["draft"]
    assert cfg.rules[0].ma == "SMA5" and cfg.rules[0].paused_by_ma
    assert cfg.rules[1].ma == "SMA21" and cfg.rules[1].name == "SMA21 slope positive"
    assert cfg.rules[2].ma == "SMA50"  # Deleting the first row must not shift rule ownership.
    assert any(r.ma == "EMA7" and r.enabled for r in cfg.rules)
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error


def test_rule_ma_dropdown_updates_its_name_and_builder_tab_order(app):
    edit_table(app, ma_table, added=[{"kind": "EMA — Exponential moving average", "period": 2,
                                    "enabled": True, "show": True}])
    app.selectbox(key="v0_rule_slope_5_ma").select("EMA2").run()
    assert not app.exception
    assert app.session_state["draft"].rules[0].name == "EMA2 slope positive"
    labels = [tab.label for tab in app.tabs]
    i = labels.index("Moving averages & trend rules")
    assert labels[i:i + 3] == ["Moving averages & trend rules", "Risk settings", "Relationships"]


def test_paused_condition_can_be_reassigned_to_an_enabled_ma(app):
    edit_table(app, ma_table, edited={0: {"enabled": False}})
    assert not app.selectbox(key="v0_rule_slope_5_ma").disabled
    app.selectbox(key="v0_rule_slope_5_ma").select("SMA20").run()
    assert not app.exception
    rule = app.session_state["draft"].rules[0]
    assert rule.enabled and not rule.paused_by_ma and rule.ma == "SMA20"
    assert rule.name == "SMA20 slope positive"
    app.button(key="run_screen").click().run()
    assert not app.exception and not app.error


def test_selection_edits_are_ticker_based_and_keep_stocks_outside_visible_subset():
    selected = apply_selection_edits(["HIDDEN", "AAA"], ["BBB", "AAA"], {0: {"Select": True}})
    assert selected == ["HIDDEN", "AAA", "BBB"]
    assert apply_selection_edits(selected, ["AAA"], {0: {"Select": False}}) == ["HIDDEN", "BBB"]


def test_named_groups_persist_separately_and_invalid_save_keeps_existing(tmp_path):
    store = StockGroups(tmp_path)
    store.change(selected=["BRK.B", "AAPL", "AAPL"], save_name="Group A")
    store.change(selected=["MSFT"], save_name="Group B")
    assert StockGroups(tmp_path).read()["groups"] == {"Group A": ["BRK-B", "AAPL"], "Group B": ["MSFT"]}
    with pytest.raises(ValueError):
        store.change(save_name=" ")
    assert "Group A" in store.read()["groups"]
    store.change(delete_name="Group A")
    assert store.read()["groups"] == {"Group B": ["MSFT"]}


def test_table_checks_accumulate_and_previews_groups_filters_do_not_clear_them(app, tmp_path):
    app.button(key="run_screen").click().run()
    tickers = app.session_state["run"].passing.ticker.tolist()
    assert len(tickers) >= 2
    edit_table(app, lambda f: "Select" in f.columns, edited={0: {"Select": True}})
    assert app.session_state["selected_tickers"] == tickers[:1]
    edit_table(app, lambda f: "Select" in f.columns, edited={0: {"Select": True}, 1: {"Select": True}})
    assert app.session_state["selected_tickers"] == tickers[:2]
    app.toggle(key="result_preview").set_value(True).run()
    app.selectbox(key="result_preview_1").select(tickers[-1]).run()
    assert app.session_state["selected_tickers"] == tickers[:2]
    app.radio(key="table_view_1").set_value("Trend details").run()
    selected = next(f.value for f in app.dataframe if "Select" in f.value.columns)
    assert selected.Select.sum() == 2
    app.text_input(key="stock_group_name").set_value("My trends").run()
    app.button(key="save_stock_group").click().run()
    app.button(key="clear_result_selection").click().run()
    assert app.session_state["selected_tickers"] == []
    app.button(key="load_stock_group").click().run()
    assert app.session_state["selected_tickers"] == tickers[:2]
    app.radio(key="grid_population").set_value("Selected stocks").run()
    app.toggle(key="grid_render").set_value(True).run()
    assert not app.exception and not app.error
    assert StockGroups(tmp_path / "collections").read()["selected"] == tickers[:2]
    app.button(key="screen_selection").click().run()
    assert app.session_state["draft"].data_settings["universe_mode"] == "Custom tickers"
    app.button(key="run_screen").click().run()
    assert app.session_state["run"].table.ticker.tolist() == tickers[:2]
    assert app.session_state["selected_tickers"] == tickers[:2]


def test_selected_stock_groups_reopen_without_running_or_downloading(tmp_path, monkeypatch):
    from trend_screener.providers import YFinanceProvider
    from trend_screener.demo import DemoProvider
    monkeypatch.setenv("SCREENER_HOME", str(tmp_path))
    StockGroups(tmp_path / "collections").change(selected=["AAPL", "MSFT"], save_name="Watchlist")
    def forbidden(*args, **kwargs):
        raise AssertionError("Opening saved selections must not download prices")
    monkeypatch.setattr(YFinanceProvider, "download", forbidden)
    monkeypatch.setattr(DemoProvider, "download", forbidden)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    assert not app.exception and not app.error
    assert app.session_state["selected_tickers"] == ["AAPL", "MSFT"]
    assert app.selectbox(key="stock_group_choice").value == "Watchlist"
