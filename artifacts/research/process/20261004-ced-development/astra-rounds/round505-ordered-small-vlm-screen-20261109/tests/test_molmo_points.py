import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
from molmoer_adapter import parse_native


def test_image_id_and_first_prediction_without_oracle():
    result = parse_native('<points label="red block" coords="1 1 500 500 2 750 600"/>', 320, 240)
    assert result["point"]["point"] == [160, 120]
    assert len(result["point"]["predictions"]) == 2


def test_explicit_absence_only():
    assert parse_native("ABSENT", 320, 240)["point"]["status"] == "REFUSAL"
    assert parse_native("I do not know", 320, 240)["point"]["status"] == "INVALID"


@pytest.mark.parametrize("raw", ['<points coords="2 1 500 500"/>', '<points coords="1 1 1001 500"/>', '<points coords="1 1 500"/>'])
def test_wrong_image_range_or_arity_is_invalid(raw):
    assert parse_native(raw, 320, 240)["point"]["status"] == "INVALID"
