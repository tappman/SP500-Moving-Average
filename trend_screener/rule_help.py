"""Plain-language control descriptions; calculations remain in metrics/rules."""
from __future__ import annotations

import re

MA_TYPES = {"SMA": "SMA — Simple moving average", "EMA": "EMA — Exponential moving average"}

CONTROL_HELP = {
    "name": "A label to help you recognize this condition. Renaming it does not change the calculation.",
    "enabled": "Include this condition when screening. Untick to keep its settings but temporarily ignore it.",
    "duplicate": "Create an independent copy of this rule, including its current settings and group.",
    "remove": "Delete this rule from the draft. Click Run Screen to apply the changed set of conditions.",
    "ma": "Choose the moving-average line to analyze. Its number is the MA period; the trend lookback below is a separate window.",
    "method": "Choose the mathematical meaning of the trend: overall slope, uninterrupted increases, percentage rise, consistency, acceleration or a turn upward.",
    "group": "Place this rule inside an AND group (all conditions) or OR group (any condition). Parent groups combine the resulting decisions.",
    "use_r2": "Add a second requirement for how closely the analyzed MA follows a straight fitted line. A high R-squared alone does not imply an upward slope.",
    "r2": "A value from 0 to 1: 0.80 means the fitted straight line explains 80% of variation in the MA values. A flat MA has undefined R-squared and cannot pass this requirement.",
    "use_positive": "Also require enough daily MA changes to be strictly positive. Flat and falling changes both reduce the positive percentage.",
    "positive": "Enter 80 for 80%. For a 15-observation regression there are 14 transitions, so 80% requires at least 12 positive transitions. Acceleration/turning rules use their latest component window.",
    "lag": "Compare today's regression slope with the slope evaluated this many trading sessions earlier, using the same regression-window length. This is an exact earlier evaluation, not a search for any reversal inside that interval.",
    "confirmation": "Require the most recent consecutive slope evaluations, including today, all to exceed the minimum positive slope. 3 means today and the two preceding sessions. Must not exceed the reversal lag.",
    "allow_flat": "Tick to allow the earlier slope to be zero or negative. Unticked requires the earlier slope to be strictly negative.",
    "pos_current": "In addition to the acceleration comparison, require the latest percentage change or normalized slope to be greater than zero.",
    "pos_previous": "Also require the preceding percentage change or normalized slope to be greater than zero. Unticked allows acceleration from a flat or falling earlier trend.",
    "other": "The right-hand MA in this comparison. For example, SMA5 on the left and SMA20 on the right tests their relationship, using the selected adjusted/unadjusted price input.",
}

