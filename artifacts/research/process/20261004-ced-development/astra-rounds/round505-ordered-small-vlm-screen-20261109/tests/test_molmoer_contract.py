import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
from molmoer_adapter import parse_native, next_call_index


def test_points_endpoint_and_axis():
    assert parse_native('<points coords="1 1 1000 000"/>', 320, 240)["point"]["point"] == [319, 0]


def test_nonfinite_is_invalid():
    assert parse_native('<points coords="1 1 NaN 500"/>', 320, 240)["point"]["status"] == "INVALID"


def test_hard_budget_includes_warm_and_debug():
    assert next_call_index(33, 34) == 34
    with pytest.raises(ValueError):
        next_call_index(34, 34)
    with pytest.raises(ValueError):
        next_call_index(134, 134)
