"""Interactive Plotly charts exposing exactly the observations used by a selected rule."""
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .metrics import InsufficientData, regression
from .models import REGRESSION_METHODS, RELATION_METHODS, Rule, ScreenConfig
from .rules import RuleResult, window_description

COLORS = ["#0D9488", "#F59E0B", "#7C3AED", "#E24B70", "#2563EB", "#B45309", "#0891B2", "#65A30D"]


def price_chart(frame: pd.DataFrame, ticker: str, config: ScreenConfig, display_start: date,
                rule: Rule | None = None, evaluation: RuleResult | None = None,
                chart_mas: list[str] | None = None, height: int = 560) -> go.Figure:
    fig = go.Figure()
    if frame.empty:
        fig.add_annotation(text="No history available", showarrow=False)
        return fig
    start = pd.Timestamp(display_start)
    if evaluation and evaluation.window_start is not None:
        start = min(start, evaluation.window_start)
    visible = frame.loc[frame.index >= start]
    source_label = "Adjusted close" if config.price_source == "adj_close" else "Close (unadjusted)"
    fig.add_trace(go.Scatter(
        x=visible.index, y=visible["PRICE"], name=source_label,
        line={"color": "#334155", "width": 1.7}, connectgaps=False,
        hovertemplate="%{x|%b %d, %Y}<br>%{y:.4f}<extra>%{fullData.name}</extra>",
    ))
    selected = chart_mas if chart_mas is not None else [m.key for m in config.moving_averages if m.enabled and m.show]
    for i, ma in enumerate(m for m in config.moving_averages if m.enabled):
        if ma.key not in frame:
            continue
        fig.add_trace(go.Scatter(
            x=visible.index, y=visible[ma.key], name=ma.key,
            line={"color": COLORS[i] if i < len(COLORS) else f"hsl({i * 137.508 % 360:.2f},65%,42%)",
                  "width": 2},
            visible=True if ma.key in selected else "legendonly", connectgaps=False,
            hovertemplate="%{x|%b %d, %Y}<br>%{y:.4f}<extra>%{fullData.name}</extra>",
        ))
    if rule and evaluation and evaluation.window_start is not None:
        segment = frame.loc[evaluation.window_start:evaluation.window_end]
        y = segment[rule.ma]
        passed = evaluation.valid and evaluation.passed
        color = "#059669" if passed else "#DC2626"
        fig.add_vrect(x0=segment.index[0], x1=segment.index[-1],
                      fillcolor=color, opacity=0.07, line_width=0, layer="below")
        fig.add_trace(go.Scatter(x=segment.index, y=y, name=f"Analyzed: {rule.ma}",
                                 mode="lines+markers", line={"color": color, "width": 4},
                                 marker={"size": 5}, connectgaps=False))
        if rule.method in RELATION_METHODS and rule.other in segment:
            fig.add_trace(go.Scatter(x=segment.index, y=segment[rule.other], name=f"Compared: {rule.other}",
                                     line={"color": "#EA580C", "width": 3, "dash": "dot"}))
        if rule.method in REGRESSION_METHODS:
            n = rule.lookback
            windows = [(segment.iloc[-n:], "Current fitted trend", "#0F172A")]
            if rule.method == "accel_slope":
                windows.append((segment.iloc[:n], "Previous fitted trend", "#EA580C"))
            elif rule.method == "turn_up":
                stop = len(segment) - rule.reversal_lag
                windows.append((segment.iloc[stop-n:stop], "Previous fitted trend", "#EA580C"))
            for part, label, line_color in windows:
                try:
                    fit = regression(part[rule.ma])
                    fitted = fit.intercept + fit.slope * np.arange(len(part))
                    fig.add_trace(go.Scatter(
                        x=part.index, y=fitted, name=label, line={"color": line_color, "width": 3, "dash": "dash"},
                        hovertemplate="%{y:.5f}<extra>" + label + "</extra>",
                    ))
                except InsufficientData:
                    pass
        else:
            change = y.diff().iloc[1:]
            if not change.empty:
                fig.add_trace(go.Scatter(
                    x=change.index, y=y.iloc[1:], name="Daily transitions", mode="markers",
                    marker={"color": np.where(change > 0, "#059669", np.where(change < 0, "#DC2626", "#64748B")),
                            "symbol": "circle", "size": 8, "line": {"width": 1, "color": "white"}},
                    customdata=change.to_numpy(),
                    hovertemplate="MA: %{y:.5f}<br>Daily change: %{customdata:.6f}<extra></extra>",
                ))
            fig.add_trace(go.Scatter(x=[y.index[0], y.index[-1]], y=[y.iloc[0], y.iloc[-1]],
                                     mode="markers", name="Start / end",
                                     marker={"size": 12, "symbol": "diamond", "color": color}))
        text = f"{rule.name} · {'PASS' if passed else 'FAIL' if evaluation.valid else 'UNAVAILABLE'}"
        if evaluation.valid:
            m = evaluation.metrics
            text += f" · change {m.get('pct_change', float('nan')):.3f}%"
            if "slope" in m:
                text += (f" · slope {m['slope']:.5f}"
                         f" · normalized {m['normalized_slope']:.5f}%/session · R² {m['r2']:.3f}")
            if height < 450:
                text = f"{rule.ma} · {'PASS' if passed else 'FAIL'}"
                if "normalized_slope" in m:
                    text += f" · {m['normalized_slope']:.4f}%/session"
        fig.add_annotation(text=text, x=0, y=1.13, xref="paper", yref="paper",
                           showarrow=False, xanchor="left", font={"size": 11, "color": color})
    fig.update_layout(
        title={"text": ticker, "font": {"size": 19}}, template="plotly_white", height=height,
        margin={"l": 20, "r": 20, "t": 88, "b": 15}, hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF",
        legend={"orientation": "h", "y": -0.18},
        yaxis={"title": source_label, "fixedrange": False},
        xaxis={
            "rangeslider": {"visible": False},
            "rangeselector": {"buttons": [
                {"count": 1, "label": "1m", "step": "month", "stepmode": "backward"},
                {"count": 3, "label": "3m", "step": "month", "stepmode": "backward"},
                {"count": 6, "label": "6m", "step": "month", "stepmode": "backward"},
                {"step": "all", "label": "All"},
            ]},
        }, uirevision=f"{ticker}-{rule.id if rule else 'overview'}-{frame.index[-1]}",
    )
    return fig


