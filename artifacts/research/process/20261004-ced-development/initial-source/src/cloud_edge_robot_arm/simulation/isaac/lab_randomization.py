"""Map a simulator-neutral sample to an Isaac Lab EventManager plan.

This module intentionally does not import Isaac Lab.  The returned plan is a
serializable contract that can be inspected in CI and materialized inside an
official Isaac Lab Python runtime by ``scripts/phase9/isaac_lab_event_bridge.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloud_edge_robot_arm.simulation.randomization import RandomizationSample


@dataclass(frozen=True)
class IsaacLabEventTerm:
    name: str
    function: str
    mode: str
    params: dict[str, Any]

    def to_jsonable(self) -> dict[str, object]:
        return {
            "name": self.name,
            "function": self.function,
            "mode": self.mode,
            "params": self.params,
        }


def build_isaac_lab_event_plan(sample: RandomizationSample) -> dict[str, object]:
    """Build reset events with exact values from the shared deterministic sample."""

    values = sample.values
    events: list[IsaacLabEventTerm] = []
    if "object_mass_kg" in values:
        value = values["object_mass_kg"]
        events.append(
            IsaacLabEventTerm(
                name="object_mass_kg",
                function="randomize_rigid_body_mass",
                mode="reset",
                params={
                    "asset_cfg": {"name": "object", "body_names": [".*"]},
                    "mass_distribution_params": [value, value],
                    "operation": "abs",
                    "distribution": "uniform",
                    "recompute_inertia": True,
                },
            )
        )
    if "friction_coefficient" in values:
        value = values["friction_coefficient"]
        events.append(
            IsaacLabEventTerm(
                name="friction_coefficient",
                function="randomize_rigid_body_material",
                mode="reset",
                params={
                    "asset_cfg": {"name": "object", "body_names": [".*"]},
                    "static_friction_range": [value, value],
                    "dynamic_friction_range": [value, value],
                    "restitution_range": [0.0, 0.0],
                    "num_buckets": 1,
                },
            )
        )
    if "joint_damping_scale" in values:
        value = values["joint_damping_scale"]
        events.append(
            IsaacLabEventTerm(
                name="joint_damping_scale",
                function="randomize_actuator_gains",
                mode="reset",
                params={
                    "asset_cfg": {"name": "robot", "joint_names": ["panda_joint.*"]},
                    "damping_distribution_params": [value, value],
                    "operation": "scale",
                    "distribution": "uniform",
                },
            )
        )
    if "actuator_gain_scale" in values:
        value = values["actuator_gain_scale"]
        events.append(
            IsaacLabEventTerm(
                name="actuator_gain_scale",
                function="randomize_actuator_gains",
                mode="reset",
                params={
                    "asset_cfg": {"name": "robot", "joint_names": ["panda_joint.*"]},
                    "stiffness_distribution_params": [value, value],
                    "operation": "scale",
                    "distribution": "uniform",
                },
            )
        )
    if "gravity_z_m_s2" in values:
        value = values["gravity_z_m_s2"]
        events.append(
            IsaacLabEventTerm(
                name="gravity_z_m_s2",
                function="randomize_physics_scene_gravity",
                mode="reset",
                params={
                    "gravity_distribution_params": [[0.0, 0.0, value], [0.0, 0.0, value]],
                    "operation": "abs",
                    "distribution": "uniform",
                },
            )
        )
    runtime_configs: dict[str, object] = {}
    if "actuator_delay_ms" in values:
        runtime_configs["actuator_delay"] = {
            "config_class": "isaaclab.actuators.DelayedPDActuatorCfg",
            "delay_ms": values["actuator_delay_ms"],
            "step_conversion": "round(delay_ms / 1000 / physics_dt_s)",
        }
    if "camera_depth_noise_m" in values:
        runtime_configs["camera_depth_noise"] = {
            "config_class": "isaaclab.utils.noise.GaussianNoiseCfg",
            "mean_m": 0.0,
            "std_m": values["camera_depth_noise_m"],
            "operation": "add",
        }
    return {
        "schema_version": "sim2real.isaac_lab.events.v1",
        "sample_version": sample.version,
        "seed": sample.seed,
        "randomization_level": sample.level.value,
        "events": [event.to_jsonable() for event in events],
        "runtime_configs": runtime_configs,
        "parity_values": dict(sorted(values.items())),
        "runtime_required": "Isaac Lab EventManager",
        "validation_claimed": False,
    }
