"""Exact hand-calculated SOFTWARE_ONLY time recipes; no runtime qualification."""

from dataclasses import FrozenInstanceError, asdict
from fractions import Fraction
from importlib import import_module

import pytest


def recipe(**changes):
    return (
        dict(
            skill="MOVE_ABOVE",
            dt_numerator=1,
            dt_denominator=240,
            registered_dt_s=1 / 240,
            original_timeout_ns=1_000_000_000,
            original_expected_ns=1_000_000_000,
            compiled_timeout_ns=1_000_000_000,
            compiled_expected_ns=1_000_000_000,
            effective_owner_required_ns=1_000_000_000,
            builtin_tail_included=False,
            registered_wait_steps=0,
        )
        | changes
    )


def calculate(**changes):
    module = import_module("cloud_edge_robot_arm.vision.native_completion_horizon")
    return module.completion_horizon_rational_v1(**recipe(**changes))


def test_registered_one_over_240_exact_horizon():
    result = calculate()
    assert (result.base_steps, result.total_steps) == (240, 240)
    assert (result.total_duration_numerator, result.total_duration_denominator) == (1, 1)
    assert result.registered_dt_hex == (1 / 240).hex()
    assert result.registered_dt_ratio == (1 / 240).as_integer_ratio()
    assert result.native_authority == "UNAVAILABLE"


@pytest.mark.parametrize("skill,tail,total", [("LIFT", 120, 360), ("RELEASE", 240, 480)])
def test_tail_oracle_and_included_tail(skill, tail, total):
    result = calculate(skill=skill)
    assert (result.builtin_tail_steps, result.added_tail_steps, result.total_steps) == (
        tail,
        tail,
        total,
    )
    included = calculate(skill=skill, builtin_tail_included=True, registered_wait_steps=2)
    assert (included.added_tail_steps, included.total_steps) == (0, 242)


def test_ceil_and_reduction_without_float_accumulation():
    result = calculate(
        dt_numerator=2, dt_denominator=480, effective_owner_required_ns=1_000_000_001
    )
    assert (result.dt_numerator, result.dt_denominator, result.total_steps) == (1, 240, 241)
    assert (result.total_duration_numerator, result.total_duration_denominator) == (241, 240)


def test_decimal_default_is_a_distinct_explicit_recipe():
    dt = Fraction("0.0041666667")
    result = calculate(
        dt_numerator=dt.numerator, dt_denominator=dt.denominator, registered_dt_s=0.0041666667
    )
    assert result.total_steps == 240
    assert Fraction(result.total_duration_numerator, result.total_duration_denominator) > 1
    with pytest.raises(ValueError):
        calculate(registered_dt_s=0.0041666667)


def test_invalid_types_nonfinite_and_inclusion_are_rejected():
    for change in (
        {"dt_numerator": True},
        {"dt_denominator": 0},
        {"registered_wait_steps": True},
        {"registered_dt_s": float("nan")},
        {"registered_dt_s": float("inf")},
        {"registered_dt_s": 1},
        {"original_timeout_ns": 0},
        {"compiled_expected_ns": 2.5},
        {"builtin_tail_included": 1},
        {"builtin_tail_included": True},
        {"skill": "UNKNOWN"},
    ):
        with pytest.raises(ValueError):
            calculate(**change)


def test_all_eight_skills_and_fixed_frozen_scope():
    for skill in (
        "MOVE_ABOVE",
        "APPROACH",
        "GRASP",
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "RETREAT",
    ):
        result = calculate(skill=skill)
        assert result.total_steps >= 240
        assert asdict(result)["qualification"] == "UNKNOWN"
        with pytest.raises(FrozenInstanceError):
            result.total_steps = 1