def information_panel(rule: Rule, evaluation: RuleResult) -> pd.DataFrame:
    m = evaluation.metrics
    pairs = [
        ("Moving average / series", rule.ma), ("Rule", rule.name),
        ("Window definition", window_description(rule)),
        ("Analyzed start", str(evaluation.window_start.date()) if evaluation.window_start is not None else "—"),
        ("Analyzed end", str(evaluation.window_end.date()) if evaluation.window_end is not None else "—"),
        ("Start MA value", m.get("start")), ("End MA value", m.get("end")),
        ("MA change (%)", m.get("pct_change")), ("Raw slope / session", m.get("slope")),
        ("Normalized slope (% / session)", m.get("normalized_slope")), ("R-squared", m.get("r2")),
        ("Positive transitions", m.get("positive_count")), ("Downward transitions", m.get("negative_count")),
        ("Flat transitions", m.get("flat_count")), ("Positive transitions (%)", m.get("positive_pct")),
        ("Maximum MA drawdown (%)", m.get("max_drawdown_pct")), ("Longest rising streak", m.get("longest_streak")),
        ("Previous normalized slope (% / session)", m.get("previous_normalized_slope")),
        ("Current normalized slope (% / session)", m.get("current_normalized_slope")),
        ("Previous change (%)", m.get("previous_change")), ("Current change (%)", m.get("current_change")),
        ("Slope acceleration (pp / session)", m.get("accel_slope")),
        ("Percentage acceleration (pp)", m.get("accel_pct")),
        ("Sessions since crossover", m.get("sessions_since_crossover")),
        ("Compared latest MA value", m.get("other_end")),
        ("Compared starting MA value", m.get("other_start")),
        ("Measured rule value", evaluation.value),
        ("Final result", "PASS" if evaluation.passed else "FAIL" if evaluation.valid else "UNAVAILABLE"),
        ("Evaluation detail", evaluation.reason),
    ]
    def formatted(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            return "undefined" if not np.isfinite(v) else f"{v:.8g}"
        return str(v)
    return pd.DataFrame({"Metric": [p[0] for p in pairs], "Value": [formatted(p[1]) for p in pairs]})
