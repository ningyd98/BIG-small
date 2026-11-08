"""Explicit research snapshot loading, with its evidence verified before use."""

from __future__ import annotations

import json
from pathlib import Path

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, PlannerDraft
from cloud_edge_robot_arm.vision.defaults import DEFAULT_VISUAL_MODEL
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot, resolve_visual_planner
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter


class EnvironmentRGBDPlanner:
    """Defer verified model resolution until planning; never fall back on a failed freeze."""

    requires_rgbd = True
    planner_name = "rgbd_visual"
    model_name = DEFAULT_VISUAL_MODEL

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        return RGBDPlannerAdapter.from_environment().plan(request)


def load_frozen_planner(directory: Path) -> RGBDPlannerAdapter:
    # The research verifier lives with the repository's reproducible CLI tools.
    from scripts.probe_rgbd_model import verify_frozen_bundle

    if not verify_frozen_bundle(directory):
        raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: frozen model evidence drift or missing")
    snapshot = ModelConfigSnapshot(**json.loads((directory / "model-frozen.json").read_text()))
    return resolve_visual_planner(snapshot)
