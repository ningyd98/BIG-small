"""Explicit research snapshot loading, with its evidence verified before use."""

from __future__ import annotations

import json
from pathlib import Path

from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot, resolve_visual_planner
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter


def load_frozen_planner(directory: Path) -> RGBDPlannerAdapter:
    # The research verifier lives with the repository's reproducible CLI tools.
    from scripts.probe_rgbd_model import verify_frozen_bundle

    if not verify_frozen_bundle(directory):
        raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: frozen model evidence drift or missing")
    snapshot = ModelConfigSnapshot(**json.loads((directory / "model-frozen.json").read_text()))
    return resolve_visual_planner(snapshot)