METHOD_HELP = {
    "normalized_slope": (
        "Fit a straight line through the selected MA observations. Divide its slope by the average MA value in that window and multiply by 100 to compare stocks at different price levels.",
        "Use > 0 for overall upward direction, or > 0.01 for more than 0.01% of the average MA value per trading session. Small daily dips are allowed.",
        "Percentage of the average MA value per session. 0.01 means 0.01% per session, not 1%.",
    ),
    "slope": (
        "Fit a straight line through the selected MA observations. Its raw slope measures how many price units the fitted line rises or falls per session.",
        "Use > 0 for an upward fitted line. A slope of 0.25 means a fitted rise of 0.25 price units per session. This is not adjusted for different stock price levels.",
        "Raw price units per session. Positive is upward overall; negative is downward overall.",
    ),
    "net_increase": (
        "Compare the final MA with the value X trading transitions earlier: 100 × (end / start − 1). The final value must also be strictly greater than the start, even if the threshold comparison would allow a decline.",
        "With 10 transitions and >= 1, an MA rising from 100 to 101 passes. It may dip between the endpoints.",
        "Percent change: 1 means 1%. An actual endpoint increase is required as well.",
    ),
    "pct_change": (
        "Measure the MA's endpoint percentage change over X trading transitions: 100 × (end / start − 1). Intermediate dips are allowed.",
        "Use >= 1 for at least a 1% rise, <= 2 for a maximum 2% change, or < 0 for a decline.",
        "Percent change: 1 means 1%; −1 means a 1% decline.",
    ),
    "strict": (
        "Check whether every one of the X daily MA transitions is strictly positive. One flat or falling transition makes the result false.",
        "Use == 1 with 5 transitions to require six MA observations rising without interruption. A positive regression slope alone would not guarantee this.",
        "Boolean target: 1 means true; 0 means false. Usually choose == 1.",
    ),
    "positive_count": (
        "Count how many of the last X daily MA transitions are strictly positive. Flat changes do not count as positive.",
        "Choose 10 transitions, >= and 8 to require a rise on at least 8 of the last 10 transitions.",
        "A count of transitions, from 0 to the chosen lookback. Use whole-number targets.",
    ),
    "positive_pct": (
        "Divide the number of strictly positive daily MA transitions by all X transitions, then multiply by 100. Flat and falling transitions remain in the denominator.",
        "Choose 10 transitions, >= and 80 for at least 8 positive transitions. This can be combined with a positive-slope rule.",
        "Percentage of transitions: 80 means 80%, not 0.80.",
    ),
    "r2": (
        "Measure how closely the MA observations follow their fitted straight regression line. R-squared ranges from 0 to 1 and measures linear consistency, not the direction of the line.",
        "Use >= 0.80 for a close linear fit. Add a positive-slope condition if the line must also rise. Flat lines have undefined R-squared.",
        "A fraction from 0 to 1. Enter 0.80 for an R-squared of 80%.",
    ),
    "negative_count": (
        "Count strictly downward daily MA transitions in the lookback. Flat transitions are neither downward nor upward.",
        "Use <= 2 over 10 transitions to permit at most two MA declines. This does not by itself require an overall rise.",
        "A count of downward transitions, from 0 to the lookback. Smaller values permit fewer dips.",
    ),
    "max_drawdown_pct": (
        "Find the largest percentage fall from an earlier running MA peak to a later MA value inside the window. This is the MA line's peak-to-trough decline, not the stock price's drawdown.",
        "Use <= 0.5 to allow no MA drawdown larger than 0.5% inside the window. Add a slope condition to require upward direction.",
        "Positive drawdown magnitude in percent: 0.5 means a maximum half-percent decline. Usually use <=.",
    ),
    "longest_streak": (
        "Find the longest uninterrupted sequence of strictly positive daily MA changes anywhere inside the selected window. A flat or falling change breaks the streak.",
        "Use >= 5 over 20 transitions to require at least one five-transition rising streak. That streak need not end today.",
        "A count of consecutive rising transitions, not observations.",
    ),
    "accel_pct": (
        "Compare two consecutive X-transition windows. Subtract the preceding MA percentage change from the most recent MA percentage change; the windows share their boundary observation.",
        "An earlier +0.5% followed by +1.5% gives acceleration of +1.0 percentage point. Use > 0 to require the recent change to be stronger.",
        "Percentage points: 1 means the recent percentage change exceeds the preceding change by one percentage point.",
    ),
    "accel_slope": (
        "Fit normalized slopes in two consecutive, non-overlapping X-observation windows. Subtract the preceding normalized slope from the most recent one.",
        "A slope rising from 0.01% to 0.03% per session gives +0.02 percentage points per session. Use > 0 for a stronger recent slope.",
        "Change in normalized slope, in percentage points per session. 0.02 means an increase of 0.02 percentage points per session.",
    ),
    "turn_up": (
        "Compare the normalized regression slope now with the slope evaluated at the selected earlier session. Require the earlier slope to be negative (or flat if allowed), and the latest confirmation slopes to exceed the minimum.",
        "With a 10-observation regression, lag 5 and confirmation 3: the slope five sessions ago must be declining/flat, while today and the two previous evaluations must exceed the minimum slope.",
        "Minimum normalized slope, in % per session. Every confirmation slope must be strictly above it. The Comparison control separately compares the turning-up result with 1.",
    ),
    "relative": (
        "Compare the latest left-hand price/MA with the right-hand MA: 100 × (left / right − 1). Positive means above; negative means below. Only the latest observation is used.",
        "SMA5 on the left, SMA20 on the right and > 0 means SMA5 > SMA20. PRICE > SMA20 is configured the same way.",
        "Percentage difference relative to the right-hand MA. Use > 0 for above or < 0 for below.",
    ),
    "cross_up": (
        "Look for any transition in the window where the left line was at or below the right MA and then moved strictly above it.",
        "Use == 1 and 5 transitions to find at least one bullish crossover in the last five transitions. A crossover need not have happened today.",
        "Boolean target: use == 1 to require a bullish crossover; 0 means none was detected.",
    ),
    "cross_down": (
        "Look for any transition in the window where the left line was at or above the right MA and then moved strictly below it.",
        "Use == 1 and 5 transitions to find at least one bearish crossover in the last five transitions.",
        "Boolean target: use == 1 to require a bearish crossover; 0 means none was detected.",
    ),
    "separation_change": (
        "Measure absolute percentage separation as abs(100 × (left / right − 1)). Subtract the starting separation from the final separation.",
        "Use > 0 for widening separation or < 0 for narrowing. Separation growing from 1% to 2% gives +1 percentage point, regardless of which line is above.",
        "Percentage-point change in absolute separation. This does not by itself require a bullish alignment.",
    ),
}

OPERATOR_HELP = {">": "greater than", ">=": "greater than or equal to", "<": "less than",
                 "<=": "less than or equal to", "==": "equal to", "!=": "not equal to"}


def series_label(value):
    if value == "PRICE":
        return "Price — selected adjusted/unadjusted input"
    match = re.fullmatch(r"(SMA|EMA)([1-9][0-9]*)", str(value))
    return f"{value} · {MA_TYPES[match[1]].split(' — ')[1]}" if match else str(value)


def lookback_help(method):
    if method == "relative":
        return "Latest observation only. No historical lookback is applied to a current above/below comparison."
    if method == "accel_pct":
        return "X is the number of transitions in EACH comparison window: 2X+1 MA observations in total."
    if method == "accel_slope":
        return "X is the number of observations in EACH regression: 2X total, with no overlap between the windows."
    if method == "turn_up":
        return "X observations in EACH slope evaluation, not X transitions. The lag and confirmation controls add the earlier history needed."
    if method in {"normalized_slope", "slope", "r2"}:
        return "Exactly X trading-day MA observations. 10 observations span 9 daily transitions; this is separate from the MA's own period."
    return "X daily trading transitions require X+1 MA observations. 10 transitions use 11 values; weekends and exchange holidays do not count."
