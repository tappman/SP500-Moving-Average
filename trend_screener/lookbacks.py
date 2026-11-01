"""Editable-window recommendations, not fitted or optimized trading parameters."""

EMA_LOOKBACK_ANCHORS = (
    (2, 5), (3, 5), (5, 5), (7, 6), (8, 6), (9, 7), (10, 7),
    (12, 8), (13, 8), (15, 9), (20, 10), (25, 10), (30, 12),
    (34, 14), (37, 15), (50, 20), (75, 25), (100, 30), (150, 35), (200, 40),
)
AUTO_LOOKBACK_METHODS = {"slope", "normalized_slope", "r2"}


def suggested_ema_lookback(period: int) -> int:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("EMA period must be a positive integer")
    if period <= EMA_LOOKBACK_ANCHORS[0][0]:
        return 5
    pairs = list(zip(EMA_LOOKBACK_ANCHORS, EMA_LOOKBACK_ANCHORS[1:]))
    left, right = next(((a, b) for a, b in pairs if period <= b[0]), pairs[-1])
    # Piecewise linear interpolation; extend the final segment above EMA200.
    # Integer arithmetic rounds half up without banker's rounding/float drift.
    denominator = right[0] - left[0]
    numerator = left[1] * denominator + (period - left[0]) * (right[1] - left[1])
    return max(5, (2 * numerator + denominator) // (2 * denominator))


def supports_auto_lookback(rule) -> bool:
    return (rule.method in AUTO_LOOKBACK_METHODS and rule.ma.startswith("EMA")
            and rule.ma[3:].isdigit() and int(rule.ma[3:]) > 0)
