"""Performance settings and stock analytics, separated from MA rule controls."""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from .models import ScreenConfig
from .risk import RISK_METRICS, numeric_prices, rolling_metrics
from .universe import provider_symbol


def risk_settings_panel(config: ScreenConfig, key):
    risk = config.risk
    with st.expander("Risk & performance settings", expanded=True):
        risk.enabled = st.checkbox("Calculate risk and performance metrics", value=risk.enabled,
                                    key=key("risk_enabled"))
        st.caption("Compare Sharpe ratios and other metrics across several periods at once. "
                   "Each N-return window requires N+1 consecutive adjusted closes.")
        windows = st.text_input(
            "Lookbacks (daily returns, comma-separated)",
            value=", ".join(map(str, risk.lookbacks)), key=key("risk_lookbacks"), disabled=not risk.enabled,
            help="For example: 21, 63, 126, 252. Arbitrary integers of at least 2 are supported.")
        choices = ["SPY", "^GSPC", "QQQ", "Custom"]
        selection = risk.benchmark if risk.benchmark in choices[:-1] else "Custom"
        benchmark = st.selectbox("Benchmark for beta, alpha and information ratio", choices,
                                 index=choices.index(selection), key=key("risk_benchmark"),
                                 disabled=not risk.enabled)
        if benchmark == "Custom":
            benchmark = st.text_input("Custom benchmark ticker", value=risk.benchmark,
                                       key=key("risk_custom_benchmark"), disabled=not risk.enabled)
        columns = st.columns(3)
        risk.risk_free_pct = float(columns[0].number_input(
            "Assumed annual risk-free rate (%)", min_value=-99.99, value=float(risk.risk_free_pct),
            step=0.25, format="%.4f", key=key("risk_rf"), disabled=not risk.enabled,
            help="An effective annual rate that you specify. The app does not fetch a live Treasury rate."))
        risk.annualization = int(columns[1].number_input(
            "Trading sessions per year", min_value=1, max_value=366, value=risk.annualization,
            step=1, key=key("risk_annualization"), disabled=not risk.enabled))
        targets = ["risk_free", "custom"]
        risk.sortino_target = columns[2].selectbox(
            "Sortino target return", targets, index=targets.index(risk.sortino_target),
            format_func=lambda v: "Use risk-free rate" if v == "risk_free" else "Custom annual target",
            key=key("risk_target"), disabled=not risk.enabled)
        if risk.sortino_target == "custom":
            risk.target_return_pct = float(st.number_input(
                "Assumed annual Sortino target (%)", min_value=-99.99, value=float(risk.target_return_pct),
                step=0.25, format="%.4f", key=key("risk_target_pct"), disabled=not risk.enabled))
        risk.metrics = st.multiselect(
            "Performance metrics to display", list(RISK_METRICS), default=risk.metrics,
            format_func=lambda m: RISK_METRICS[m], key=key("risk_metrics"), disabled=not risk.enabled)
        st.caption("Risk statistics always use adjusted daily simple returns, including when the MA chart uses "
                   "unadjusted prices or the daily-return display uses log returns. SPY is an adjusted ETF "
                   "benchmark; ^GSPC is a price index and excludes reinvested dividends.")
        try:
            if risk.enabled:
                parsed = [int(v) for v in re.split(r"[,;\s]+", windows.strip()) if v]
                if not parsed or any(n < 2 for n in parsed):
                    raise ValueError("Enter one or more lookbacks of at least 2 daily returns")
                risk.lookbacks = sorted(set(parsed))
                risk.benchmark = provider_symbol(benchmark)
            risk.validate()
            st.session_state.risk_settings_error = ""
        except (ValueError, TypeError) as exc:
            st.session_state.risk_settings_error = str(exc)
            st.error(str(exc))
        st.caption("Default risk-free assumption: 0% annually. Changes apply with Run Screen and are saved in presets.")


def _formatted(value):
    return "Unavailable" if not np.isfinite(value) else f"{value:,.4f}"


