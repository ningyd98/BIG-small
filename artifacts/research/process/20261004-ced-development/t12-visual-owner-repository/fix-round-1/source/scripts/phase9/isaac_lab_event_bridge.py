"""Materialize the serializable parity plan inside an Isaac Lab runtime.

This file must be imported only by Isaac Lab's Python launcher. Core CI can
inspect and test the plan contract without importing NVIDIA modules.
"""

from __future__ import annotations

from typing import Any


def materialize_event_terms(plan: dict[str, object]) -> dict[str, Any]:
    from isaaclab.envs import mdp  # type: ignore[import-not-found]
    from isaaclab.managers import (  # type: ignore[import-not-found]
        EventTermCfg,
        SceneEntityCfg,
    )

    function_map = {
        "randomize_rigid_body_mass": mdp.randomize_rigid_body_mass,
        "randomize_rigid_body_material": mdp.randomize_rigid_body_material,
        "randomize_actuator_gains": mdp.randomize_actuator_gains,
        "randomize_physics_scene_gravity": mdp.randomize_physics_scene_gravity,
    }
    result: dict[str, Any] = {}
    raw_events = plan.get("events", [])
    if not isinstance(raw_events, list):
        raise ValueError("event plan events must be a list")
    for raw in raw_events:
        if not isinstance(raw, dict):
            raise ValueError("event plan entry must be an object")
        function_name = str(raw.get("function", ""))
        function = function_map.get(function_name)
        if function is None:
            raise ValueError(f"unsupported Isaac Lab event function: {function_name}")
        params = dict(raw.get("params", {}))
        asset = params.get("asset_cfg")
        if isinstance(asset, dict):
            params["asset_cfg"] = SceneEntityCfg(
                str(asset["name"]),
                body_names=list(asset.get("body_names", [])),
                joint_names=list(asset.get("joint_names", [])),
            )
        result[str(raw["name"])] = EventTermCfg(
            func=function,
            mode=str(raw.get("mode", "reset")),
            params=params,
        )
    return result


def materialize_runtime_configs(
    plan: dict[str, object],
    *,
    physics_dt_s: float,
    delayed_pd_base: dict[str, Any],
) -> dict[str, Any]:
    """Build Isaac Lab actuator/noise configs that are not EventManager terms.

    ``delayed_pd_base`` supplies the robot-specific joint expressions, gains,
    and limits required by DelayedPDActuatorCfg. The shared sample supplies only
    the randomized delay, so it cannot silently replace those robot settings.
    """

    if physics_dt_s <= 0:
        raise ValueError("physics_dt_s must be positive")
    from isaaclab.actuators import (  # type: ignore[import-not-found]
        DelayedPDActuatorCfg,
    )
    from isaaclab.utils.noise import (  # type: ignore[import-not-found]
        GaussianNoiseCfg,
    )

    raw_configs = plan.get("runtime_configs", {})
    if not isinstance(raw_configs, dict):
        raise ValueError("event plan runtime_configs must be an object")
    result: dict[str, Any] = {}
    actuator = raw_configs.get("actuator_delay")
    if isinstance(actuator, dict):
        delay_ms = _numeric(actuator.get("delay_ms", 0.0))
        delay_steps = max(0, int(round(delay_ms / 1_000.0 / physics_dt_s)))
        result["actuator"] = DelayedPDActuatorCfg(
            **delayed_pd_base,
            min_delay=delay_steps,
            max_delay=delay_steps,
        )
        result["actuator_delay_steps"] = delay_steps
    noise = raw_configs.get("camera_depth_noise")
    if isinstance(noise, dict):
        result["camera_depth_noise"] = GaussianNoiseCfg(
            mean=_numeric(noise.get("mean_m", 0.0)),
            std=_numeric(noise.get("std_m", 0.0)),
            operation="add",
        )
    return result


def _numeric(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"expected numeric Isaac Lab configuration value, got {value!r}")
    return float(value)
