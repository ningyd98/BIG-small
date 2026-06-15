from __future__ import annotations


def build_stage_manifest(*, scenario_id: str, seed: int) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "seed": seed,
        "robot": "franka_panda",
        "sensors": ["rgb_camera", "depth_camera", "contacts", "effort"],
    }
