"""Independent arithmetic controls, never original-data or native admission evidence."""

import itertools
import math
from dataclasses import FrozenInstanceError, replace
from importlib import import_module, util

import pytest


def api():
    name = "cloud_edge_robot_arm.vision.native_completion"
    assert util.find_spec(name) is not None, "missing planned completion kernel"
    return import_module(name)


def metric_args():
    return dict(
        geometric_error_m=0.001,
        command_points_m=[[0.002, 0, 0]],
        capture_reference_points_m=[[0, 0, 0]],
        terminal_reference_points_m=[[-0.004, 0, 0]],
        actual_points_m=[[0.005, 0, 0]],
    )


def horizon_args():
    return dict(
        physics_dt_ns=3_000_000,
        original_timeout_ns=1_000_000_000,
        original_expected_ns=1_000_000_000,
        compiled_timeout_ns=1_000_000_000,
        compiled_expected_ns=1_000_000_000,
        effective_owner_required_ns=1_000_000_000,
    )


def test_joint_triangle_example():
    result = api().completion_metric_v2(**metric_args())
    assert (result.u_m, result.l_m, result.m_m) == pytest.approx((0.002, 0.003, 0.004))
    assert result.completion_error_m == pytest.approx(0.009)
    assert result.endpoint_error_m == pytest.approx(0.009)
    assert result.point_u_m == pytest.approx((0.002,))
    assert result.schema_version == "native.completion.metric.v2"
    assert result.evidence_scope == "SOFTWARE_ONLY"
    assert result.native_authority == "UNAVAILABLE"


def test_noncollinear_three_dimensional_metric():
    module = api()
    args = dict(
        geometric_error_m=0,
        command_points_m=[(1, 2, 2)],
        capture_reference_points_m=[(0, 0, 0)],
        terminal_reference_points_m=[(0, 0, -12)],
        actual_points_m=[(1, 2, 6)],
    )
    result = module.completion_metric_v2(**args)
    assert (result.u_m, result.l_m, result.m_m, result.completion_error_m) == (3, 4, 12, 19)
    assert result.endpoint_error_m == math.sqrt(329)
    assert module.completion_metric_v2(**{**args, "geometric_error_m": 20}).completion_error_m == 20


def test_pointwise_sum_and_rotated_vertices():
    module = api()
    result = module.completion_metric_v2(
        geometric_error_m=0,
        command_points_m=[(3, 0, 0), (0, 0, 0)],
        capture_reference_points_m=[(0, 0, 0), (0, 0, 0)],
        terminal_reference_points_m=[(0, 0, 0), (0, 0, 0)],
        actual_points_m=[(3, 0, 0), (0, 4, 0)],
    )
    assert result.point_u_m == (3, 0)
    assert result.point_l_m == (0, 4)
    assert result.completion_error_m == 4
    vertices = list(itertools.product((-1, 1), repeat=3))
    rotated = [(-y, x, z) for x, y, z in vertices]
    result = module.completion_metric_v2(
        geometric_error_m=0,
        command_points_m=vertices,
        capture_reference_points_m=vertices,
        terminal_reference_points_m=vertices,
        actual_points_m=rotated,
    )
    assert len(result.point_l_m) == 8
    assert result.point_l_m == (2.0,) * 8
    assert result.completion_error_m == 2.0
    rotated_half_turn = [(-x, -y, z) for x, y, z in vertices]
    result = module.completion_metric_v2(
        geometric_error_m=0,
        command_points_m=vertices,
        capture_reference_points_m=vertices,
        terminal_reference_points_m=vertices,
        actual_points_m=rotated_half_turn,
    )
    assert result.point_l_m == pytest.approx((math.sqrt(8),) * 8)
    assert result.completion_error_m == pytest.approx(math.sqrt(8))
    assert result.u_m == result.m_m == 0
    assert result.endpoint_error_m == pytest.approx(math.sqrt(8))


def test_metric_requires_complete_finite_points():
    module = api()
    for name in metric_args():
        if name == "geometric_error_m":
            invalid = (-1, True, "1", None, math.nan, math.inf, -math.inf)
        else:
            invalid = [[], [[0, 0]], [[0] * 4], [[0, 0, 0]] * 2, None, "123"]
            invalid += [[[v, 0, 0]] for v in (True, "0", None, math.nan, math.inf, -math.inf)]
        for value in invalid:
            with pytest.raises(ValueError):
                module.completion_metric_v2(**{**metric_args(), name: value})
    with pytest.raises(ValueError):
        module.completion_metric_v2(
            **{
                **metric_args(),
                "command_points_m": [[1e308, 0, 0]],
                "capture_reference_points_m": [[-1e308, 0, 0]],
            }
        )


