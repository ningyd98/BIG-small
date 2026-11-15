"""Molmo专用主线程规划适配器；组件诊断执行权属于真实SimulationWorker。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, PlannerDraft
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
from cloud_edge_robot_arm.vision.grounded_planner import MolmoGroundedPlannerAdapter
from cloud_edge_robot_arm.vision.molmo_pointing import MODEL_ID
from cloud_edge_robot_arm.vision.planner import RGBDModelCallFailed, RGBDPlannerAdapter
from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    RoleProviderSnapshot,
    configuration_hash,
)
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

ROOT = Path(__file__).resolve().parents[3]


class MolmoWorkerPlanner(RGBDPlannerAdapter):
    """只消费一次云意图和worker领取的新帧；不执行控制器调用。"""

    def __init__(self, grounded: MolmoGroundedPlannerAdapter, *, output: Path) -> None:
        if type(grounded) is not MolmoGroundedPlannerAdapter or not grounded.worker_owned_refresh:
            raise ValueError("worker-owned two-phase Molmo planner required")
        cloud = grounded.cloud
        role = getattr(cloud, "role_snapshot", None)
        if cloud.model_name != "gpt-6.1-sol" or not isinstance(role, RoleProviderSnapshot):
            raise ValueError("explicit selected Sol cloud role required")
        super().__init__(
            base_url=cloud.base_url,
            model=cloud.model_name,
            provider=cloud.provider,
            timeout_s=cloud.timeout_s,
            allow_paid=cloud.allow_paid,
            chat_path=cloud.chat_path,
            model_snapshot=cloud.model_snapshot,
            cost_ledger=cloud.cost_ledger,
        )
        self.role_snapshot = role
        self.role_config_version = getattr(cloud, "role_config_version", 1)
        self.grounded = grounded
        self.output = Path(output)
        self.calls = 0

    @property
    def awaiting_owned_refresh(self) -> bool:
        """告知执行器是否应在暂停状态领取下一帧。"""
        return self.grounded.awaiting_owned_refresh

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        """用现有完整管线校验两阶段结果，保留原始输出而不再次付费。"""
        self.calls += 1
        if self.calls > 2:
            raise RGBDModelCallFailed("Molmo worker planning budget exhausted")
        response = PlanningPipeline(planner=self.grounded, max_repair_attempts=0).process(request)
        self.output.mkdir(parents=True, exist_ok=True)
        with (self.output / f"planning-stage-{self.calls:02d}.json").open("x") as stream:
            stream.write(response.model_dump_json(indent=2) + "\n")
        if not response.attempts:
            raise RGBDModelCallFailed("Molmo worker planning source rejected")
        draft = response.attempts[-1].draft.model_copy(deep=True)
        if self.calls == 2 and response.outcome != "PLANNED":
            raise RGBDModelCallFailed("Molmo worker owned refresh rejected")
        snapshot = self.model_snapshot
        assert snapshot is not None
        draft.observation_evidence.update(
            model_snapshot=snapshot.evidence(),
            model_snapshot_hash=snapshot.digest(),
        )
        return draft


def make_worker_binding(
    planner: MolmoWorkerPlanner,
    *,
    asset_manifest_sha256: str,
    marker_family_id: str | None = None,
    component_diagnostic: bool = False,
    component_scene: dict[str, Any] | None = None,
) -> RoleRuntimeBinding:
    """固定本次云、规则边缘、OpenCV及本地感知配置，不生成正式验收许可。"""
    if len(asset_manifest_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in asset_manifest_sha256
    ):
        raise ValueError("exact local model manifest digest required")
    if planner.grounded.cloud_vision_fallback and not component_diagnostic:
        raise ValueError("cloud vision fallback requires a component diagnostic binding")
    budget = ExecutionPolicy("budget source", model_snapshot_hash="a" * 64).verification_budget
    policy: dict[str, Any] = {
        "provider": "rules",
        "local_recover_enabled": False,
        "verification_budget": asdict(budget),
        "runtime_router": "verification_router.v1",
        "capabilities": ["CONTINUE", "REOBSERVE", "STOP"],
        "perception_binding": {
            "model": MODEL_ID,
            "precision": "BF16",
            "asset_manifest_sha256": asset_manifest_sha256,
            "generation_limit": 4,
            "cloud_requests": 1,
            "worker_owned_refresh": True,
            "cloud_vision_fallback": planner.grounded.cloud_vision_fallback,
        },
        "research_scope": "MUJOCO_DEVELOPMENT_NOT_FORMAL_ACCEPTANCE",
        "development_marker_family": marker_family_id,
        "component_diagnostic": component_diagnostic,
    }
    if component_scene is not None:
        if not component_diagnostic:
            raise ValueError("component scene requires an explicit component diagnostic")
        from cloud_edge_robot_arm.research.sol_molmo_scenarios import physical_component_scenario

        scene_seed = component_scene.get("seed")
        if type(scene_seed) is not int:
            raise ValueError("component scene requires an integer seed")
        physical_component_scenario(scene_seed, component_scene)
        policy["component_scene"] = json.loads(json.dumps(component_scene, allow_nan=False))
    edge_paths = ["src/cloud_edge_robot_arm/edge/recovery/verification_router.py"] + [
        f"src/cloud_edge_robot_arm/edge/evidence/{name}.py"
        for name in ("models", "validator", "conditions")
    ]
    device_paths = [
        f"src/cloud_edge_robot_arm/vision/{name}.py"
        for name in (
            "action_evidence",
            "tracking",
            "top_grasp",
            "molmo_worker",
            "grounded_planner",
            "cloud_vision_fallback",
            "molmo_pointing",
            "point_association",
            "marked_asset",
            "execution",
            "request_control",
            "evaluation",
        )
    ]
    if marker_family_id is not None:
        from cloud_edge_robot_arm.vision.marker_families import marker_family

        device_paths += [
            marker_family(marker_family_id).asset_path,
            "assets/robots/franka_panda/scene.xml",
        ]

    def hashes(paths: list[str]) -> dict[str, str]:
        return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}

    edge = RoleProviderSnapshot(
        "EDGE",
        "rules",
        "LOCAL_HOST",
        None,
        None,
        None,
        None,
        configuration_hash(policy),
        hashes(edge_paths),
    )
    if component_diagnostic:
        device_paths += [
            "src/cloud_edge_robot_arm/research/sol_molmo_components.py",
            "src/cloud_edge_robot_arm/research/sol_molmo_scenarios.py",
            "src/cloud_edge_robot_arm/simulation/models.py",
            "src/cloud_edge_robot_arm/research/sol_molmo_single_episode.py",
            "src/cloud_edge_robot_arm/simulation_runtime/worker.py",
            "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
            "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
            "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
            "src/cloud_edge_robot_arm/vision/capture.py",
            "src/cloud_edge_robot_arm/vision/marker_families.py",
            "src/cloud_edge_robot_arm/vision/pose_markers.py",
            "src/cloud_edge_robot_arm/edge/runtime/skill_executor.py",
            "src/cloud_edge_robot_arm/edge/runtime/skill_registry.py",
            "src/cloud_edge_robot_arm/edge/safety/shield.py",
            "src/cloud_edge_robot_arm/edge/safety/context_builder.py",
            "src/cloud_edge_robot_arm/edge/safety/rules.py",
            "src/cloud_edge_robot_arm/edge/safety/policy.py",
        ]
    device = hashes(device_paths)
    bundle = RoleModelBundle(
        planner.role_snapshot, "rules", edge.digest(), configuration_hash(device)
    )
    binding = RoleRuntimeBinding(bundle, edge, device, policy, root=ROOT)
    binding.validate(planner)
    return binding
