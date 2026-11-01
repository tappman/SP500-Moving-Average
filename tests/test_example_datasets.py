from fractions import Fraction
import json
import math
from pathlib import Path

import pytest

from trend_screener.metrics import trend_metrics


def test_published_synthetic_datasets_match_independent_expected_values():
    path = Path(__file__).resolve().parents[1] / "examples" / "synthetic_scenarios.json"
    for case in json.loads(path.read_text())["scenarios"]:
        measured = trend_metrics(case["ma_values"])
        assert len(case["ma_values"]) == case["regression_observations"] == case["net_transitions"] + 1
        for name, expected in case["expected"].items():
            if expected is None:
                assert math.isnan(measured[name]), case["name"]
            elif isinstance(expected, bool):
                assert measured[name] is expected, case["name"]
            else:
                target = float(Fraction(expected)) if isinstance(expected, str) else expected
                assert measured[name] == pytest.approx(target), (case["name"], name)