def test_metric_reference_drift_and_detachment():
    module = api()
    args = metric_args()
    result = module.completion_metric_v2(**args)
    assert result.m_m == 0.004
    args["terminal_reference_points_m"][0][0] = 123
    args["command_points_m"][0][0] = 456
    assert result.point_m_m == (0.004,)
    assert result.point_u_m == (0.002,)
    with pytest.raises(FrozenInstanceError):
        result.completion_error_m = 0
    args["terminal_reference_points_m"] = args["capture_reference_points_m"]
    assert module.completion_metric_v2(**args).m_m == 0


def test_horizon_rounds_exact_integer_ns():
    module = api()
    base = {k: (3_000_000 if k == "physics_dt_ns" else 999_000_000) for k in horizon_args()}
    assert module.completion_horizon_v2("GRASP", **base).base_steps == 333
    for field in base.keys() - {"physics_dt_ns"}:
        result = module.completion_horizon_v2("GRASP", **{**base, field: 999_000_001})
        assert result.base_steps == result.total_steps == 334
        assert result.total_sim_ns == 1_002_000_000
        assert type(result.total_sim_ns) is int
    # An integer beyond floating point precision still rounds by exact division.
    large = {**base, "physics_dt_ns": 1, "effective_owner_required_ns": 2**60 + 1}
    assert module.completion_horizon_v2("GRASP", **large).total_steps == 2**60 + 1


def test_lift_release_tails_and_waits():
    module = api()
    for skill, tail, total in (("LIFT", 167, 501), ("RELEASE", 334, 668)):
        result = module.completion_horizon_v2(skill, **horizon_args())
        assert result.base_steps == 334
        assert result.builtin_tail_steps == result.added_tail_steps == tail
        assert result.total_steps == total
        result = module.completion_horizon_v2(skill, **horizon_args(), registered_wait_steps=2)
        assert result.total_steps == total + 2
        assert result.total_sim_ns == (total + 2) * 3_000_000
        assert result.evidence_scope == "SOFTWARE_ONLY"
        assert result.native_authority == "UNAVAILABLE"


def test_horizon_included_tail_is_not_added_twice():
    module = api()
    for skill in ("LIFT", "RELEASE"):
        result = module.completion_horizon_v2(skill, **horizon_args(), builtin_tail_included=True)
        assert result.total_steps == 334
        assert result.builtin_tail_steps > 0 and result.added_tail_steps == 0
        short = {k: (3_000_000 if k == "physics_dt_ns" else 1) for k in horizon_args()}
        with pytest.raises(ValueError):
            module.completion_horizon_v2(skill, **short, builtin_tail_included=True)
    for skill in set(module.COMPLETION_SKILLS_V2) - {"LIFT", "RELEASE"}:
        assert module.completion_horizon_v2(skill, **horizon_args()).builtin_tail_steps == 0
        with pytest.raises(ValueError):
            module.completion_horizon_v2(skill, **horizon_args(), builtin_tail_included=True)


def test_horizon_strict_numeric_inputs():
    module = api()
    args = {**horizon_args(), "registered_wait_steps": 0}
    for field in args:
        invalid = [True, 1.0, "1", None, math.nan, math.inf, -1]
        if field != "registered_wait_steps":
            invalid.append(0)
        for value in invalid:
            with pytest.raises(ValueError):
                module.completion_horizon_v2("LIFT", **{**args, field: value})
    for value in (0, 1, None):
        with pytest.raises(ValueError):
            module.completion_horizon_v2("LIFT", **args, builtin_tail_included=value)
    for skill in ("HOME", "lift", None, True):
        with pytest.raises(ValueError):
            module.completion_horizon_v2(skill, **args)


def test_metric_and_horizon_are_public_diagnostics_only():
    module = api()
    for result in (
        module.completion_metric_v2(**metric_args()),
        module.completion_horizon_v2("LIFT", **horizon_args()),
    ):
        assert result.evidence_scope == "SOFTWARE_ONLY"
        assert result.native_authority == "UNAVAILABLE"
        for name in ("admit", "validate", "geometric_error_bound_m", "motion_bound_m_s"):
            assert not hasattr(result, name)
        with pytest.raises(ValueError):
            replace(result, native_authority="VALID")
        with pytest.raises(FrozenInstanceError):
            result.evidence_scope = "ACTUAL"
