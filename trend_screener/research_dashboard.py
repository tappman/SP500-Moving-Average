"""Button-driven screen history, portfolio diagnostics and historical research lab."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from io import BytesIO
import json
from pathlib import Path
import zipfile

import pandas as pd
import plotly.express as px
import streamlit as st

from .appearance import empty_state, show_figure, style_figure
from .cache import PriceCache
from .calendar import history_start, latest_completed_session
from .demo import DemoProvider
from .history import HistoryStore
from .membership import MembershipHistory
from .portfolio import analyze_portfolio
from .providers import AliasedProvider, YFinanceProvider
from .risk import RISK_METRICS, RiskSettings, sharpe_help, sharpe_label
from .robustness import (
    engine_slice, evaluate_frozen_holdout, export_frozen_bundle, finite_json, freeze_study,
    import_frozen_bundle, recorded_backtest, robustness_trials,
)
from .studies import (
    RANKINGS, BacktestSettings, StudyEngine, cohort_study,
)
from .universe import provider_symbol


def archive(tables, metadata):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name, table in tables.items():
            out.writestr(name + ".csv", table.to_csv(index=True))
        out.writestr("methodology.json", json.dumps(finite_json(metadata), indent=2, default=str, allow_nan=False))
    return buffer.getvalue()


def research_figure(figure, *, key):
    show_figure(style_figure(figure), key=key)


def load_membership(home):
    return MembershipHistory.load(Path(home) / "research")


def membership_panel(home):
    st.subheader("Historical membership data")
    st.caption("Supply a complete interval history, including removed companies. No historical constituent "
               "feed is bundled. Coverage and source are your declarations, not independently verified.")
    template = ("ticker,start_date,end_date,company,sector,industry\n"
                "EXAMPLE_OLD,2020-01-01,2024-01-10,Fictional removed company,Industrials,Example\n"
                "EXAMPLE_NEW,2024-01-10,,Fictional added company,Technology,Example\n")
    st.download_button("Download synthetic membership CSV template", template,
                       file_name="SYNTHETIC_membership_template.csv", mime="text/csv", key="membership_template")
    st.info("Dates use YYYY-MM-DD. start_date is included; end_date is excluded. A blank end means still active. "
            "For a sector change, close the old interval and start a new one on the same effective date.")
    uploaded = st.file_uploader("Historical membership intervals (CSV)", type="csv", key="membership_upload")
    cols = st.columns(2)
    start = cols[0].date_input("Declared coverage start", value=date(2000, 1, 1), key="membership_start")
    end = cols[1].date_input("Declared coverage end", value=latest_completed_session(), key="membership_end")
    source = st.text_input("Membership source / provenance", placeholder="Dataset name, version and source",
                           key="membership_source")
    if st.button("Validate and save membership data", key="membership_save", disabled=uploaded is None):
        try:
            membership = MembershipHistory.from_csv(uploaded.getvalue().decode("utf-8-sig"), start, end, source)
            membership.save(Path(home) / "research")
            st.success(f"Saved {len(membership.frame)} membership intervals. Select Historical membership CSV "
                       "in Data settings or in the study universe below.")
        except (ValueError, OSError, UnicodeError) as exc:
            st.error(str(exc))
    try:
        membership = load_membership(home)
        if membership:
            st.caption(f"Saved source: {membership.source} · declared coverage {membership.coverage_start} to "
                       f"{membership.coverage_end} · digest {membership.digest[:12]}")
            st.dataframe(membership.frame, hide_index=True, width="stretch")
            st.download_button("Download saved membership intervals", membership.to_csv(),
                               file_name="membership_intervals.csv", mime="text/csv", key="membership_export")
            st.warning("Membership support alone does not remove bias: incomplete intervals, unavailable delisted "
                       "prices, ticker aliases and retrospectively adjusted prices still limit the study.")
    except (ValueError, OSError, KeyError) as exc:
        st.error(f"Saved membership data could not be read: {exc}")


def history_panel(home):
    st.subheader("Saved screen history")
    st.caption("Each successful Run Screen saves a local snapshot automatically. Comparisons use the same "
               "rule/universe definition and a strictly earlier screening date. No background scheduling is enabled.")
    store = HistoryStore(Path(home) / "research")
    count = int(st.number_input("Saved snapshots to list", min_value=1, max_value=20000, value=200,
                                 key="history_limit"))
    index = store.list_screens(count)
    if index.empty:
        empty_state("Track how your matches change", "Run a screen to save the first snapshot. "
                    "Run the same definition on a later date to see new and dropped qualifiers.")
        return
    labels = {r.id: f"{r.screen_date} · saved {r.created_at[:19]} UTC · {r.id[:6]}" for r in index.itertuples()}
    identifier = st.selectbox("Saved screen", index.id.tolist(), format_func=labels.get, key="history_snapshot")
    with st.expander("Delete saved screens"):
        selected = st.multiselect("Snapshots to delete", index.id.tolist(), default=[identifier],
                                  format_func=labels.get, key="history_delete_ids")
        confirmed = st.checkbox("Permanently delete the selected snapshots", key="history_delete_confirm",
                                help="Removes saved results and their comparison dates. Cached prices, presets, "
                                     "the applied screen and frozen research remain available. Download snapshots first if needed.")
        if st.button("Delete selected snapshots", key="history_delete", disabled=not selected or not confirmed):
            store.delete_screens(selected)
            for key in ("history_snapshot", "history_delete_ids", "history_delete_confirm"):
                st.session_state.pop(key, None)
            st.rerun()
    current = store.screen(identifier)
    old, changes = store.compare(identifier)
    st.caption(f"Definition {current['definition'][:12]} · {len(current['table'])} requested stocks")
    if old is None:
        st.info("This definition has no saved earlier date yet. Same-day reruns do not count as another session.")
    else:
        st.caption(f"Compared with {old['screen_date']}. Streaks count consecutive saved distinct dates, "
                   "which may skip trading sessions. A data failure is reported as unavailable.")
        cols = st.columns(4)
        for col, change in zip(cols, ("Newly qualifying", "Still qualifying", "Stopped qualifying", "Now unavailable")):
            col.metric(change, int(changes.change.eq(change).sum()))
        st.dataframe(changes, hide_index=True, width="stretch")
        st.download_button("Download screen changes", changes.to_csv(index=False),
                           file_name=f"screen_changes_{current['screen_date']}.csv", mime="text/csv")
    with st.expander("Snapshot results and configuration"):
        st.dataframe(current["table"], hide_index=True, width="stretch")
        st.download_button("Download saved snapshot", archive({"results": current["table"], "changes": changes},
                                                              {"config": current["config"], "created_at": current["created_at"]}),
                           file_name=f"screen_snapshot_{current['screen_date']}.zip", mime="application/zip")


def portfolio_panel(run, home):
    st.subheader("Portfolio concentration & diversification")
    st.caption("Build a hypothetical basket from this screen. Metrics use complete aligned adjusted closes "
               "and daily rebalancing to target weights, with no transaction costs. Unallocated weight earns "
               "the chosen risk-free assumption. This basket is separate from the trading backtester.")
    prefix = f"portfolio_{st.session_state.run_id}"
    population = st.radio("Basket candidates", ["Matching stocks", "All screened stocks"],
                          horizontal=True, key=prefix + "_population")
    table = run.passing if population == "Matching stocks" else run.table
    if table.empty:
        st.info("No matching stocks. Select all screened stocks or change the screen.")
        return
    selected = st.multiselect("Basket stocks", table.ticker.tolist(), default=table.ticker.head(10).tolist(),
                              key=prefix + "_tickers")
    mode = st.radio("Weighting", ["Equal weights", "Custom weights"], horizontal=True, key=prefix + "_mode")
    if not selected:
        return
    weights = {t: 1 / len(selected) for t in selected}
    if mode == "Custom weights":
        base = pd.DataFrame({"ticker": selected, "weight_pct": [100 / len(selected)] * len(selected)})
        edited = st.data_editor(base, hide_index=True, disabled=["ticker"], width="stretch",
                                column_config={"weight_pct": st.column_config.NumberColumn("Weight (%)", min_value=0.0,
                                                                                          max_value=100.0, required=True)},
                                key=prefix + "_weights_" + "_".join(selected))
        weights = dict(zip(edited.ticker, edited.weight_pct / 100))
    lookback = int(st.number_input("Portfolio return window (sessions)", min_value=2, value=63, step=1,
                                    key=prefix + "_window"))
    signature = (run.screen_date, tuple(weights.items()), lookback, run.config.risk.signature())
    if st.button("Calculate basket risk", type="primary", key=prefix + "_calculate"):
        try:
            report = analyze_portfolio(run.frames, weights, run.table, run.screen_date, lookback,
                                       run.config.risk, run.benchmark.get("adj_close"))
            st.session_state[prefix + "_report"] = (signature, report)
        except ValueError as exc:
            st.error(str(exc))
            st.caption("For a longer window, increase displayed history or a risk lookback in Build screen, then Run Screen.")
    stored = st.session_state.get(prefix + "_report")
    if not stored:
        return
    if stored[0] != signature:
        st.info("Basket settings changed. Calculate again to update the diagnostics.")
        return
    report = stored[1]
    cols = st.columns(4)
    for col, key, label in zip(cols, ("largest_position_pct", "effective_stock_holdings", "cash_weight_pct", "diversification_ratio"),
                                ("Largest position (%)", "Effective stock holdings", "Cash (%)", "Diversification ratio")):
        value = report.concentration[key]
        col.metric(label, f"{value:.2f}" if pd.notna(value) else "Undefined")
    st.caption("Effective holdings and HHI normalize invested stock weights to 100%; cash is shown separately. "
               "Variance contributions can be negative for hedging positions and are undefined for zero variance.")
    left, right = st.columns(2)
    with left:
        st.dataframe(report.sectors, hide_index=True, width="stretch")
    with right:
        st.subheader(sharpe_label(lookback, run.config.risk),
                     help=sharpe_help(lookback, run.config.risk, report=report.risk))
        st.dataframe(pd.DataFrame([{"Metric": RISK_METRICS[m], "Value": v} for m, v in report.risk.values.items()]),
                     hide_index=True, width="stretch", height=260)
    st.dataframe(report.weights, hide_index=True, width="stretch")
    if report.risk.notes:
        st.caption(" · ".join(report.risk.notes))
    shown = report.correlations.iloc[:40, :40]
    if len(shown) > 1:
        research_figure(px.imshow(shown, zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                              title="Stock return correlations · common dates"), key=prefix + "_correlation")
        if len(report.correlations) > 40:
            st.caption("Heatmap shows the first 40 stocks. The export contains the complete matrix.")
    research_figure(px.line(report.equity.drop(columns="drawdown_pct"), title="Hypothetical basket · growth of 1"),
                key=prefix + "_equity")
    st.download_button("Download basket analysis", archive({"weights": report.weights, "sectors": report.sectors,
                                                          "correlations": report.correlations, "equity": report.equity},
                                                         {"concentration": report.concentration, "risk": report.risk.values,
                                                          "screen_date": str(run.screen_date), "lookback": lookback,
                                                          "screen_config": run.config.to_dict(),
                                                          "risk_settings": asdict(run.config.risk),
                                                          "method": "Daily target-weight rebalancing; no costs"}),
                       file_name="portfolio_analysis.zip", mime="application/zip", key=prefix + "_download")


def backtest_controls(prefix, benchmark):
    cols = st.columns(3)
    initial = cols[0].number_input("Initial capital", min_value=1.0, value=100000.0, key=prefix + "_capital")
    maximum = cols[1].number_input("Maximum positions", min_value=1, value=10, key=prefix + "_max")
    hold = cols[2].number_input("Holding period (full sessions)", min_value=1, value=20, key=prefix + "_hold")
    cols = st.columns(3)
    review = cols[0].number_input("Review every N sessions", min_value=1, value=5, key=prefix + "_review")
    fee = cols[1].number_input("Commission per side (bps)", min_value=0.0, max_value=9999.0, value=5.0, key=prefix + "_fee")
    slip = cols[2].number_input("Slippage per side (bps)", min_value=0.0, max_value=9999.0, value=5.0, key=prefix + "_slip")
    ranking = st.selectbox("Entry ranking", list(RANKINGS), format_func=RANKINGS.get, key=prefix + "_rank")
    exit_fail = st.checkbox("Exit next open if a scheduled review no longer qualifies", value=True, key=prefix + "_fail")
    cash_rate = st.number_input("Idle cash annual yield (%)", min_value=-99.9, value=0.0, key=prefix + "_cash")
    return BacktestSettings(initial_cash=initial, max_positions=int(maximum), holding_sessions=int(hold),
                            review_every=int(review), ranking=ranking, commission_bps=fee, slippage_bps=slip,
                            exit_on_fail=exit_fail, cash_rate_pct=cash_rate, benchmark=benchmark)


def display_backtest(result, identifier, prefix):
    st.caption(f"Recorded experiment {identifier[:12]} · {result.equity.index[0].date()} to "
               f"{result.equity.index[-1].date()} · {len(result.trades)} closed trades")
    values = result.report.values
    cols = st.columns(4)
    for col, metric in zip(cols, ("total_return_pct", "cagr_pct", "sharpe", "max_drawdown_pct")):
        value = values[metric]
        settings = RiskSettings(**result.provenance.get("risk_settings", {}))
        col.metric(sharpe_label(result.report.requested_returns, settings) if metric == "sharpe" else RISK_METRICS[metric],
                   f"{value:.2f}" if pd.notna(value) else "Undefined",
                   help=sharpe_help(result.report.requested_returns, settings, report=result.report) if metric == "sharpe" else None)
    research_figure(px.line(result.equity[["equity", "benchmark"]], title="Portfolio and benchmark · after assumed costs"),
                key=prefix + "_equity")
    research_figure(px.area(result.equity[["drawdown_pct"]], title="Portfolio drawdown (%)"), key=prefix + "_drawdown")
    st.dataframe(result.trades, hide_index=True, width="stretch")
    with st.expander("Risk statistics, orders and data coverage"):
        st.json(finite_json(result.summary()))
        st.dataframe(result.orders, hide_index=True, width="stretch")
        st.dataframe(result.diagnostics, hide_index=True, width="stretch")
        for note in [*result.notes, *result.report.notes]:
            st.caption(note)
    st.download_button("Download backtest evidence", archive({"equity": result.equity, "trades": result.trades,
                                                           "orders": result.orders, "diagnostics": result.diagnostics},
                                                          {"experiment_id": identifier, "settings": asdict(result.settings),
                                                           "summary": result.summary(), "notes": result.notes,
                                                           "provenance": result.provenance}),
                       file_name=f"backtest_{identifier[:12]}.zip", mime="application/zip", key=prefix + "_export")


def load_study(run, applied, home, start, end, mode, benchmark, *, cache_only=None, refresh=False):
    membership = load_membership(home) if mode == "Historical membership CSV" else None
    if mode == "Historical membership CSV" and membership is None:
        raise ValueError("Upload historical membership intervals in Membership data first")
    if membership:
        universe = membership.universe(start, end)
    else:
        universe = run.table[[c for c in ("ticker", "company", "sector", "industry", "symbol") if c in run.table]].copy()
    if universe.empty:
        raise ValueError("The study universe is empty")
    config = run.config
    earliest = history_start(start, start, config.required_history() + 5)
    tickers = list(dict.fromkeys([*universe.ticker, benchmark]))
    provider = AliasedProvider(DemoProvider() if applied["demo"] else YFinanceProvider(),
                               config.data_settings.get("ticker_aliases", {}))
    progress = st.progress(0.0, text="Checking saved study prices…")
    try:
        batch = PriceCache(Path(home) / "prices", provider).get_many(
            tickers, earliest, end, refresh_recent=False,
            cache_only=applied["cache_only"] if cache_only is None else cache_only,
            refresh_now=refresh, retry_missing=refresh,
            progress=lambda done, total: progress.progress(.8 * done / max(1, total), text=f"Downloading study prices: {done}/{total}"))
        progress.progress(.85, text="Preparing causal indicators…")
        engine = StudyEngine(batch.frames, universe, config, start, end, membership)
        return engine, batch
    finally:
        progress.empty()


RESEARCH_HELP = {
    "Single-date outcomes": "Start with one applied screen date and measure what happened afterward to its matches "
        "or all screened stocks. The 5/20/60-session returns use later adjusted closes. Example: a 5-session "
        "outcome compares the screen close with the close five trading sessions later. Later prices never "
        "enter that original screen. This describes a group at one date, not a trading strategy.",
    "Outcome comparison": "Repeat the applied rules at historical review dates, then compare qualifiers with "
        "valid nonqualifiers, sector controls and the benchmark. Entries use the next open; each horizon is "
        "measured in trading sessions and applies the chosen per-side cost. Sampling every 21 sessions means "
        "roughly monthly reviews. Overlapping stocks and holding periods are dependent; averaged cohort "
        "outcomes are not one portfolio's compounded return. Missing complete horizons stay unavailable.",
    "Portfolio backtest": "Simulate a long-only portfolio. Rules see prices through the review close; entries "
        "occur at the next open. Ranking chooses among qualifying stocks when slots are limited. Position "
        "limits, holding periods, review frequency, fees and slippage determine trades and cash. Existing "
        "positions drift; fixed-period exits and final liquidation use closes. Inspect trades, equity and "
        "drawdowns together. Daily bars cannot reproduce execution, taxes, liquidity or market impact.",
    "Robustness": "Check whether results survive small parameter changes and chronological training slices. "
        "Freeze rules and inputs before evaluating the later holdout. The ledger records attempts, including "
        "failures. Choosing the best of many trials can overfit; a user-declared holdout is not proof that "
        "those dates were never inspected. Frozen data preserves inputs, not the executing software.",
    "Membership data": "Supply dated constituent intervals to avoid applying today's list to every past date. "
        "Start dates are included and end dates excluded. Include removed companies and declare the source "
        "and coverage. The app cannot certify completeness or supply missing delisting prices. Fixed current "
        "constituents remain survivorship-biased.",
    "Saved holdouts": "Reopen frozen studies from their archived price bars, membership and rules without "
        "redownloading market data. Export a portable bundle as a backup or import it on another computer. "
        "Checksums detect damaged inputs. The executing app version can affect calculations; inputs alone "
        "do not freeze software. This archive is separate from ordinary screen-history snapshots.",
}


def research_views(home, run, forward_panel):
    outcomes, cohorts, simulation, robustness, membership_tab, saved_tab = st.tabs(
        ["Single-date outcomes", "Outcome comparison", "Portfolio backtest", "Robustness", "Membership data",
         "Saved holdouts"])
    for tab, (title, explanation) in zip(
            (outcomes, cohorts, simulation, robustness, membership_tab, saved_tab), RESEARCH_HELP.items()):
        with tab:
            st.subheader(title, help=explanation)
    with membership_tab:
        membership_panel(home)
    with saved_tab:
        saved_holdouts_panel(home)
    if run is None:
        for tab in (outcomes, cohorts, simulation, robustness):
            with tab:
                empty_state("Start with an applied screen", "Run a screen to define the rules for historical research. "
                            "Historical membership can be uploaded in Membership data now.")
    else:
        with outcomes:
            forward_panel(run)
    return cohorts, simulation, robustness


def research_lab(run, applied, home, forward_panel):
    st.subheader("Historical research lab")
    st.caption("Use the last applied screen definition. Each study records assumptions and separates "
               "historical signals from later outcomes. Synthetic mode remains clearly labeled.")
    if run is None:
        research_views(home, run, forward_panel)
        return
    # Shared controls sit above the study subviews and trigger no download until pressed.
    with st.expander("Study data · date range, universe and benchmark", expanded=True):
        cols = st.columns(2)
        end_default = run.screen_date
        start = cols[0].date_input("Study start", value=(pd.Timestamp(end_default) - pd.DateOffset(years=1)).date(),
                                   min_value=date(1970, 1, 1), max_value=latest_completed_session(), key="study_start")
        end = cols[1].date_input("Study end", value=end_default, min_value=date(1970, 1, 1),
                                 max_value=latest_completed_session(), key="study_end")
        modes = ["Applied universe (fixed)", "Historical membership CSV"]
        mode = st.selectbox("Study universe", modes, index=int(applied["universe_mode"] == "Historical membership CSV"),
                             key="study_universe")
        benchmark_text = st.text_input("Study benchmark ticker", value=run.config.risk.benchmark, key="study_benchmark")
        if mode == "Applied universe (fixed)":
            st.warning("This reuses the applied universe at every historical date. Current constituents create "
                       "survivorship bias; this is not historical index membership.")
        st.caption("Loading studies uses the same incremental cache as the screener. Holdings require complete "
                   "prices. Yahoo data is retrospectively adjusted and may lack delisted companies.")
        saved_only = st.checkbox("Use saved study prices only", value=applied["cache_only"],
                                 key="study_cache_only", help="Block all price downloads for this study, "
                                 "including missing warm-up dates. Incomplete histories remain unavailable.")
        load_col, update_col = st.columns(2)
        load_clicked = load_col.button("Load study data", type="primary", key="study_load",
                                      help="Check the shared price cache first; request missing ranges with "
                                           "a small overlap to detect revised adjustments. No routine refresh.")
        update_clicked = update_col.button("Update study prices", key="study_update", disabled=saved_only,
                                           help="Explicitly refresh recent prices, repair gaps and load the study. "
                                                "Revised adjustments can require a full-history refresh.")
        if load_clicked or update_clicked:
            try:
                benchmark = provider_symbol(benchmark_text)
                if start >= end:
                    raise ValueError("Choose a study start earlier than its end")
                engine, batch = load_study(run, applied, home, start, end, mode, benchmark,
                                           cache_only=saved_only, refresh=update_clicked)
                st.session_state.study = {"engine": engine, "batch": batch, "run_id": st.session_state.run_id,
                                          "benchmark": benchmark, "controls": (start, end, mode, benchmark_text),
                                          "demo": applied["demo"]}
                for key in ("cohort_result", "backtest_result", "robustness_result", "holdout_result", "training_result"):
                    st.session_state.pop(key, None)
                st.success(f"Loaded {len(engine.universe)} stocks and {len(engine.dates)} sessions.")
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
    cohorts, simulation, robustness = research_views(home, run, forward_panel)
    study = st.session_state.get("study")
    valid = (study is not None and study["run_id"] == st.session_state.run_id
             and study["controls"] == (start, end, mode, benchmark_text))
    if valid and mode == "Historical membership CSV":
        saved_membership = load_membership(home)
        valid = saved_membership is not None and saved_membership.digest == study["engine"].membership.digest
    if not valid:
        for tab in (cohorts, simulation, robustness):
            with tab:
                st.info("Choose a range in Study data above, then click Load study data to apply it.")
        return
    engine, benchmark = study["engine"], study["benchmark"]
    store = HistoryStore(Path(home) / "research")
    label = "SYNTHETIC STUDY" if study["demo"] else "HISTORICAL STUDY"
    st.caption(f"{label} · {engine.start} to {engine.end} · {len(engine.universe)} stocks · "
               f"prices {engine.fingerprint[:12]} · benchmark {benchmark}")
    st.caption(f"Membership: {engine.membership.source} · {engine.membership.digest[:12]}" if engine.membership
               else "Membership: fixed applied universe at every study date")
    batch = study["batch"]
    if batch.downloads:
        st.caption(f"Study price download requests: {len(batch.downloads)}. See exact ranges below.")
    else:
        st.caption("Used saved study prices. No price downloads were requested.")
    with st.expander("Study price download activity"):
        st.json(batch.downloads)
        for warning in batch.warnings:
            st.warning(warning)
    if study["batch"].errors:
        with st.expander("Study data issues"):
            st.json(study["batch"].errors)
    with cohorts:
        cohort_panel(engine, benchmark, run, store)
    with simulation:
        st.caption("Signals at a review's close → entries next open. Fractional shares; cash cap; vacancy-filling "
                   "reviews; existing holdings drift. Fixed-period exits occur at close; the study liquidates "
                   "remaining holdings at its final close. One bp is 0.01%.")
        settings = backtest_controls("sim", benchmark)
        signature = json.dumps(asdict(settings), sort_keys=True)
        if st.button("Run portfolio backtest", type="primary", key="sim_run"):
            progress = st.progress(0.0, text="Simulating portfolio…")
            try:
                identifier, result = recorded_backtest(store, "portfolio_backtest", engine, settings, run.config.risk,
                                                       progress=lambda done, total: progress.progress(done / total))
                st.session_state.backtest_result = (signature, identifier, result)
            except (ValueError, RuntimeError) as exc:
                st.session_state.pop("backtest_result", None)
                st.error(str(exc))
            finally:
                progress.empty()
        stored = st.session_state.get("backtest_result")
        if stored and stored[0] == signature:
            display_backtest(stored[2], stored[1], "sim_result")
        elif stored:
            st.info("Portfolio assumptions changed; run the backtest again.")
    with robustness:
        robustness_panel(engine, benchmark, run, store)


def cohort_panel(engine, benchmark, run, store):
    st.caption("Sample historical closes, then compare next-open holding-period outcomes for qualifiers, "
               "valid nonqualifiers, the benchmark and nonqualifiers in the same sector. These are cohort "
               "outcomes, not returns on one investable portfolio.")
    text = st.text_input("Holding horizons (sessions, comma-separated)", "5, 20, 60", key="cohort_horizons")
    every = int(st.number_input("Sample every N sessions", min_value=1, value=21, key="cohort_every"))
    cost = st.number_input("Combined friction per side (bps)", min_value=0.0, max_value=9999.0,
                            value=10.0, key="cohort_cost")
    signature = (text, every, cost)
    if st.button("Compare historical outcomes", type="primary", key="cohort_run"):
        progress = st.progress(0.0, text="Evaluating historical cohorts…")
        identifier = None
        try:
            horizons = [int(v) for v in text.split(",") if v.strip()]
            plan = {"config": run.config.to_dict(), "start": str(engine.start), "end": str(engine.end),
                    "horizons": horizons, "every": every, "cost_bps": cost, "benchmark": benchmark,
                    "data_fingerprint": engine.fingerprint,
                    "membership_digest": engine.membership.digest if engine.membership else None}
            identifier = store.record_experiment("cohort_comparison", plan)
            result = cohort_study(engine, horizons=horizons, every=every, benchmark=benchmark, cost_bps=cost,
                                   progress=lambda done, total: progress.progress(done / total))
            store.complete_experiment(identifier, finite_json({"status": "COMPLETED", "summary": result.summary.to_dict("records")}))
            st.session_state.cohort_result = (signature, identifier, result, plan)
        except (ValueError, RuntimeError) as exc:
            if identifier:
                store.complete_experiment(identifier, {"status": "ERROR", "error": str(exc)})
            st.session_state.pop("cohort_result", None)
            st.error(str(exc))
        finally:
            progress.empty()
    saved = st.session_state.get("cohort_result")
    if not saved:
        return
    if saved[0] != signature:
        st.info("Outcome assumptions changed; run the comparison again.")
        return
    result = saved[2]
    st.dataframe(result.summary, hide_index=True, width="stretch")
    st.caption("Mean comparisons give each sampled date equal weight when a comparison exists. Median and "
               "10th/90th percentiles describe individual observed stock outcomes. Overlapping dates and "
               "stocks are dependent; counts are not independent trials. Missing horizons remain unavailable.")
    if not result.observations.empty:
        plot = result.observations[result.observations.status.isin(["PASS", "FAIL"])].copy()
        research_figure(px.box(plot, x="horizon", y="return_pct", color="status", points=False,
                           labels={"horizon": "Holding sessions", "return_pct": "Net outcome (%)"},
                           title="Observed outcome distributions"), key="cohort_distribution")
    with st.expander("Every date and stock outcome"):
        st.dataframe(result.by_date, hide_index=True, width="stretch")
        st.dataframe(result.observations, hide_index=True, width="stretch")
    st.download_button("Download outcome comparison", archive({"summary": result.summary, "by_date": result.by_date,
                                                            "observations": result.observations}, saved[3]),
                       file_name=f"cohorts_{saved[1][:12]}.zip", mime="application/zip", key="cohort_export")


def robustness_panel(engine, benchmark, run, store):
    st.caption("Compare a fixed neighborhood and chronological slices. Declare a holdout before examining its "
               "result. Freezing saves the plan, prices and membership; it cannot prove you have never "
               "seen these historical dates. No optimizer selects the best test result.")
    split = st.date_input("Training ends / declared holdout starts after", value=engine.dates[int(len(engine.dates) * .65)].date(),
                           min_value=engine.start, max_value=engine.end, key="robust_split")
    settings = backtest_controls("robust", benchmark)
    active_mas = [m.key for m in engine.config.moving_averages if m.enabled]
    active_rules = [r for r in engine.config.rules if r.enabled]
    ma = st.selectbox("MA period to perturb (−1 / +1)", active_mas, key="robust_ma")
    rule_id = st.selectbox("Rule lookback to perturb (−1 / +1)", [r.id for r in active_rules],
                            format_func=lambda v: next(r.name for r in active_rules if r.id == v), key="robust_rule")
    signature = json.dumps({"split": str(split), "backtest": asdict(settings), "ma": ma, "rule": rule_id}, sort_keys=True)
    if st.button("Run training robustness checks", type="primary", key="robust_run"):
        progress = st.progress(0.0, text="Recording all fixed trials…")
        try:
            if not engine.start < split < engine.end:
                raise ValueError("Choose an interior training/holdout split")
            training = engine_slice(engine, engine.config, engine.start, split)
            result = robustness_trials(training, settings, ma, rule_id, store, risk=run.config.risk,
                                        progress=lambda done, total: progress.progress(done / total))
            st.session_state.robustness_result = (signature, result)
        except (ValueError, RuntimeError) as exc:
            st.session_state.pop("robustness_result", None)
            st.error(str(exc))
        finally:
            progress.empty()
    stored = st.session_state.get("robustness_result")
    if stored and stored[0] == signature:
        st.dataframe(stored[1], hide_index=True, width="stretch")
        st.caption("Only training dates are evaluated above. Chronological slices reset capital and liquidate "
                   "at their own boundaries, so their returns are separate experiments, not one compounded curve.")
        st.download_button("Download training robustness trials", stored[1].to_csv(index=False),
                           file_name="training_robustness.csv", mime="text/csv", key="robust_export")
    if st.button("Freeze this plan for holdout", key="robust_freeze"):
        try:
            identifier = freeze_study(store, run.config, settings, engine, split,
                                       {"source": run.config.data_settings.get("source"),
                                        "ticker_aliases": run.config.data_settings.get("ticker_aliases", {}),
                                        "membership_source": engine.membership.source if engine.membership else "Fixed applied universe"})
            st.session_state.frozen_choice = identifier
            st.session_state.holdout_choice = identifier
            st.success(f"Plan and inputs frozen as {identifier[:12]}. Reopen or export it from Saved holdouts, "
                       "including after an app restart.")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    ledger = store.list_experiments()
    frozen = ledger[ledger.kind.eq("frozen_holdout")] if len(ledger) else ledger
    if not frozen.empty:
        ids = frozen.id.tolist()
        preferred = st.session_state.get("frozen_choice")
        chosen = st.selectbox("Frozen holdout plan", ids, index=ids.index(preferred) if preferred in ids else 0,
                                format_func=lambda x: f"{x[:12]} · {frozen.set_index('id').loc[x, 'created_at'][:19]} UTC",
                                key="holdout_choice")
        plan = store.experiment(chosen)
        if plan["plan"].get("snapshot"):
            st.caption("Evaluation uses the saved input snapshot. The currently loaded study and later cache updates "
                       "do not replace those inputs.")
        with st.expander("Frozen assumptions"):
            st.json(plan)
        st.download_button("Download frozen plan", json.dumps(plan, indent=2),
                           file_name=f"frozen_plan_{chosen[:12]}.json", mime="application/json", key="holdout_plan_export")
        if st.button("Evaluate frozen holdout", key="holdout_run"):
            progress = st.progress(0.0, text="Evaluating frozen holdout…")
            try:
                identifier, result = evaluate_frozen_holdout(store, chosen, engine,
                                                            progress=lambda done, total: progress.progress(done / total))
                st.session_state.holdout_result = (chosen, identifier, result)
            except (ValueError, RuntimeError) as exc:
                st.session_state.pop("holdout_result", None)
                st.error(str(exc))
            finally:
                progress.empty()
        saved = st.session_state.get("holdout_result")
        if saved and saved[0] == chosen:
            st.warning("This is a recorded user-declared holdout. Repeated evaluation and prior manual exploration "
                       "can contaminate it; every completed evaluation remains in the ledger.")
            display_backtest(saved[2], saved[1], "holdout_result")
    with st.expander("Research experiment ledger · all trials"):
        ledger = store.list_experiments()
        st.dataframe(ledger, hide_index=True, width="stretch")
        st.download_button("Download experiment ledger", ledger.to_csv(index=False),
                           file_name="research_experiments.csv", mime="text/csv", key="ledger_export")


def saved_holdouts_panel(home):
    st.subheader("Saved holdouts")
    st.caption("Reopen frozen research without running a new screen or downloading prices. Portable bundles "
               "contain the frozen rules, simulation settings, price bars, universe and supplied membership.")
    store = HistoryStore(Path(home) / "research")
    with st.expander("Restore a frozen study bundle"):
        uploaded = st.file_uploader("Frozen study bundle (ZIP)", type="zip", key="saved_holdout_upload")
        if st.button("Import frozen study", disabled=uploaded is None, key="saved_holdout_import"):
            try:
                identifier = import_frozen_bundle(store, uploaded.getvalue())
                st.session_state.archived_holdout_choice = identifier
                st.session_state.pop("saved_holdout_result", None)
                st.success("Frozen study restored. Its saved inputs are ready to evaluate offline.")
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
    ledger = store.list_experiments()
    frozen = ledger[ledger.kind.eq("frozen_holdout")]
    if frozen.empty:
        empty_state("Your frozen research will appear here", "Load a study, open Robustness and freeze a plan. "
                    "You can also restore a previously exported frozen study bundle above.")
        return
    ids = frozen.id.tolist()
    chosen = st.selectbox("Saved holdout", ids, key="archived_holdout_choice",
                            format_func=lambda x: f"{x[:12]} · {frozen.set_index('id').loc[x, 'created_at'][:19]} UTC")
    record = store.experiment(chosen)
    plan, snapshot = record["plan"], record["plan"].get("snapshot")
    source = plan.get("metadata", {}).get("source") or plan["config"].get("data_settings", {}).get("source", "Unspecified source")
    st.caption(f"{source} · study {plan['start']} to {plan['end']} · training ends {plan['split']}")
    if snapshot:
        st.caption(f"Saved inputs: {snapshot['bytes'] / (1024 * 1024):.2f} MiB · captured {snapshot['created_at'][:19]} UTC")
    else:
        st.info("This older plan saved its settings without price bars. Load its original study in Robustness "
                "to evaluate it, or freeze a new plan with a saved snapshot.")
    with st.expander("Saved assumptions and provenance"):
        st.json(record)
    if st.button("Prepare frozen study download", disabled=not snapshot, key="saved_holdout_prepare"):
        try:
            st.session_state.saved_holdout_bundle = (chosen, export_frozen_bundle(store, chosen))
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    prepared = st.session_state.get("saved_holdout_bundle")
    if prepared and prepared[0] == chosen:
        st.download_button("Download frozen study bundle", prepared[1], file_name=f"frozen_study_{chosen[:12]}.zip",
                           mime="application/zip", key="saved_holdout_download")
    if st.button("Evaluate saved holdout", type="primary", disabled=not snapshot, key="saved_holdout_run"):
        progress = st.progress(0.0, text="Restoring saved inputs and evaluating…")
        try:
            identifier, result = evaluate_frozen_holdout(store, chosen,
                                                        progress=lambda done, total: progress.progress(done / total))
            st.session_state.saved_holdout_result = (chosen, identifier, result)
        except (ValueError, RuntimeError, OSError) as exc:
            st.session_state.pop("saved_holdout_result", None)
            st.error(str(exc))
        finally:
            progress.empty()
    saved = st.session_state.get("saved_holdout_result")
    if saved and saved[0] == chosen:
        st.warning("This remains a user-declared holdout. Saved inputs make it reproducible; they do not prove "
                   "the historical period was unseen or preserve an original vendor point-in-time vintage.")
        display_backtest(saved[2], saved[1], "saved_holdout_result")
