"""Plain-language control descriptions; calculations remain in metrics/rules."""
from __future__ import annotations

import re

from .models import METHODS

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

# Formula, numerical walkthrough and interpretation for the selected method's tooltip.
METHOD_DETAILS = {
    "normalized_slope": (
        "Number the MA observations 0, 1, …, X−1 and fit y = intercept + slope × session. "
        "The least-squares slope is sum((x−mean(x)) × (y−mean(y))) / sum((x−mean(x))²). "
        "Normalized slope = 100 × raw slope / mean(MA in this same window).",
        "If the fitted MA slope is +0.10 price units per session and the window's average MA is 100, "
        "the normalized slope is +0.10% per session. It passes > 0.05, but fails > 0.20. "
        "An MA averaging 200 with slope +0.20 has the same normalized slope.",
        "This measures the direction and steepness of the fitted MA line using every observation. "
        "It is not the stock's daily return or the percentage change between the MA endpoints. "
        "Temporary dips are allowed. Add minimum R-squared for a more linear fit, or a positive-transition "
        "requirement for fewer daily dips. A flat MA has slope zero, so it fails > 0.",
    ),
    "slope": (
        "Fit y = intercept + slope × session to all X MA observations using least squares. "
        "Slope = sum((x−mean(x)) × (y−mean(y))) / sum((x−mean(x))²), where x is the observation number.",
        "MA values 100, 101, 102, 103 have a fitted slope of +1 price unit per session. "
        "They pass > 0 or >= 1, but fail > 1. A slope of −0.25 means a fitted decline of 0.25 units per session.",
        "Raw slopes depend on the stock's price level. Use normalized slope to compare proportional "
        "steepness across differently priced stocks. Positive slope means an overall fitted rise, "
        "not a rise on every day, and can disagree with an endpoint-only change.",
    ),
    "net_increase": (
        "Take the MA today and X trading transitions earlier. Change = 100 × (today / earlier − 1). "
        "Apply your threshold comparison AND require today's MA to be strictly higher than the earlier MA.",
        "An MA starting at 100 and ending at 105 has a +5% change. With >= 2 it passes, "
        "even if some intermediate days fell. An unchanged MA fails even with >= 0.",
        "Only the endpoints determine the change; intervening values must exist but do not need to rise. "
        "This method always requires a real increase. To allow flat or negative endpoint changes, "
        "select Net percentage change instead. It does not fit a regression line.",
    ),
    "pct_change": (
        "Change = 100 × (final MA / MA X trading transitions earlier − 1). "
        "Compare that signed percentage directly with your threshold.",
        "100 to 103 gives +3%, which passes >= 2. 100 to 99 gives −1%, which passes < 0 "
        "but fails >= 0. Unlike Net increase, this method does not separately require a rise.",
        "This is an endpoint comparison, not a fitted slope or an every-day test. Intermediate dips "
        "are allowed. The comparison operator matters: <= 2 sets a ceiling on change; it does not "
        "mean the MA rose by at least 2%. Add a positive-slope or daily-consistency rule if needed.",
    ),
    "strict": (
        "Calculate each daily change MA[i] − MA[i−1] over the last X transitions. "
        "Return true (1) only when ALL X changes are greater than zero; otherwise return false (0).",
        "100, 101, 102, 103 passes == 1 over three transitions. "
        "100, 101, 100.5, 103 fails, despite its +3% endpoint gain. "
        "100, 101, 101, 103 also fails because one transition is flat.",
        "Use == 1 to require uninterrupted increases; == 0 finds windows that did not rise every day. "
        "A tiny positive change counts, so this alone does not require a large gain. "
        "Use Net percentage change as an additional condition if the size of the rise matters.",
    ),
    "positive_count": (
        "Count transitions with MA[i] > MA[i−1]. Every positive change counts once, regardless of size. "
        "Flat and negative transitions contribute zero to this count.",
        "If eight changes are positive, one is flat and one is negative, the count is 8. "
        "Over ten transitions, >= 8 passes; > 8 fails. A count cannot exceed the number of transitions.",
        "Frequent small rises can be outweighed by a few large declines. This method measures frequency, "
        "not the total gain or fitted direction. Add a positive slope or net-rise condition if you "
        "also require upward direction overall. Positive transitions (%) expresses the same idea as a percentage.",
    ),
    "positive_pct": (
        "Positive percentage = 100 × number of strictly positive MA changes / all X daily transitions. "
        "Flat transitions remain in the denominator and are not positive.",
        "Eight positive changes out of ten transitions gives 80%. Enter >= 80, not >= 0.80. "
        "With nine transitions, >= 80 requires at least eight rises because seven out of nine is only 77.78%.",
        "The percentage counts days, not how much the MA moved. A line can rise on most days and still "
        "fall overall if its few declines are large. Add a slope or endpoint-change condition when "
        "direction or magnitude also matters.",
    ),
    "r2": (
        "Fit a straight line with an intercept to the X MA observations. R² = 1 − "
        "sum((observed MA − fitted MA)²) / sum((observed MA − mean MA)²). "
        "It measures how much variation the fitted line explains.",
        "100, 101, 102, 103 has R² = 1, but so does 103, 102, 101, 100. "
        "Both pass >= 0.80 because both are perfectly straight. The second line is declining.",
        "High R² means a more consistent straight-line fit, not a positive trend or a return probability. "
        "Combine it with slope > 0 to require a smooth upward trend. A flat line has no variation, "
        "so its R² is undefined and this rule is unavailable rather than assigned zero or one.",
    ),
    "negative_count": (
        "Count transitions with MA[i] < MA[i−1]. Flat transitions do not count as negative, "
        "and the size of each decline does not affect the count.",
        "Two declines, three flat changes and five rises produce a downward count of 2 over ten transitions. "
        "The window passes <= 2, but fails < 2.",
        "A low downward count does not establish an upward trend: an entirely flat line has zero declines. "
        "Use a positive slope or net increase alongside this rule to require an actual rise. "
        "Maximum MA drawdown measures the size of pullbacks rather than their count.",
    ),
    "max_drawdown_pct": (
        "For each MA observation, find the highest MA reached earlier in this same window, including "
        "that observation. Decline = 100 × (1 − current MA / running peak). Return the largest decline.",
        "For 100, 102, 101, 103, the pullback from 102 to 101 is about 0.9804%. "
        "The maximum drawdown is therefore 0.9804%, even though the line ends at a new high. "
        "It passes <= 1 but fails <= 0.5.",
        "The value is a positive loss magnitude, and lower values allow smaller pullbacks. "
        "This measures the MA line, not the underlying stock price, and only peaks inside the "
        "selected window count. A flat line has zero drawdown, so add an upward-direction condition if needed.",
    ),
    "longest_streak": (
        "Read the X daily MA changes in order. Add one to the running streak for each positive change; "
        "reset it to zero after a flat or negative change. Return the largest streak seen anywhere in the window.",
        "For changes +, +, −, +, +, +, 0, the longest rising streak is 3 transitions. "
        "It passes >= 3 but fails >= 4. Its final flat day means the current ending streak is zero.",
        "This looks for the longest historical run within the window, not necessarily a run continuing "
        "today. Use Strictly increasing over the last X transitions when the uninterrupted rise must "
        "end on the screening date. A three-transition streak consumes four MA observations.",
    ),
    "accel_pct": (
        "Compute the MA percentage change over the most recent X transitions and over the preceding "
        "X transitions. Acceleration = recent change − preceding change, in percentage points. "
        "The two windows share their boundary MA value.",
        "A preceding +0.5% change followed by +1.5% gives +1.0 percentage point of acceleration. "
        "It passes > 0.5. This is a subtraction of rates, not a 200% relative-growth calculation.",
        "A change from −2% to −1% also has positive acceleration (+1 percentage point), while the MA "
        "is still falling in the recent window. Require current rate > 0 to exclude that case; require "
        "previous rate > 0 too if both periods must rise. This compares observed trends, not future prices.",
    ),
    "accel_slope": (
        "Fit a normalized regression slope to each of two consecutive X-observation MA windows. "
        "Each slope is 100 × raw slope / its OWN window's average MA. "
        "Acceleration = recent normalized slope − preceding normalized slope.",
        "A preceding slope of +0.01% per session followed by +0.03% per session gives "
        "+0.02 percentage points per session. With > 0.01 it passes. The windows do not share an observation.",
        "A slope becoming less negative also gives positive acceleration. The current/previous rate "
        "checkboxes separately require those slopes to be positive. Normalizing each window permits "
        "comparison across price levels. A stronger recent slope is a historical measurement, not a forecast.",
    ),
    "turn_up": (
        "Fit an X-observation normalized slope today and at the evaluation L sessions earlier. "
        "The earlier slope must be negative, or zero if flat is allowed. Then fit each of the most "
        "recent C consecutive slope evaluations and require ALL to be strictly above the minimum slope.",
        "With X=10, L=5, C=3 and minimum 0.01% per session: a slope of −0.02% five sessions ago "
        "and latest evaluation slopes +0.02%, +0.03%, +0.04% passes == 1. "
        "One confirmation slope equal to 0.01% would fail because the minimum is strict.",
        "Confirmation counts rolling regression evaluations, not consecutive MA increases. "
        "The comparison uses the final true/false result against 1; the numeric threshold sets the "
        "minimum normalized slope, not a boolean target. The earlier evaluation is exactly L sessions "
        "ago, rather than a search for any reversal inside that interval. C must not exceed L.",
    ),
    "relative": (
        "At the screening session, calculate 100 × (left series / right-hand MA − 1). "
        "The left series can be price or another MA. Only one observation is used.",
        "If SMA5 is 102 and SMA20 is 100, the difference is +2%. It passes > 0 and >= 2. "
        "If the left series is 99, the difference is −1%, which passes < 0.",
        "This tests which line is above the other and by how much. It does not require either line "
        "to slope upward or a crossover to have occurred recently. Add separate trend or crossover "
        "conditions for those requirements. The historical lookback control is unused and disabled.",
    ),
    "cross_up": (
        "Compare the left series with the right MA at each pair of consecutive observations. "
        "A bullish crossover occurs when left was at/below right and then becomes strictly above. "
        "Return true (1) if ANY such event exists in the last X transitions.",
        "Left-minus-right differences −1, +1, −0.5 contain a bullish crossover on the first transition. "
        "The rule passes == 1 over those two transitions, even though the left line finishes below again.",
        "This detects a recent event, not the current alignment, an uninterrupted rise, or a minimum "
        "slope. Add left > right as a separate relationship if it must still be above today. "
        "Ending exactly equal does not count as crossing above; the new difference must be positive.",
    ),
    "cross_down": (
        "Compare the left series with the right MA at each pair of consecutive observations. "
        "A bearish crossover occurs when left was at/above right and then becomes strictly below. "
        "Return true (1) if ANY such event exists in the last X transitions.",
        "Differences +1, −1, +0.5 contain a bearish crossover, so == 1 passes over those two "
        "transitions even though the left line finishes above again.",
        "This tests whether a crossing event occurred, not whether the left line is still below. "
        "Add left < right to require that current alignment. Ending exactly equal does not count "
        "as crossing below; the new difference must be negative.",
    ),
    "separation_change": (
        "At the beginning and end, calculate absolute separation = abs(100 × (left / right MA − 1)). "
        "Return final absolute separation minus starting absolute separation, in percentage points.",
        "Starting separation 1% and ending separation 2.5% gives +1.5 percentage points and passes > 0. "
        "Shrinking from 2% to 0.5% gives −1.5 points and passes < 0.",
        "Absolute separation ignores which line is above. Widening can therefore be bullish or bearish. "
        "Moving from 1% above to 1% below gives zero endpoint separation change despite a crossover. "
        "Add a current above/below condition to specify alignment. Intermediate separation values do "
        "not determine this endpoint-change metric.",
    ),
}


def method_tooltip(method):
    description, example, units = METHOD_HELP[method]
    calculation, worked_example, interpretation = METHOD_DETAILS[method]
    return (
        f"**{METHODS[method]}**\n\n"
        f"**What it measures**\n\n{description}\n\n"
        f"**How it is calculated**\n\n{calculation}\n\n"
        f"**Lookback**\n\n{lookback_help(method)}\n\n"
        f"**Threshold and units**\n\n{units}\n\n"
        f"**Worked example**\n\n{worked_example}\n\n"
        f"**Example settings**\n\n{example}\n\n"
        f"**Interpretation and limits**\n\n{interpretation}\n\n"
        "The MA period controls how the line is calculated; the trend lookback controls which part "
        "of that line is tested. All windows use trading sessions through the screening date. "
        "Required missing observations make the rule unavailable; they are not filled or treated as passing."
    )


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