def performance_panel(run, *, demo: bool, widget_prefix: str):
    risk = run.config.risk
    if not risk.enabled:
        st.info("Enable risk and performance metrics in Build screen, then click Run Screen.")
        return
    st.subheader("Risk & performance")
    if demo:
        st.info("SYNTHETIC DATA · Stock and benchmark statistics both use fictional demo prices.")
    st.caption("These statistics describe historical stock returns. They are not returns from a backtest of "
               "the moving-average screening rules.")
    choices = run.table.ticker.tolist()
    preferred = st.session_state.get("selected_ticker")
    index = choices.index(preferred) if preferred in choices else 0
    ticker = st.selectbox("Stock for risk analysis", choices, index=index, key=widget_prefix + "_stock")
    reports = run.risk_reports[ticker]
    lookback = st.selectbox("Detail lookback (daily returns)", risk.lookbacks,
                            index=risk.lookbacks.index(max(risk.lookbacks)),
                            format_func=lambda n: f"{n} returns / {n + 1} closes",
                            key=widget_prefix + "_lookback")
    report = reports[lookback]
    provider_symbol_used = run.config.data_settings.get("ticker_aliases", {}).get(risk.benchmark, risk.benchmark)
    label = risk.benchmark if provider_symbol_used == risk.benchmark else f"{risk.benchmark} (provider: {provider_symbol_used})"
    st.caption(f"Benchmark: {label} · risk-free assumption: {risk.risk_free_pct:g}% per year · "
               f"{risk.annualization} sessions/year · Sortino target: {risk.target_pct:g}% per year.")
    if provider_symbol_used == "^GSPC":
        st.caption("^GSPC is a price-index benchmark and excludes reinvested dividends.")
    if report.start_date:
        st.caption(f"Requested window: {report.start_date} through {report.end_date} · "
                   f"valid stock returns: {report.available_returns}/{lookback} · "
                   f"valid benchmark returns: {report.benchmark_returns}/{lookback}.")
    chosen = risk.metrics[:6]
    for start in range(0, len(chosen), 3):
        for col, metric in zip(st.columns(3), chosen[start:start + 3]):
            col.metric(RISK_METRICS[metric], _formatted(report.values[metric]))
    rows = []
    for n in risk.lookbacks:
        r = reports[n]
        rows.append({
            "Daily returns in window": n, "Start": r.start_date, "End": r.end_date,
            **{RISK_METRICS[m]: r.values[m] for m in risk.metrics},
            "Stock returns available": r.available_returns,
            "Benchmark returns available": r.benchmark_returns, "Status": r.status,
        })
    st.markdown("#### Compare lookback periods")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.download_button("Download this stock's risk metrics", pd.DataFrame(rows).to_csv(index=False),
                        file_name=f"{ticker}_{run.screen_date}_risk.csv", mime="text/csv",
                        key=widget_prefix + "_download")
    if report.notes:
        with st.expander("Metric availability and calculation notes", expanded=True):
            for note in report.notes:
                st.write(note)
    with st.expander("How to read the metrics"):
        st.write("Sharpe compares mean daily excess return with sample daily volatility. The annualized value "
                 "is the daily Sharpe multiplied by the square root of sessions per year. Sortino uses mean "
                 "return above its selected target and downside deviation across all days in the window.")
        st.write("Beta is the slope of daily stock excess returns against benchmark excess returns. Alpha is "
                 "that regression's daily intercept, multiplied by sessions per year for the annualized display. "
                 "It is an arithmetic annualization, not CAGR or the difference in cumulative returns.")
        st.write("Maximum drawdown is the largest peak-to-trough price loss within this window, displayed as "
                 "a positive magnitude. Calmar divides CAGR by that magnitude. Information ratio compares "
                 "mean daily active return with tracking-error volatility. All zero-denominator ratios are unavailable.")
        st.write("Return-regression R-squared describes the benchmark fit; MA-rule R-squared describes a "
                 "moving-average trendline. They answer different questions. Annualization assumes comparable "
                 "daily observations and does not correct for serial correlation.")
    if not st.toggle("Show performance charts", value=False, key=widget_prefix + "_charts"):
        return
    prices = run.frames[ticker].adj_close
    benchmark = run.benchmark.get("adj_close")
    options = ["sharpe", "sortino", "beta", "alpha_ann_pct", "volatility_ann_pct"]
    metric = st.selectbox("Rolling metric", options, format_func=lambda m: RISK_METRICS[m],
                          key=widget_prefix + "_rolling_metric")
    rolling = rolling_metrics(prices, benchmark, lookback, risk)
    series = rolling[metric]
    finite = int(series.notna().sum())
    if not finite:
        st.info("No complete rolling windows are available for this metric.")
    else:
        fig = go.Figure(go.Scatter(x=series.index, y=series, mode="lines" if finite > 1 else "lines+markers",
                                  connectgaps=False,
                                  name=f"{ticker}: {lookback}-return window", line={"color": "#0D9488"}))
        if metric != "volatility_ann_pct":
            fig.add_hline(y=0, line_color="#94A3B8", line_dash="dot")
        fig.update_layout(title=f"Rolling {RISK_METRICS[metric]}", template="plotly_white",
                          yaxis_title=RISK_METRICS[metric], height=420, hovermode="x unified")
        st.plotly_chart(fig, width="stretch", key=widget_prefix + "_rolling_plot")
        if finite < 2:
            st.caption("Only one complete rolling evaluation is available. Select a longer displayed history "
                       "and run again to see a longer rolling series.")
    if report.available_returns != lookback or not math.isfinite(report.values["total_return_pct"]):
        st.info("The selected stock needs a complete window for growth and drawdown charts.")
        return
    sample = numeric_prices(prices).iloc[-(lookback + 1):]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        subplot_titles=("Growth of 100 over the selected window", "Stock drawdown (%)"))
    fig.add_trace(go.Scatter(x=sample.index, y=100 * sample / sample.iloc[0], name=ticker,
                             line={"color": "#0D9488"}, connectgaps=False), row=1, col=1)
    if benchmark is not None and report.benchmark_returns == lookback:
        b = numeric_prices(benchmark).reindex(sample.index)
        fig.add_trace(go.Scatter(x=b.index, y=100 * b / b.iloc[0], name=risk.benchmark,
                                 line={"color": "#7C3AED"}, connectgaps=False), row=1, col=1)
    drawdown = 100 * (sample / sample.cummax() - 1)
    fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown, fill="tozeroy", name="Drawdown",
                             line={"color": "#E24B70"}, connectgaps=False), row=2, col=1)
    fig.update_layout(template="plotly_white", height=610, hovermode="x unified",
                      legend={"orientation": "h"})
    st.plotly_chart(fig, width="stretch", key=widget_prefix + "_growth_plot")
