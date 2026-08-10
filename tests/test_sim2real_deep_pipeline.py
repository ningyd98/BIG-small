"""Deep Sim2Real pipeline regression tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from cloud_edge_robot_arm.simulation.config import RandomizationLevel
from cloud_edge_robot_arm.simulation.isaac.lab_randomization import (
    build_isaac_lab_event_plan,
)
from cloud_edge_robot_arm.simulation.mujoco.spec_randomization import (
    compile_randomized_mjspec_model,
)
from cloud_edge_robot_arm.simulation.randomization import DomainRandomizationPolicy
from cloud_edge_robot_arm.simulation.sim2real import (
    GapReportRequest,
    Sim2RealTrace,
    TraceSample,
    generate_gap_report,
)


def test_custom_parameter_ranges_are_deterministic_and_order_independent() -> None:
    mass = {
        "enabled": True,
        "distribution": "UNIFORM",
        "range_mode": "ABSOLUTE",
        "nominal": 0.2,
        "min": 0.15,
        "max": 0.25,
    }
    base = DomainRandomizationPolicy.default(
        RandomizationLevel.MODERATE,
        {"object_mass_kg": mass},
    ).sample(seed=81)
    with_unrelated_override = DomainRandomizationPolicy.default(
        RandomizationLevel.MODERATE,
        {
            "camera_depth_noise_m": {
                "enabled": True,
                "distribution": "FIXED",
                "range_mode": "ABSOLUTE",
                "nominal": 0.01,
                "min": 0.0,
                "max": 0.02,
            },
            "object_mass_kg": mass,
        },
    ).sample(seed=81)

    assert base.parameters["object_mass_kg"] == with_unrelated_override.parameters["object_mass_kg"]
    assert 0.15 <= base.parameters["object_mass_kg"].value <= 0.25
    assert with_unrelated_override.parameters["camera_depth_noise_m"].value == 0.01


def test_custom_parameter_allowlist_rejects_unknown_model_paths() -> None:
    policy = DomainRandomizationPolicy.default(
        RandomizationLevel.SEVERE,
        {"arbitrary_model_path": {"min": 0, "max": 1, "nominal": 0.5}},
    )
    with pytest.raises(ValueError, match="unsupported randomization parameter"):
        policy.sample(seed=1)


def test_mjspec_compiles_dynamic_physical_parameters() -> None:
    mujoco = pytest.importorskip("mujoco")
    result = compile_randomized_mjspec_model(
        mujoco,
        model_path=Path("assets/robots/franka_panda/scene.xml"),
        parameters={
            "object_mass_kg": 0.21,
            "friction_coefficient": 0.34,
            "joint_damping_scale": 1.25,
            "actuator_gain_scale": 1.1,
            "gravity_z_m_s2": -9.7,
        },
    )

    assert float(result.model.body("object").mass[0]) == pytest.approx(0.21)
    assert float(result.model.geom("object_geom").friction[0]) == pytest.approx(0.34)
    assert float(result.model.joint("joint1").damping[0]) == pytest.approx(1.0)
    assert float(result.model.actuator("act1").gainprm[0]) == pytest.approx(13.2)
    assert float(result.model.opt.gravity[2]) == pytest.approx(-9.7)
    assert len(result.spec_xml_sha256) == 64
    assert {item.application_stage for item in result.evidence} == {"MJSPEC"}


def test_isaac_lab_plan_uses_the_exact_shared_sample() -> None:
    sample = DomainRandomizationPolicy.default(RandomizationLevel.MODERATE).sample(seed=17)
    plan = build_isaac_lab_event_plan(sample)
    raw_events = cast(list[dict[str, Any]], plan["events"])
    events = {item["name"]: item for item in raw_events}

    mass = sample.parameters["object_mass_kg"].value
    assert plan["parity_values"]["object_mass_kg"] == mass  # type: ignore[index]
    assert events["object_mass_kg"]["function"] == "randomize_rigid_body_mass"
    assert events["object_mass_kg"]["params"]["mass_distribution_params"] == [mass, mass]
    assert events["friction_coefficient"]["function"] == "randomize_rigid_body_material"
    assert events["joint_damping_scale"]["function"] == "randomize_actuator_gains"
    runtime_configs = cast(dict[str, dict[str, Any]], plan["runtime_configs"])
    assert runtime_configs["actuator_delay"]["delay_ms"] == sample.values["actuator_delay_ms"]
    assert runtime_configs["camera_depth_noise"]["std_m"] == sample.values["camera_depth_noise_m"]


def test_gap_report_aligns_trajectory_and_sensor_samples() -> None:
    simulation = _trace("sim-1", "SIM", offset=0.0)
    real = _trace("real-1", "REAL", offset=0.005)
    report = generate_gap_report(
        GapReportRequest(simulation=simulation, real=real, alignment_tolerance_ms=20)
    )

    assert report.status.value == "PASS"
    assert report.aligned_sample_count == 3
    assert report.alignment_ratio == 1.0
    assert {metric.name for metric in report.metrics} >= {
        "tcp_position_rmse",
        "joint_position_rmse",
        "sensor_latency_rmse",
        "timestamp_skew_p95",
    }
    assert "hardware_write_operations" in report.markdown.lower()
    assert report.safety_boundary["hardware_write_operations"] == []


def test_gap_report_fails_when_alignment_or_pose_gap_exceeds_gate() -> None:
    simulation = _trace("sim-2", "SIM", offset=0.0)
    real = _trace("real-2", "REAL", offset=0.2, tcp_bias=0.2)
    report = generate_gap_report(
        GapReportRequest(simulation=simulation, real=real, alignment_tolerance_ms=10)
    )

    assert report.status.value == "FAIL"
    assert report.aligned_sample_count < report.real_sample_count


def test_gap_report_warns_when_parameter_evidence_is_incomplete() -> None:
    simulation = _trace("sim-3", "SIM", offset=0.0)
    real = _trace("real-3", "REAL", offset=0.0).model_copy(update={"parameters": {}})

    report = generate_gap_report(GapReportRequest(simulation=simulation, real=real))

    assert report.status.value == "WARN"
    assert report.parameter_gaps[0].status == "MISSING_REAL"
    assert any("Parameter evidence incomplete" in warning for warning in report.warnings)


def _trace(
    trace_id: str,
    source: str,
    *,
    offset: float,
    tcp_bias: float = 0.0,
) -> Sim2RealTrace:
    return Sim2RealTrace(
        trace_id=trace_id,
        source=source,  # type: ignore[arg-type]
        clock="simulation_time" if source != "REAL" else "monotonic_time",
        samples=[
            TraceSample(
                elapsed_s=index * 0.1 + offset,
                joint_positions_rad=[0.1 * index, -0.05 * index],
                tcp_position_m=(0.4 + 0.01 * index + tcp_bias, 0.0, 0.3),
                sensor_latency_ms=10.0 + index,
                depth_mean_m=0.5 + index * 0.01,
            )
            for index in range(3)
        ],
        parameters={"object_mass_kg": 0.08 + tcp_bias},
    )
