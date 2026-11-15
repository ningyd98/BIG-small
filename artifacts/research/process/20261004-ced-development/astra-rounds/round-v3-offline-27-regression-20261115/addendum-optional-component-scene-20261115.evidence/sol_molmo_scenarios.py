"""Seeded component-only conditions; never a native/formal scene qualification."""
from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig


def sample_component_scene(seed: int, split: str) -> dict[str, Any]:
    """Sample actual initial poses in a separate diagnostic namespace."""
    if type(seed) is not int or not 0 <= seed < 2**31:
        raise ValueError("component scene seed must be a nonnegative 31-bit integer")
    if type(split) is not str or split not in {"development", "held-out"}:
        raise ValueError("unknown component scene split")
    digest = hashlib.sha256(f"sol-molmo.component-pose.v1/{split}/{seed}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    stress = seed % 4 == 0
    if stress:
        x, y = rng.uniform(0.36, 0.42), rng.uniform(-0.44, -0.36)
    elif split == "development":
        x, y = rng.uniform(0.40, 0.49), rng.uniform(-0.05, 0.05)
    else:
        x, y = rng.uniform(0.38, 0.51), rng.uniform(-0.07, 0.07)
    yaw = rng.uniform(-0.30 if split == "held-out" else -0.20,
                      0.30 if split == "held-out" else 0.20)
    return {
        "schema_version": "sol-molmo.component-pose.v1",
        "seed": seed,
        "split": split,
        "condition": "ARM_OCCLUSION_STRESS" if stress else "VISIBLE_POSE",
        "object_position_m": [round(x, 6), round(y, 6), 0.035],
        "object_yaw_rad": round(yaw, 6),
        "coverage": "ONE_REGISTERED_ASSET_VARIED_OBJECT_POSE",
        "occlusion_label_scope": "INTENDED_STRESS_NOT_MEASURED_OCCLUSION",
    }


def physical_component_scenario(
    seed: int, scene: Mapping[str, Any] | None
) -> PhysicalScenarioConfig:
    """Require exact seeded conditions before selecting the initial physics state."""
    base = PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=seed)
    if scene is None:
        return base
    if not isinstance(scene, Mapping):
        raise ValueError("component scene must be an exact sampled mapping")
    split = scene.get("split")
    if type(split) is not str:
        raise ValueError("component scene requires a known split")
    expected = sample_component_scene(seed, split)
    if dict(scene) != expected:
        raise ValueError("component scene differs from its exact seeded specification")
    x, y, z = expected["object_position_m"]
    return replace(
        base, object_pose=Pose(x=x, y=y, z=z),
        object_yaw_rad=expected["object_yaw_rad"],
    )
