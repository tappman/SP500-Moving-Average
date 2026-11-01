"""Streamlit interface. Widget edits are drafts until the user presses Run Screen."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timedelta
import math
import os
from pathlib import Path
import sqlite3
import time

import pandas as pd
import streamlit as st

from .cache import PriceCache
from .calendar import history_start, latest_completed_session
from .charts import information_panel, price_chart
from .demo import DemoProvider, demo_universe
from .engine import ScreenRun, screen
from .exports import excel_bytes, history_zip
from .models import (
    BOOL_METHODS, METHODS, OPERATORS, REGRESSION_METHODS, RELATION_METHODS,
    Group, MovingAverage, Rule, ScreenConfig, uid,
)
from .history import HistoryStore
from .membership import MembershipHistory
from .presets import PresetStore, builtins
from .providers import AliasedProvider, YFinanceProvider
from .research import forward_returns
from .rules import window_description
from .rule_help import CONTROL_HELP, MA_TYPES, METHOD_HELP, OPERATOR_HELP, lookback_help, series_label
from .risk import RISK_METRICS, risk_column_label
from .risk_dashboard import performance_panel, risk_settings_panel
from .research_dashboard import history_panel, portfolio_panel, research_lab
from .universe import UniverseService, custom_universe, parse_tickers, provider_symbol
from .appearance import (
    apply_workspace_style, context_strip, empty_state, sidebar_brand, show_figure, workspace_header,
)

ROOT = Path(__file__).resolve().parents[1]
PERIODS = {"3 months": 3, "6 months": 6, "1 year": 12, "2 years": 24,
           "3 years": 36, "5 years": 60, "10 years": 120}
TABLE_LABELS = {
    "ticker": "Ticker", "company": "Company", "sector": "Sector", "industry": "Industry",
    "latest_adjusted_price": "Adjusted close", "daily_return_pct": "Daily return (%)",
    "return_5d_pct": "5-session return (%)", "return_20d_pct": "20-session return (%)",
    "rank_normalized_slope": "MA slope (% / session)", "rank_pct_change": "MA change (%)",
    "rank_r2": "Trend R²", "rank_longest_streak": "Rising streak",
    "rules_passed": "Rules passed", "rules_unavailable": "Unavailable rules", "status": "Screen result",
}


def table_column_label(name):
    parts = name.split("_", 2)
    if len(parts) == 3 and parts[0] == "risk" and parts[1].isdigit() and parts[2] in RISK_METRICS:
        short = {
            "sharpe": "Sharpe", "sharpe_daily": "Daily Sharpe", "sortino": "Sortino", "beta": "Beta",
            "alpha_ann_pct": "Alpha (%/yr)", "alpha_daily_pct": "Alpha (%/day)",
            "volatility_ann_pct": "Volatility (%/yr)", "max_drawdown_pct": "Max drawdown (%)",
            "cagr_pct": "CAGR (%)", "calmar": "Calmar", "information_ratio": "Information ratio",
            "correlation": "Correlation", "regression_r2": "Return R²",
        }.get(parts[2], RISK_METRICS[parts[2]])
        return f"{short} · {parts[1]}d"
    return TABLE_LABELS.get(name, risk_column_label(name))


def table_column_formats():
    numeric = {"latest_adjusted_price", "daily_return_pct", "return_5d_pct", "return_20d_pct",
               "rank_normalized_slope", "rank_pct_change", "rank_r2"}
    integer = {"rules_passed", "rules_unavailable", "rank_longest_streak"}
    return {
        name: st.column_config.NumberColumn(label, format="%.4f" if name == "rank_normalized_slope" else "%.2f")
        if name in numeric else st.column_config.NumberColumn(label, format="%d")
        if name in integer else st.column_config.TextColumn(label, width="medium" if name == "company" else None)
        for name, label in TABLE_LABELS.items()
    }


def home() -> Path:
    return Path(os.environ.get("SCREENER_HOME", ROOT / ".screener"))


def load_config(config: ScreenConfig) -> None:
    st.session_state.draft = ScreenConfig.from_dict(config.to_dict())
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
    for name in ("raw_batch", "data_key", "data_loaded_at", "indicator_cache", "risk_cache"):
        st.session_state.pop(name, None)


def key(name):
    return f"v{st.session_state.editor_version}_{name}"


def default_option(options, value):
    return options.index(value) if value in options else 0


def settings_panel(config: ScreenConfig) -> dict:
    saved = config.data_settings
    today = pd.Timestamp.now(tz="America/New_York").date()
    with st.sidebar:
        sidebar_brand()
        st.markdown("### Data settings")
        source = st.selectbox("Data source", ["Live Yahoo Finance", "Synthetic demo (offline)"],
                              index=default_option(["Live Yahoo Finance", "Synthetic demo (offline)"],
                                                   saved.get("source", "Live Yahoo Finance")),
                              key=key("source"))
        modes = ["S&P 500 (current constituents)", "Sector", "Custom tickers", "Single stock", "S&P 500 index",
                 "Historical membership CSV"]
        mode = st.selectbox("Stock universe", modes, index=default_option(modes, saved.get("universe_mode")),
                            key=key("universe"))
        demo = source.startswith("Synthetic")
        if demo:
            st.info("SYNTHETIC DATA · 24 fictional stocks. These are not market quotes.")
            if mode in {"Custom tickers", "Single stock", "S&P 500 index"}:
                st.caption("The chosen ticker names also receive synthetic prices in demo mode.")
        elif mode in {"S&P 500 (current constituents)", "Sector"}:
            st.caption("Current membership is refreshed at most daily. Past screens have survivorship bias.")
        membership = None
        if mode == "Historical membership CSV":
            try:
                membership = MembershipHistory.load(home() / "research")
                if membership:
                    st.caption(f"Membership: {membership.source} · declared coverage "
                               f"{membership.coverage_start} to {membership.coverage_end}.")
                else:
                    st.info("Upload intervals in Historical research → Membership data first.")
            except (ValueError, KeyError, OSError) as exc:
                st.warning(f"Cannot read historical membership: {exc}")
        tickers = saved.get("tickers", "AAPL, MSFT, NVDA")
        if mode == "Custom tickers":
            tickers = st.text_area("Tickers (commas or spaces)", value=tickers, key=key("tickers"))
        elif mode == "Single stock":
            tickers = st.text_input("Ticker", value=saved.get("single_ticker", "AAPL"), key=key("single"))
        sector = saved.get("sector", "")
        if mode == "Sector":
            if demo:
                sector_options = sorted(demo_universe().sector.unique())
            else:
                if st.button("Load / refresh sectors", key=key("load_sectors")):
                    try:
                        with st.spinner("Retrieving current constituents…"):
                            st.session_state.universe_snapshot = UniverseService(home() / "universe").get(force=True)
                    except (RuntimeError, OSError) as exc:
                        st.error(str(exc))
                snapshot = st.session_state.get("universe_snapshot")
                sector_options = sorted(snapshot.frame.sector.unique()) if snapshot else []
            if sector_options:
                sector = st.selectbox("Sector", sector_options,
                                      index=default_option(sector_options, sector), key=key("sector"))
            else:
                st.caption("Load the current list above before choosing a sector.")
                sector = ""
        time_modes = ["Latest completed session", "Historical date"]
        time_mode = st.radio("Screening date", time_modes,
                             index=default_option(time_modes, saved.get("time_mode")), key=key("date_mode"))
        requested = None
        if time_mode == "Historical date":
            requested = st.date_input("Historical screening date",
                                      value=min(date.fromisoformat(saved.get("requested_date", str(today))), today),
                                      min_value=date(1970, 1, 1), max_value=today, key=key("screen_date"))
        end = latest_completed_session(requested=requested)
        ranges = [*PERIODS, "Custom dates"]
        period = st.selectbox("Displayed history", ranges,
                              index=default_option(ranges, saved.get("period", "1 year")), key=key("period"))
        if period == "Custom dates":
            custom = st.date_input(
                "Custom start and end",
                value=(date.fromisoformat(saved.get("custom_start", str(end - timedelta(days=365)))),
                       min(date.fromisoformat(saved.get("custom_end", str(end))), today)),
                min_value=date(1970, 1, 1), max_value=today, key=key("custom_range"),
            )
            if len(custom) != 2:
                st.warning("Choose both range endpoints before screening.")
                display_start = end
            else:
                display_start = custom[0]
                end = latest_completed_session(requested=custom[1])
        else:
            display_start = (pd.Timestamp(end) - pd.DateOffset(months=PERIODS[period])).date()
        st.caption(f"Effective completed session: **{end}** (NYSE, 15-minute publication buffer).")
        config.price_source = st.selectbox(
            "Price input for MAs and relationships", ["adj_close", "close"],
            index=default_option(["adj_close", "close"], config.price_source),
            format_func=lambda v: "Adjusted close (default)" if v == "adj_close" else "Unadjusted close",
            key=key("price_source"),
        )
        config.return_kind = st.selectbox("Return calculation", ["simple", "log"],
                                          index=default_option(["simple", "log"], config.return_kind),
                                          key=key("return_kind"))
        st.caption("Returns always use adjusted close. Percentage controls use 1 = 1%, not 0.01.")
        st.markdown("### Price updates")
        cache_only = st.checkbox("Saved prices only (no downloads)", value=saved.get("cache_only", False),
                                 key=key("cache_only"),
                                 help="Unticked still checks saved prices first and downloads only missing ranges. "
                                      "Ticked prevents all price-provider calls, including for missing histories.")
        st.caption("Run Screen uses saved prices first. Leaving this unticked only allows missing history "
                   "to download; it does not refresh existing bars. Use Update prices & run to refresh them.")
        with st.expander("Price update options"):
            scopes = ["Recent prices + missing dates", "Full price history"]
            update_scope = st.selectbox("Update scope", scopes,
                                         index=default_option(scopes, saved.get("price_update_scope", scopes[0])),
                                         key=key("price_update_scope"),
                                         help="Used only by Update prices & run. Recent updates recheck the last "
                                              "21 calendar days and repair saved gaps. Full history redownloads "
                                              "the entire cached span. Run Screen ignores this update scope.")
            st.caption("Updates keep existing history and check overlapping bars for corrections. A detected "
                       "price-adjustment revision triggers a full refresh to keep the series consistent.")
        aliases = saved.get("ticker_aliases", {})
        with st.expander("Ticker aliases / symbol changes"):
            st.caption("Route a displayed ticker to a different Yahoo symbol, for example FB → META. "
                       "This uses the destination's history; histories are not automatically spliced.")
            alias_base = key("alias_base")
            if alias_base not in st.session_state:
                st.session_state[alias_base] = pd.DataFrame(
                    [{"ticker": a, "provider_ticker": b} for a, b in aliases.items()],
                    columns=["ticker", "provider_ticker"], dtype=str)
            alias_rows = st.data_editor(st.session_state[alias_base], hide_index=True, num_rows="dynamic",
                                         key=key("alias_editor"), column_config={
                                             "ticker": st.column_config.TextColumn("Displayed ticker", required=True),
                                             "provider_ticker": st.column_config.TextColumn("Provider ticker", required=True),
                                         })
            try:
                aliases = {}
                for row in alias_rows.to_dict("records"):
                    if pd.isna(row["ticker"]) or pd.isna(row["provider_ticker"]):
                        raise ValueError("Complete both columns of every ticker alias")
                    aliases[provider_symbol(row["ticker"])] = provider_symbol(row["provider_ticker"])
                st.session_state.alias_error = ""
            except ValueError as exc:
                st.session_state.alias_error = str(exc)
                st.error(str(exc))
    result = {
        "source": source, "universe_mode": mode, "tickers": tickers,
        "single_ticker": tickers if mode == "Single stock" else saved.get("single_ticker", "AAPL"),
        "sector": sector, "time_mode": time_mode, "requested_date": str(requested or end),
        "period": period, "custom_start": str(display_start), "custom_end": str(end),
        "cache_only": cache_only,
        "price_update_scope": update_scope,
        "ticker_aliases": aliases,
        **({"membership_digest": membership.digest, "membership_source": membership.source}
           if membership else {}),
    }
    config.data_settings = result
    return {**result, "screen_date": end, "display_start": display_start,
            "demo": demo, "force": False, "retry_missing": False, "refresh_now": False,
            "incomplete_range": period == "Custom dates" and len(custom) != 2}


def moving_average_builder(config: ScreenConfig) -> None:
    st.subheader("Moving average builder")
    st.caption("Add or remove rows. Any positive integer period is allowed. Enabled MAs can be used in rules.")
    base_key = key("ma_base")
    if base_key not in st.session_state:
        st.session_state[base_key] = pd.DataFrame([asdict(m) for m in config.moving_averages],
                                                 columns=["kind", "period", "enabled", "show"])
    base = st.session_state[base_key].copy()
    base["kind"] = base.kind.map(lambda value: MA_TYPES.get(value, value))
    edited = st.data_editor(
        base, num_rows="dynamic", hide_index=True, width="stretch",
        column_config={
            "kind": st.column_config.SelectboxColumn("Type", options=list(MA_TYPES.values()), required=True,
                                                     help="Simple moving average: equal weight to each price in "
                                                          "the rolling window. Exponential moving average: "
                                                          "more weight to recent prices."),
            "period": st.column_config.NumberColumn("Period (sessions)", min_value=1, step=1, required=True,
                                                      help="Number of trading-day prices for SMA, or the EMA "
                                                           "span. A 20-period SMA averages 20 daily prices; "
                                                           "weekends and holidays do not count."),
            "enabled": st.column_config.CheckboxColumn("Enabled", default=True,
                                                        help="Allow this MA to be calculated and selected by rules."),
            "show": st.column_config.CheckboxColumn("Show on charts", default=True,
                                                     help="Display this line on charts. Hiding a line does not "
                                                          "remove its enabled screening rules."),
        }, key=key("ma_editor"),
    )
    averages = []
    try:
        for row in edited.to_dict("records"):
            period = float(row["period"])
            if not math.isfinite(period) or not period.is_integer():
                raise ValueError("Every MA period must be a positive integer")
            kind = next((code for code, label in MA_TYPES.items() if label == row["kind"]), str(row["kind"]))
            ma = MovingAverage(kind, int(period),
                               True if pd.isna(row["enabled"]) else bool(row["enabled"]),
                               True if pd.isna(row["show"]) else bool(row["show"]))
            ma.validate()
            averages.append(ma)
        old = config.moving_averages
        if len(old) == len(averages):
            mapping = {a.key: b.key for a, b in zip(old, averages) if a.key != b.key}
            for rule in config.rules:
                rule.ma = mapping.get(rule.ma, rule.ma)
                rule.other = mapping.get(rule.other, rule.other)
        config.moving_averages = averages
        st.session_state["ma_error"] = ""
    except (ValueError, TypeError, KeyError) as exc:
        st.session_state["ma_error"] = str(exc)
        st.error(str(exc))
    st.caption("Simple moving average (SMA) gives equal weight to the prices in its rolling window. "
               "Exponential moving average (EMA) gives more weight to recent prices, using span=N and "
               "adjust=False. Missing prices reset the EMA. Warm-up history is included automatically.")


def group_builder(config: ScreenConfig):
    st.subheader("How conditions combine")
    root = next(g for g in config.groups if g.id == "root")
    root.logic = st.radio("Root logic", ["AND", "OR"], index=default_option(["AND", "OR"], root.logic),
                          horizontal=True, key=key("root_logic"),
                          help="AND requires all conditions/groups to pass; OR needs any passing branch. "
                               "Missing data is unavailable, never automatically passing.")
    st.caption("AND requires every condition; OR accepts any passing condition. Empty groups are ignored.")
    with st.expander("Nested rule groups"):
        for group in [g for g in config.groups if g.id != "root"]:
            cols = st.columns([2, 1, 2, 1])
            group.name = cols[0].text_input("Group name", group.name, key=key(f"gname_{group.id}"),
                                           help="A descriptive name for this set of conditions; no effect on calculations.")
            group.logic = cols[1].selectbox("Logic", ["AND", "OR"],
                                            index=default_option(["AND", "OR"], group.logic),
                                            key=key(f"glogic_{group.id}"), help="AND = every condition; OR = any condition.")
            parents = [g.id for g in config.groups if g.id != group.id]
            names = {g.id: g.name for g in config.groups}
            group.parent = cols[2].selectbox("Parent group", parents,
                                              index=default_option(parents, group.parent),
                                              format_func=lambda v: names[v], key=key(f"gparent_{group.id}"),
                                              help="The outer group that combines this group's result. Circular groups are invalid.")
            if cols[3].button("Remove", key=key(f"gremove_{group.id}"),
                               help="Remove this group and move its rules/subgroups into its parent."):
                for r in config.rules:
                    if r.group == group.id:
                        r.group = group.parent
                for g in config.groups:
                    if g.parent == group.id:
                        g.parent = group.parent
                config.groups.remove(group)
                st.rerun()
        with st.form(key("add_group_form")):
            name = st.text_input("New group name", "Alternative conditions", help="A label for the new set of conditions.")
            logic = st.selectbox("New group logic", ["AND", "OR"], help="AND requires all children; OR requires any passing child.")
            parent = st.selectbox("Place inside", [g.id for g in config.groups],
                                  format_func=lambda v: next(g.name for g in config.groups if g.id == v),
                                  help="Choose the parent group that will contain this new group.")
            if st.form_submit_button("Add nested group"):
                config.groups.append(Group(id=uid("g"), name=name, logic=logic, parent=parent))
                st.rerun()


def rule_editor(config: ScreenConfig, rule: Rule, relationships: bool = False):
    prefix = f"rule_{rule.id}_"
    options = [m.key for m in config.moving_averages if m.enabled]
    if relationships:
        options = ["PRICE", *options]
    label = f"{'●' if rule.enabled else '○'} {rule.name} · {series_label(rule.ma)}"
    with st.expander(label, expanded=len(config.rules) <= 1):
        top = st.columns([3, 1, 1, 1])
        rule.name = top[0].text_input("Rule name", rule.name, key=key(prefix + "name"), help=CONTROL_HELP["name"])
        rule.enabled = top[1].checkbox("Enabled", value=rule.enabled, key=key(prefix + "enabled"),
                                       help=CONTROL_HELP["enabled"])
        if top[2].button("Duplicate", key=key(prefix + "duplicate"), help=CONTROL_HELP["duplicate"]):
            config.rules.append(replace(rule, id=uid(), name=rule.name + " (copy)"))
            st.rerun()
        if top[3].button("Remove", key=key(prefix + "remove"), help=CONTROL_HELP["remove"]):
            config.rules = [r for r in config.rules if r.id != rule.id]
            st.rerun()
        if not options or (relationships and len(options) < 2):
            st.warning("Enable a moving average in the builder first.")
            return
        cols = st.columns([1, 2])
        # Keep invalid references visible until the user explicitly resolves them.
        ma_options = options if rule.ma in options else [rule.ma, *options]
        rule.ma = cols[0].selectbox("Series / MA", ma_options, index=ma_options.index(rule.ma),
                                    key=key(prefix + "ma"), format_func=series_label, help=CONTROL_HELP["ma"])
        method_options = [m for m in METHODS if (m in RELATION_METHODS) == relationships]
        old_method = rule.method
        rule.method = cols[1].selectbox(
            "Trend method" if not relationships else "Relationship",
            method_options, index=default_option(method_options, rule.method),
            format_func=lambda v: METHODS[v], key=key(prefix + "method"), help=CONTROL_HELP["method"],
        )
        if rule.method != old_method:
            rule.operator = "==" if rule.method in BOOL_METHODS else ">"
            rule.threshold = 1.0 if rule.method in BOOL_METHODS and rule.method != "turn_up" else 0.0
            if rule.method == "positive_pct":
                rule.threshold, rule.operator = 80.0, ">="
            for name, value in (("operator", rule.operator), ("threshold", rule.threshold)):
                st.session_state[key(prefix + name)] = value
        description, example, threshold_help = METHOD_HELP[rule.method]
        st.caption(description)
        st.caption("Example: " + example)
        if relationships:
            other_options = [m.key for m in config.moving_averages if m.enabled]
            if not other_options:
                st.warning("Enable a comparison moving average first.")
                return
            rule.other = st.selectbox("Compare with MA", other_options,
                                      index=default_option(other_options, rule.other), key=key(prefix + "other"),
                                      format_func=series_label, help=CONTROL_HELP["other"])
            st.caption("Difference = 100 × (left / right − 1). Positive means the left line is above the right. "
                       "Absolute separation uses the magnitude of this difference.")
        minimum = 2 if rule.method in REGRESSION_METHODS else 1
        unit = "observations" if rule.method in REGRESSION_METHODS else "daily transitions"
        if rule.method == "relative":
            rule.lookback, unit = 1, "latest observation only"
            st.session_state[key(prefix + "lookback")] = 1
        cols = st.columns(3)
        rule.lookback = int(cols[0].number_input(f"Lookback ({unit})", min_value=minimum,
                                                value=max(minimum, rule.lookback), step=1,
                                                key=key(prefix + "lookback"), disabled=rule.method == "relative",
                                                help=lookback_help(rule.method)))
        rule.operator = cols[1].selectbox("Comparison", list(OPERATORS),
                                          index=default_option(list(OPERATORS), rule.operator),
                                          key=key(prefix + "operator"),
                                          help="Compare the calculated metric with the threshold: > greater than, "
                                               ">= at least, < less than, <= at most, == equal, != not equal. "
                                               "For Turning up, the boolean result is compared with 1.")
        threshold_label = "Threshold"
        if rule.method == "turn_up":
            threshold_label = "Minimum positive slope (% / session)"
        elif rule.method in {"pct_change", "net_increase", "relative", "positive_pct", "max_drawdown_pct"}:
            threshold_label = "Threshold (%)"
        elif rule.method == "normalized_slope":
            threshold_label = "Threshold (% / session)"
        elif rule.method == "accel_slope":
            threshold_label = "Threshold (pp / session)"
        elif rule.method == "accel_pct" or rule.method == "separation_change":
            threshold_label = "Threshold (percentage points)"
        elif rule.method == "slope":
            threshold_label = "Threshold (price units / session)"
        elif rule.method == "r2":
            threshold_label = "Threshold (R-squared, 0–1)"
        elif rule.method in {"positive_count", "negative_count", "longest_streak"}:
            threshold_label = "Threshold (transition count)"
        elif rule.method in BOOL_METHODS:
            threshold_label = "Boolean target (true=1)"
        rule.threshold = float(cols[2].number_input(threshold_label, value=float(rule.threshold),
                                                    step=0.01, format="%.6f", key=key(prefix + "threshold"),
                                                    help=threshold_help))
        cols[0].caption(lookback_help(rule.method))
        cols[1].caption(f"{rule.operator} means {OPERATOR_HELP[rule.operator]}. "
                        + ("The turning-up result is compared with 1." if rule.method == "turn_up"
                           else "The calculated value is compared with your threshold."))
        cols[2].caption(threshold_help)
        if rule.method == "relative":
            rule.lookback = 1
        if rule.method == "turn_up":
            c = st.columns(3)
            rule.reversal_lag = int(c[0].number_input(
                "Previous slope evaluated how many sessions ago?", min_value=1,
                value=rule.reversal_lag, step=1, key=key(prefix + "lag"), help=CONTROL_HELP["lag"]))
            rule.confirmation = int(c[1].number_input(
                "Consecutive positive slope evaluations", min_value=1,
                value=rule.confirmation, step=1, key=key(prefix + "confirmation"), help=CONTROL_HELP["confirmation"]))
            rule.allow_flat = c[2].checkbox("Allow previous slope to be flat", value=rule.allow_flat,
                                            key=key(prefix + "allow_flat"), help=CONTROL_HELP["allow_flat"])
            c[0].caption("Use the slope from exactly this many trading sessions earlier.")
            c[1].caption("Count includes today; each slope must exceed the minimum. Must be ≤ the lag.")
            c[2].caption("Ticked: earlier slope ≤ 0. Unticked: earlier slope < 0.")
            st.caption("The current and confirmation slopes must exceed the minimum above. "
                       "Comparison applies to the turning-up boolean against 1; choose == for turning-up matches.")
        if rule.method in {"accel_pct", "accel_slope"}:
            c = st.columns(2)
            rule.positive_current = c[0].checkbox("Require current rate to be positive",
                                                 value=rule.positive_current, key=key(prefix + "pos_current"),
                                                 help=CONTROL_HELP["pos_current"])
            rule.positive_previous = c[1].checkbox("Require previous rate to be positive",
                                                  value=rule.positive_previous, key=key(prefix + "pos_previous"),
                                                  help=CONTROL_HELP["pos_previous"])
            c[0].caption("The latest change or slope must also be > 0.")
            c[1].caption("The preceding change or slope must also be > 0; untick to allow a declining earlier trend.")
            st.caption("Acceleration compares recent history with preceding history; it is not a forecast.")
        group_ids = [g.id for g in config.groups]
        rule.group = st.selectbox("Rule group", group_ids, index=default_option(group_ids, rule.group),
                                   format_func=lambda v: next(g.name for g in config.groups if g.id == v),
                                   key=key(prefix + "group"), help=CONTROL_HELP["group"])
        selected_group = next(g for g in config.groups if g.id == rule.group)
        st.caption(f"This rule belongs to {selected_group.name}: "
                   + ("all conditions in this group must pass." if selected_group.logic == "AND"
                      else "any passing condition in this group is enough."))
        if not relationships:
            c = st.columns(2)
            use_r2 = c[0].checkbox("Also require minimum R-squared", value=rule.min_r2 is not None,
                                    key=key(prefix + "use_r2"), help=CONTROL_HELP["use_r2"])
            r2 = c[0].number_input("Minimum R-squared", min_value=0.0, max_value=1.0,
                                    value=rule.min_r2 if rule.min_r2 is not None else 0.8, step=0.01,
                                    disabled=not use_r2, key=key(prefix + "r2"), help=CONTROL_HELP["r2"])
            c[0].caption("Optional linear-fit consistency requirement: 0.80 means 80% explained variation. "
                         "A high R-squared can describe either an upward or downward line.")
            rule.min_r2 = float(r2) if use_r2 else None
            use_positive = c[1].checkbox("Also require mostly rising", value=rule.min_positive_pct is not None,
                                          key=key(prefix + "use_positive"), help=CONTROL_HELP["use_positive"])
            positive = c[1].number_input(
                "Minimum positive transitions (%)", min_value=0.0, max_value=100.0,
                value=rule.min_positive_pct if rule.min_positive_pct is not None else 80.0,
                step=1.0, disabled=not use_positive, key=key(prefix + "positive"), help=CONTROL_HELP["positive"])
            c[1].caption("Optional daily-rise requirement: 80 means 80% positive transitions. Flat changes "
                         "do not count as positive. Uses the latest component for acceleration/turning rules.")
            rule.min_positive_pct = float(positive) if use_positive else None
        st.info(window_description(rule))
        if rule.method in {"normalized_slope", "slope", "r2"}:
            st.caption("Regression describes overall direction. It does not imply increases on every day.")
        if rule.method == "net_increase":
            st.caption("This method additionally requires end > start. Use Net percentage change for unrestricted comparisons.")


def build_panel(config):
    averages, trends, relationships, risk = st.tabs(
        ["Moving averages", "Trend rules", "Relationships", "Risk settings"])
    with averages:
        with st.container(border=True):
            moving_average_builder(config)
    with trends:
        group_builder(config)
        st.divider()
        st.subheader("Trend detection rules")
        st.caption("Each rule has its own MA, method and lookback. A 10-observation regression uses 9 daily transitions.")
        for rule in [r for r in config.rules if r.method not in RELATION_METHODS]:
            rule_editor(config, rule)
        if st.button("Add trend rule", key=key("add_trend")):
            options = [m.key for m in config.moving_averages if m.enabled]
            config.rules.append(Rule(name="New upward trend", ma=options[0] if options else "SMA20"))
            st.rerun()
    with relationships:
        relationship_builder(config)
    with risk:
        risk_settings_panel(config, key)
    try:
        config.validate()
        st.caption(f"Draft ready · {sum(r.enabled for r in config.rules)} active conditions · "
                   f"{sum(m.enabled for m in config.moving_averages)} enabled MAs · "
                   f"at least {config.required_history()} history sessions requested")
    except ValueError as exc:
        st.warning(f"Before running: {exc}")


def relationship_builder(config):
    st.subheader("Moving average relationships")
    st.caption("Build bullish/bearish alignments with multiple comparisons. Crossovers test any selected pair.")
    with st.expander("Quick alignment builder"):
        options = [m.key for m in sorted(config.moving_averages, key=lambda m: (m.period, m.kind)) if m.enabled]
        alignment = st.selectbox("Alignment direction", ["Bullish", "Bearish"], key=key("alignment_direction"))
        selected = st.multiselect("MAs in shortest-to-longest order", options, default=options,
                                  key=key("alignment_mas"), format_func=series_label)
        if st.button("Add alignment group", key=key("add_alignment")):
            if len(selected) < 2:
                st.warning("Choose at least two moving averages.")
            else:
                group = Group(uid("g"), f"{alignment} alignment", "AND", "root")
                config.groups.append(group)
                for a, b in zip(selected, selected[1:]):
                    config.rules.append(Rule(name=f"{a} {'above' if alignment == 'Bullish' else 'below'} {b}",
                                             ma=a, other=b, method="relative", lookback=1,
                                             operator=">" if alignment == "Bullish" else "<", group=group.id))
                st.rerun()
    for rule in [r for r in config.rules if r.method in RELATION_METHODS]:
        rule_editor(config, rule, relationships=True)
    if st.button("Add relationship rule", key=key("add_relationship")):
        options = [m.key for m in config.moving_averages if m.enabled]
        config.rules.append(Rule(name="Price above moving average", ma="PRICE", method="relative",
                                 other=options[0] if options else "SMA20", lookback=1))
        st.rerun()


def resolve_universe(settings):
    mode = settings["universe_mode"]
    if mode == "Historical membership CSV":
        membership = MembershipHistory.load(home() / "research")
        if membership is None:
            raise ValueError("Upload historical membership intervals in Historical research → Membership data first")
        frame = membership.at(settings["screen_date"])
        if frame.empty:
            raise ValueError("The historical membership source contains no members on this date")
        return frame
    if mode in {"Custom tickers", "Single stock"}:
        tickers = parse_tickers(settings["tickers"])
        if not tickers or (mode == "Single stock" and len(tickers) != 1):
            raise ValueError("Enter exactly one ticker" if mode == "Single stock" else "Enter at least one ticker")
        frame = custom_universe(tickers)
        snapshot = st.session_state.get("universe_snapshot")
        if snapshot and not settings["demo"]:
            known = snapshot.frame.set_index("ticker")
            for i, row in frame.iterrows():
                if row.ticker in known.index:
                    frame.loc[i, ["company", "sector", "industry"]] = known.loc[row.ticker, ["company", "sector", "industry"]].values
        return frame
    if mode == "S&P 500 index":
        symbol = "^DEMO500" if settings["demo"] else "^GSPC"
        frame = custom_universe([symbol])
        frame.loc[0, "company"] = "Synthetic benchmark" if settings["demo"] else "S&P 500 price index"
        frame.loc[0, "sector"] = "Benchmark"
        return frame
    if settings["demo"]:
        frame = demo_universe()
    else:
        snapshot = UniverseService(home() / "universe").get()
        st.session_state.universe_snapshot = snapshot
        if snapshot.warning:
            st.warning(snapshot.warning)
        frame = snapshot.frame
    if mode == "Sector":
        if not settings["sector"]:
            raise ValueError("Load the sector list and select a sector")
        frame = frame[frame.sector == settings["sector"]]
    if frame.empty:
        raise ValueError("The selected universe has no stocks")
    return frame.reset_index(drop=True)


def run_screen(config: ScreenConfig, settings):
    try:
        if st.session_state.get("ma_error"):
            raise ValueError(st.session_state.ma_error)
        if st.session_state.get("alias_error"):
            raise ValueError(st.session_state.alias_error)
        if config.risk.enabled and st.session_state.get("risk_settings_error"):
            raise ValueError(st.session_state.risk_settings_error)
        if settings["incomplete_range"]:
            raise ValueError("Complete the custom date range")
        if settings["display_start"] > settings["screen_date"]:
            raise ValueError("History start must precede the effective screen date")
        if (settings["force"] or settings.get("refresh_now")) and settings["cache_only"]:
            raise ValueError("Turn off Saved prices only before updating prices")
        snapshot_config = ScreenConfig.from_dict(config.to_dict(), require_rules=True)
        progress = st.progress(0.0, text="Resolving stock universe…")
        universe = resolve_universe(settings)
        universe["provider_ticker"] = universe.ticker.map(lambda t: settings["ticker_aliases"].get(t, t))
        end, display_start = settings["screen_date"], settings["display_start"]
        start = history_start(display_start, end, snapshot_config.required_history())
        download_tickers = list(dict.fromkeys([
            *universe.ticker.tolist(), *([snapshot_config.risk.benchmark] if snapshot_config.risk.enabled else [])]))
        data_key = (settings["source"], settings["cache_only"], tuple(download_tickers),
                    tuple(sorted(settings["ticker_aliases"].items())), str(start), str(end))
        reuse = (not settings["force"] and not settings["retry_missing"] and not settings.get("refresh_now", False)
                 and st.session_state.get("data_key") == data_key)
        if reuse:
            batch = st.session_state.raw_batch
            progress.progress(0.55, text="Reusing loaded prices; applying new rules…")
            downloads = []
        else:
            provider = AliasedProvider(DemoProvider() if settings["demo"] else YFinanceProvider(),
                                       settings["ticker_aliases"])
            def downloaded(done, total):
                progress.progress(0.05 + 0.5 * done / max(total, 1),
                                  text=f"Downloading prices: {done} / {total}")
            progress.progress(0.05, text="Checking saved prices before requesting missing data…")
            batch = PriceCache(home() / "prices", provider).get_many(
                download_tickers, start, end, force=settings["force"],
                refresh_recent=False, refresh_now=settings.get("refresh_now", False),
                cache_only=settings["cache_only"], progress=downloaded,
                retry_missing=settings["retry_missing"],
            )
            downloads = batch.downloads
            st.session_state.raw_batch, st.session_state.data_key = batch, data_key
            st.session_state.data_loaded_at = time.time()
            st.session_state.indicator_cache = {}
            st.session_state.risk_cache = {}
        def analyzed(done, total):
            progress.progress(0.55 + 0.45 * done / max(total, 1), text=f"Analyzing: {done} / {total}")
        run = screen(universe, batch.frames, snapshot_config, end,
                     indicator_cache=st.session_state.setdefault("indicator_cache", {}),
                     risk_cache=st.session_state.setdefault("risk_cache", {}), progress=analyzed)
        st.session_state.run = run
        st.session_state.run_batch = batch
        st.session_state.run_price_activity = {
            "source": "In-memory saved prices" if reuse else "Local price cache",
            "downloads": downloads,
            "symbols_requested": len({t for request in downloads for t in request["tickers"]}),
            "action": "Update prices & run" if settings.get("refresh_now") or settings["force"] else "Run Screen",
        }
        st.session_state.run_universe_snapshot = st.session_state.get("universe_snapshot")
        st.session_state.run_settings = settings.copy()
        st.session_state.run_config_json = config.to_json()
        st.session_state.pop("history_download", None)
        st.session_state.pop("excel_download", None)
        st.session_state.pop("forward_table", None)
        st.session_state.run_id = st.session_state.get("run_id", 0) + 1
        try:
            st.session_state.saved_screen_id = HistoryStore(home() / "research").save_screen(run)
        except (OSError, sqlite3.Error) as exc:
            st.warning(f"Screen completed, but its local history snapshot could not be saved: {exc}")
        progress.empty()
        st.success(f"Screen complete: {run.summary()['passing']} of {len(run.table)} stocks matched on {end}.")
        if not downloads:
            st.caption("Used saved prices. No price downloads were requested.")
    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
        st.error(f"Screen could not complete: {exc}")


def render_chart(run: ScreenRun, ticker: str, display_start: date, widget_prefix: str):
    company = run.table.set_index("ticker").loc[ticker]
    st.markdown(f"#### {ticker} · {company['company']}")
    columns = st.columns(3)
    p = company["latest_adjusted_price"]
    columns[0].metric("Latest adjusted close", f"{p:,.2f}" if pd.notna(p) else "Unavailable")
    columns[1].metric("Latest price session", company["latest_date"] or "Unavailable")
    columns[2].metric("Overall result", company["status"])
    rules = [r for r in run.config.rules if r.enabled]
    chosen = st.selectbox("Highlight one rule", [r.id for r in rules],
                          format_func=lambda v: next(r.name for r in rules if r.id == v),
                          key=widget_prefix + "_rule")
    rule = next(r for r in rules if r.id == chosen)
    active = [m for m in run.config.moving_averages if m.enabled]
    group = st.radio("Chart lines", ["Selected MAs", "Short term (≤50)", "Long term (>50)", "Custom"],
                      horizontal=True, key=widget_prefix + "_lines")
    selected = [m.key for m in active if m.show]
    if group.startswith("Short"):
        selected = [m.key for m in active if m.period <= 50]
    elif group.startswith("Long"):
        selected = [m.key for m in active if m.period > 50]
    elif group == "Custom":
        selected = st.multiselect("Moving averages on chart", [m.key for m in active], default=selected,
                                   key=widget_prefix + "_mas")
    evaluation = run.evaluations[ticker][rule.id]
    show_figure(price_chart(run.frames[ticker], ticker, run.config, display_start, rule,
                            evaluation, selected), key=widget_prefix + "_plot")
    st.caption("The shaded segment contains exactly the observations used by the highlighted rule. "
               "The chart ends at the screening date. Red markers indicate declining MA transitions; gray means flat.")
    with st.expander("Calculation details"):
        st.dataframe(information_panel(rule, evaluation), hide_index=True, width="stretch")
    with st.expander("Every rule for this stock"):
        st.dataframe(pd.DataFrame([{
            "Rule": r.name, "MA": r.ma, "Window": window_description(r),
            "Result": "PASS" if run.evaluations[ticker][r.id].passed else
                      ("FAIL" if run.evaluations[ticker][r.id].valid else "UNAVAILABLE"),
            "Value": run.evaluations[ticker][r.id].value,
            "Detail": run.evaluations[ticker][r.id].reason,
        } for r in rules]), hide_index=True, width="stretch")
    st.download_button("Download this stock's prices, returns and MAs", run.frames[ticker].to_csv(),
                        file_name=f"{ticker}_{run.screen_date}_history.csv", mime="text/csv",
                        key=widget_prefix + "_csv")


def results_panel(run: ScreenRun, display_start):
    st.subheader("Screening results")
    summary = run.summary()
    cols = st.columns(5)
    for col, name, label in zip(cols, ["requested", "analyzed", "insufficient", "passing", "passing_pct"],
                                ["Requested", "Analyzed", "Insufficient", "Passing", "Passing (%)"]):
        col.metric(label, f"{summary[name]:.1f}" if name.endswith("pct") else summary[name])
    st.caption("Analyzed means the root AND/OR expression can be decided. Missing rules are unavailable, "
               "never passing. A decidable OR may pass despite another unavailable branch.")
    activity = st.session_state.get("run_price_activity")
    if activity:
        if activity["downloads"]:
            st.caption(f"{activity['action']}: requested prices for {activity['symbols_requested']} symbols. "
                       "Existing saved history was reused where possible; failures appear in Data diagnostics.")
            with st.expander("Price download activity"):
                st.dataframe(pd.DataFrame([{
                    "Reason": item["reason"], "Start": item["start"], "End": item["end"],
                    "Symbols": ", ".join(item["tickers"]),
                } for item in activity["downloads"]]), hide_index=True, width="stretch")
        else:
            st.caption(f"Price source: {activity['source']}. No price downloads were requested for this screen.")
    batch = st.session_state.get("run_batch")
    if batch:
        stamps = [m.get("last_success") for m in batch.metadata.values() if m.get("last_success")]
        if stamps:
            st.caption(f"Last successful price downloads (UTC): {min(stamps)} to {max(stamps)}.")
        if batch.errors or batch.warnings:
            with st.expander(f"Data diagnostics ({len(batch.errors)} ticker issues)"):
                for warning in batch.warnings:
                    st.warning(warning)
                st.dataframe(pd.DataFrame([{"Ticker": t, "Issue": e} for t, e in batch.errors.items()]),
                             hide_index=True, width="stretch")
    snapshot = st.session_state.get("run_universe_snapshot")
    if snapshot and run.config.data_settings.get("universe_mode") in {"S&P 500 (current constituents)", "Sector"}:
        st.caption(f"Membership snapshot: {snapshot.retrieved_at} · source: {snapshot.source}")
    matches_only = st.toggle("Show matching stocks only", value=True, key="matches_only")
    table = run.passing if matches_only else run.table
    view = st.radio("Table view", ["Overview", "Trend details", "Risk comparison", "Custom"],
                    horizontal=True, key=f"table_view_{st.session_state.run_id}")
    if view == "Risk comparison" and not run.config.risk.enabled:
        st.info("Enable metrics in Build screen → Risk settings and run again to compare risk statistics.")
    overview = ["ticker", "company", "latest_adjusted_price", "daily_return_pct",
                "rank_normalized_slope", "status"]
    trend = ["ticker", "company", "latest_adjusted_price",
             *[m.key for m in run.config.moving_averages if m.enabled],
             "rank_normalized_slope", "rank_pct_change", "rank_r2", "rank_longest_streak",
             "rules_passed", "rules_unavailable", "status"]
    risk_columns = []
    if run.config.risk.enabled:
        horizon = max(run.config.risk.lookbacks)
        overview += [f"risk_{horizon}_{m}" for m in ("sharpe", "beta") if m in run.config.risk.metrics]
        risk_columns = [f"risk_{n}_{m}" for n in run.config.risk.lookbacks for m in run.config.risk.metrics]
        st.caption(f"Risk benchmark: {run.config.risk.benchmark} · "
                   f"annual risk-free assumption: {run.config.risk.risk_free_pct:g}%. "
                   "Risk metrics use adjusted simple returns; blank values indicate incomplete data or undefined ratios. "
                   "The risk panel compares periods and explains the calculations.")
    defaults = {
        "Overview": overview, "Trend details": trend,
        "Risk comparison": ["ticker", "company", *risk_columns, "status"],
        "Custom": [*overview, "sector", "return_5d_pct", "return_20d_pct", "rules_passed", "rules_unavailable"],
    }
    default_columns = list(dict.fromkeys(c for c in defaults[view] if c in table))
    with st.expander("Choose visible columns"):
        visible = st.multiselect("Visible columns", list(table.columns), default=default_columns,
                                 format_func=table_column_label,
                                 key=f"visible_columns_{st.session_state.run_id}_{view}")
    if not visible:
        visible = ["ticker", "status"]
    if table.empty:
        st.info("No stocks matched. Inspect all stocks by turning off the matching-only toggle, or change the rules.")
    event = st.dataframe(table[visible], hide_index=True, width="stretch", height=400,
                          column_config={
                              **table_column_formats(),
                              **{
                              name: st.column_config.NumberColumn(table_column_label(name),
                                                                   help=risk_column_label(name), format="%.4f")
                              for name in visible if any(name == f"risk_{n}_{m}"
                                                        for n in run.config.risk.lookbacks for m in RISK_METRICS)}},
                          selection_mode="single-row", on_select="rerun",
                          key=f"results_table_{st.session_state.run_id}_{matches_only}")
    st.caption("Select a row to open its detailed chart below. Column headers sort the table. "
               "Rule metric columns use rule IDs; the configuration maps IDs to names.")
    if event.selection.rows:
        ticker = table.iloc[event.selection.rows[0]].ticker
        st.session_state.selected_ticker = ticker
        render_chart(run, ticker, display_start, f"row_chart_{st.session_state.run_id}_{ticker}")
    with st.expander("Sector breadth and statistical comparisons"):
        breadth = run.table.groupby("sector", dropna=False).agg(
            requested=("ticker", "size"), passing=("passed", "sum"),
            average_normalized_slope=("rank_normalized_slope", "mean"),
            median_normalized_slope=("rank_normalized_slope", "median"),
            average_20d_return_pct=("return_20d_pct", "mean"),
        )
        breadth["passing_pct"] = 100 * breadth.passing / breadth.requested
        st.dataframe(breadth, width="stretch")
    with st.expander("Export & download"):
        st.download_button("Download displayed results CSV", table.to_csv(index=False),
                            file_name=f"screen_{run.screen_date}.csv", mime="text/csv")
        st.download_button("Download all results and diagnostics CSV", run.table.to_csv(index=False),
                            file_name=f"all_results_{run.screen_date}.csv", mime="text/csv")
        c = st.columns(2)
        if c[0].button("Prepare Excel download"):
            st.session_state.excel_download = excel_bytes(run.table)
        if st.session_state.get("excel_download"):
            c[0].download_button("Download Excel", st.session_state.excel_download,
                                 file_name=f"screen_{run.screen_date}.xlsx",
                                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if c[1].button("Prepare historical prices and MA archive"):
            st.session_state.history_download = history_zip(run)
        if st.session_state.get("history_download"):
            c[1].download_button("Download histories ZIP", st.session_state.history_download,
                                 file_name=f"histories_{run.screen_date}.zip", mime="application/zip")


def explorer_panel(run, display_start):
    include_all = st.checkbox("Include stocks that did not match", value=run.passing.empty, key="explorer_all")
    choices = run.table.ticker.tolist() if include_all else run.passing.ticker.tolist()
    if not choices:
        st.info("No matches. Enable the option above to inspect failed or unavailable stocks.")
        return
    selected = st.session_state.get("selected_ticker")
    ticker = st.selectbox("Stock", choices, index=default_option(choices, selected),
                          key=f"explorer_ticker_{st.session_state.run_id}_{include_all}")
    render_chart(run, ticker, display_start, f"explorer_{st.session_state.run_id}_{ticker}")


def grid_panel(run, display_start):
    st.caption("Only the selected page is rendered. Ranking uses the chosen rule's own window.")
    if run.passing.empty:
        st.info("No matching stocks for the grid.")
        return
    rules = [r for r in run.config.rules if r.enabled and r.ma != "PRICE"]
    if not rules:
        rules = [r for r in run.config.rules if r.enabled]
    chosen = st.selectbox("Ranking / highlight rule", [r.id for r in rules],
                          format_func=lambda v: next(r.name for r in rules if r.id == v), key="grid_rule")
    metrics = {"Normalized MA slope": f"{chosen}.normalized_slope",
               "MA percentage increase": f"{chosen}.pct_change", "Regression R-squared": f"{chosen}.r2",
               "Longest rising streak": f"{chosen}.longest_streak", "Recent 20-day stock return": "return_20d_pct"}
    if run.config.risk.enabled:
        horizon = st.selectbox("Performance ranking lookback", run.config.risk.lookbacks,
                               index=run.config.risk.lookbacks.index(max(run.config.risk.lookbacks)),
                               key="grid_risk_horizon")
        metrics.update({
            "Highest Sharpe": f"risk_{horizon}_sharpe",
            "Highest Sortino": f"risk_{horizon}_sortino",
            "Highest alpha": f"risk_{horizon}_alpha_ann_pct",
            "Lowest beta": f"risk_{horizon}_beta",
            "Lowest volatility": f"risk_{horizon}_volatility_ann_pct",
            "Smallest drawdown": f"risk_{horizon}_max_drawdown_pct",
        })
    sort = st.selectbox("Sort charts by", list(metrics), key="grid_sort")
    c = st.columns(3)
    size = c[0].selectbox("Charts per page", [4, 8, 12, 20], key="grid_size")
    per_row = c[1].selectbox("Charts per row", [1, 2, 3, 4], index=1, key="grid_columns")
    pages = max(1, math.ceil(len(run.passing) / size))
    page = int(c[2].number_input("Page", min_value=1, max_value=pages,
                                 value=1, step=1, key=f"grid_page_{pages}_{size}"))
    if not st.toggle("Render chart grid", value=False, key="grid_render"):
        st.info("Enable the grid to draw this page of interactive charts.")
        return
    data = run.passing
    column = metrics[sort]
    if column in data:
        data = data.sort_values(column, ascending=sort in {"Lowest beta", "Lowest volatility", "Smallest drawdown"},
                                na_position="last")
    subset = data.iloc[(page - 1) * size:page * size]
    st.caption(f"Page {page} of {pages} · {len(run.passing)} matches")
    rule = next(r for r in rules if r.id == chosen)
    for offset in range(0, len(subset), per_row):
        cols = st.columns(per_row)
        for col, ticker in zip(cols, subset.iloc[offset:offset + per_row].ticker):
            with col:
                show_figure(price_chart(run.frames[ticker], ticker, run.config, display_start,
                                         rule, run.evaluations[ticker][rule.id], height=370),
                            key=f"grid_{st.session_state.run_id}_{ticker}")


def presets_panel(config):
    store = PresetStore(home() / "presets")
    examples = {f"Example · {c.name}": c for c in builtins()}
    saved = store.list()
    choices = {**examples, **{f"Saved · {name}": cfg for name, cfg in saved.items()}}
    choice = st.selectbox("Screening preset", list(choices), key="preset_choice")
    st.button("Load preset", on_click=load_config, args=(choices[choice],), key="load_preset")
    st.caption("Loading changes the draft. Click Run Screen to apply it. All example values are editable.")
    name = st.text_input("Save current draft as", value=config.name, key=key("preset_name"))
    config.name = name
    if st.button("Save preset"):
        try:
            store.save(config)
            st.success(f"Saved {name}")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    st.download_button("Download current configuration JSON", config.to_json(),
                        file_name="screen_configuration.json", mime="application/json")
    upload = st.file_uploader("Import screening configuration JSON", type=["json"])
    if st.button("Load uploaded configuration", disabled=upload is None):
        try:
            load_config(ScreenConfig.from_json(upload.getvalue().decode("utf-8")))
            st.rerun()
        except (ValueError, UnicodeError) as exc:
            st.error(str(exc))
    if saved:
        st.divider()
        old = st.selectbox("Manage saved preset", list(saved), key="manage_preset")
        new = st.text_input("New preset name", value=old, key=f"rename_{old}")
        if st.button("Rename saved preset"):
            try:
                store.rename(old, new)
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
        if st.button("Delete selected saved preset"):
            store.delete(old)
            st.rerun()
    with st.expander("Current JSON and rule IDs"):
        st.json(config.to_dict())


def research_panel(run):
    st.subheader("Forward performance research")
    st.warning("This view deliberately uses prices AFTER the screen date. These outcomes are never used by rules.")
    st.caption("Current-constituent screens are survivorship-biased. Yahoo's adjusted history is retrospectively "
               "restated; this is not a point-in-time institutional backtest or a strategy performance claim.")
    if not st.checkbox("Enable separate forward-outcome research", key="enable_research"):
        return
    latest = latest_completed_session()
    if run.screen_date >= latest:
        st.info("Choose an earlier historical screening date to measure subsequent outcomes.")
        return
    population = st.radio("Outcome population", ["Matching stocks", "All screened stocks"],
                          horizontal=True, key="research_population")
    table = run.passing if population == "Matching stocks" else run.table
    if table.empty:
        st.info("No stocks in this population.")
        return
    if st.button("Calculate 5 / 20 / 60-session forward returns"):
        provider = AliasedProvider(DemoProvider() if st.session_state.run_settings["demo"] else YFinanceProvider(),
                                   run.config.data_settings.get("ticker_aliases", {}))
        with st.spinner("Loading separate forward outcomes…"):
            try:
                data = PriceCache(home() / "prices", provider).get_many(
                    table.ticker.tolist(), run.screen_date, latest, refresh_recent=False,
                    cache_only=st.session_state.run_settings["cache_only"],
                )
                st.session_state.forward_table = forward_returns(data.frames, run.screen_date, latest)
                st.session_state.forward_population = population
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
    outcome = st.session_state.get("forward_table")
    if outcome is not None:
        st.caption(f"Outcome population used: {st.session_state.get('forward_population')} · "
                   "NA means the full forward horizon is not yet available or has missing observations.")
        st.dataframe(outcome, hide_index=True, width="stretch")
        numeric = outcome.filter(like="_return_pct")
        st.dataframe(numeric.agg(["count", "mean", "median", "min", "max"]), width="stretch")
        st.download_button("Download separate forward outcomes", outcome.to_csv(index=False),
                            file_name=f"forward_research_{run.screen_date}.csv", mime="text/csv")


def main():
    st.set_page_config(page_title="MA Trend Lab · S&P 500 Screener", page_icon="📈", layout="wide")
    apply_workspace_style()
    if "draft" not in st.session_state:
        st.session_state.draft = builtins()[0]
        st.session_state.editor_version = 0
    config = st.session_state.draft
    header_slot = st.empty()
    settings = settings_panel(config)
    with st.container(border=True, key="run_toolbar"):
        left, update, right = st.columns([1, 1.3, 2.7])
        run_clicked = left.button("Run Screen", type="primary", width="stretch", key="run_screen",
                                    help="Reuse saved prices; download only missing histories/ranges unless Saved prices only is selected.")
        update_clicked = update.button("Update prices & run", width="stretch", key="update_prices",
                                         disabled=settings["cache_only"],
                                         help="Refresh existing prices using the sidebar update scope, repair missing data, "
                                              "then apply the draft screen. Turn off Saved prices only to enable this.")
        right.markdown('<p class="lab-toolbar-title">Your screen, ready when you are.</p>'
                       '<p class="lab-toolbar-copy">Run Screen reuses saved prices. '
                       'Update prices &amp; run explicitly refreshes them.</p>', unsafe_allow_html=True)
    build, results, explorer, performance, grid, presets, research, history = st.tabs(
        ["Build screen", "Results", "Stock explorer", "Risk & performance",
         "Chart grid", "Saved presets", "Historical research", "Screen history"])
    with build:
        build_panel(config)
    # Config name changes in presets are included before execution and the draft fingerprint.
    with presets:
        presets_panel(config)
    if run_clicked or update_clicked:
        run_screen(config, {**settings, "refresh_now": update_clicked, "retry_missing": update_clicked,
                            "force": update_clicked and settings["price_update_scope"] == "Full price history"})
    run = st.session_state.get("run")
    applied = st.session_state.run_settings if run is not None else settings
    with history:
        history_panel(home())
    with research:
        research_lab(run, applied, home(), research_panel)
    with header_slot.container():
        workspace_header(run, demo=applied["demo"])
        context_strip([
            ("Universe", applied["universe_mode"]),
            ("Source", "Synthetic demo" if applied["demo"] else "Yahoo Finance"),
            ("Session", run.screen_date if run is not None else applied["screen_date"]),
        ])
        if run is not None and config.to_json() != st.session_state.run_config_json:
            st.warning("Draft settings have changed. Click Run Screen to update the results.")
    if run is not None:
        with results:
            if applied["demo"]:
                st.info("SYNTHETIC DEMO RESULTS · No real prices were used.")
            elif applied["universe_mode"] in {"S&P 500 (current constituents)", "Sector"}:
                st.caption("Current S&P 500 membership; past-date analyses have survivorship bias.")
            if applied["universe_mode"] == "S&P 500 index":
                st.caption("The live benchmark is ^GSPC, the S&P 500 price index, not a dividend-reinvested index.")
            results_panel(run, applied["display_start"])
        with explorer:
            explorer_panel(run, applied["display_start"])
        with performance:
            stock_risk, portfolio_risk = st.tabs(["Stock metrics", "Portfolio concentration"])
            with stock_risk:
                performance_panel(run, demo=applied["demo"], widget_prefix=f"risk_{st.session_state.run_id}")
            with portfolio_risk:
                portfolio_panel(run, home())
        with grid:
            grid_panel(run, applied["display_start"])
    else:
        messages = [
            (results, "Your results will appear here", "Choose a universe and configure the builder, then click Run Screen. "
             "Synthetic demo in Data settings is ready to explore without a market-data connection."),
            (explorer, "See the story behind each trend", "Run a screen, select a stock, and inspect the exact "
             "moving-average segment and regression used by each rule."),
            (performance, "Compare return and risk", "Run a screen to compare Sharpe, beta, alpha and other metrics "
             "across your selected lookback periods."),
            (grid, "Put your matches side by side", "After screening, choose a ranking metric and compare "
             "interactive stock charts on one page."),
        ]
        for tab, title, description in messages:
            with tab:
                empty_state(title, description)
    st.markdown('<footer class="lab-footer">MA Trend Lab · Daily market research<br>'
                'Historical prices describe observed behavior and do not forecast returns. '
                'Current-constituent historical screens have survivorship bias. '
                'Historical membership requires a supplied interval dataset.</footer>',
                unsafe_allow_html=True)
