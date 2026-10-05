"""Project entry points use the repaired gripper without overriding explicit choices."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CURRENT_FREEZE = ROOT / "artifacts/research/process/20261004-gripper-project-migration/model-probe"
MODEL_ENV = (
    "BIGSMALL_VLM_FROZEN_DIR", "BIGSMALL_VLM_PROVIDER", "BIGSMALL_VLM_MODEL",
    "BIGSMALL_VLM_BASE_URL", "BIGSMALL_VLM_API_KEY",
)


def clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in MODEL_ENV:
        monkeypatch.delenv(name, raising=False)


def test_environment_default_uses_the_current_verified_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_edge_robot_arm.vision import frozen_model
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    clear_model_env(monkeypatch)
    calls: list[Path] = []
    marker = object()

    def load(path: Path) -> Any:
        calls.append(path.resolve())
        return marker

    monkeypatch.setattr(frozen_model, "load_frozen_planner", load)
    assert RGBDPlannerAdapter.from_environment() is marker
    assert calls == [CURRENT_FREEZE]


def test_lazy_default_defers_loading_and_preserves_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_edge_robot_arm.vision import frozen_model
    from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable
    from tests.test_rgbd_grasp_scope import _request

    clear_model_env(monkeypatch)
    calls: list[Path] = []

    def unavailable(path: Path) -> Any:
        calls.append(path)
        raise RGBDModelUnavailable("frozen model evidence drift or missing")

    monkeypatch.setattr(frozen_model, "load_frozen_planner", unavailable)
    lazy_type = getattr(frozen_model, "EnvironmentRGBDPlanner", None)
    assert lazy_type is not None
    planner = lazy_type()
    assert not calls
    with pytest.raises(RGBDModelUnavailable, match="drift or missing"):
        planner.plan(_request("mujoco_camera"))
    assert calls == [CURRENT_FREEZE]


def test_api_capabilities_do_not_claim_a_model_before_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from cloud_edge_robot_arm.cloud.api.app import create_app

    clear_model_env(monkeypatch)
    monkeypatch.setenv("BIGSMALL_VLM_MODEL", "custom-vision-model")
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/planning/capabilities")
    assert response.status_code == 200
    assert response.json()["model_name"] == "UNRESOLVED"


@pytest.mark.parametrize("disable_freeze", [False, True])
def test_explicit_environment_model_is_not_replaced(
    monkeypatch: pytest.MonkeyPatch, disable_freeze: bool,
) -> None:
    from cloud_edge_robot_arm.vision import frozen_model
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    clear_model_env(monkeypatch)
    monkeypatch.setenv("BIGSMALL_VLM_MODEL", "custom-vision-model")
    if disable_freeze:
        monkeypatch.setenv("BIGSMALL_VLM_FROZEN_DIR", "")
    monkeypatch.setattr(frozen_model, "load_frozen_planner", lambda _: pytest.fail("override"))
    planner = RGBDPlannerAdapter.from_environment()
    assert planner.model_name == "custom-vision-model"
    assert planner.model_snapshot is None


def test_workbench_factory_uses_current_default_and_preserves_active_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.vision import frozen_model

    clear_model_env(monkeypatch)
    marker = object()
    monkeypatch.setattr(frozen_model, "load_frozen_planner", lambda _: marker)
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "model.db"),
        secret_store=InMemorySecretStore(),
    )
    assert service.visual_planner() is marker
    profile = service.create_profile(
        display_name="explicit", provider_kind=PlannerProviderKind.OLLAMA,
        base_url="http://127.0.0.1:11434", model_name="custom-vision-model",
    )
    service.activate_profile(profile.profile_id)
    monkeypatch.setenv("BIGSMALL_VLM_FROZEN_DIR", str(CURRENT_FREEZE))
    assert service.visual_planner().model_name == "custom-vision-model"


def test_current_research_configs_share_repaired_geometry_and_freeze() -> None:
    for name in ("model_qwen3vl_4b_normalized.yaml", "model_qwen3vl_4b_gripper_v2.yaml"):
        config = yaml.safe_load((ROOT / "configs/research" / name).read_text())
        assert config["grasp_profile"] == "mujoco_upright_box_v2"
        assert config["coordinate_system"] == "normalized_1000"
    for name in ("visual_smoke.yaml", "pilot_foundation.yaml", "pilot_foundation_v2.yaml"):
        config = yaml.safe_load((ROOT / "configs/research" / name).read_text())
        assert (ROOT / config["frozen_dir"]).resolve() == CURRENT_FREEZE


def test_default_probe_generates_the_current_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import probe_rgbd_model as probe

    captured: dict[str, Path] = {}

    def run(config: Path, output: Path) -> dict[str, str]:
        captured.update(config=config, output=output)
        return {"status": "PASS"}

    monkeypatch.setattr(probe, "run_probe", run)
    monkeypatch.setattr(sys, "argv", ["probe_rgbd_model"])
    assert probe.main() == 0
    assert captured["output"].resolve() == CURRENT_FREEZE
    config = yaml.safe_load(captured["config"].read_text())
    assert config["grasp_profile"] == "mujoco_upright_box_v2"


def test_default_offline_evaluator_loads_current_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import evaluate_rgbd_model as evaluate

    from cloud_edge_robot_arm.vision.evaluation import EvaluationReport

    captured: list[Path] = []
    monkeypatch.setattr(evaluate, "load_frozen_planner", lambda p: captured.append(p) or object())
    monkeypatch.setattr(evaluate, "evaluate_model", lambda *_: EvaluationReport(
        assigned=1, succeeded=1, blocked=0, localization_errors_m=(), recognition_coverage=1,
        invalid_depth_rejection_rate=0, latency_summary={},
    ))
    monkeypatch.setattr(sys, "argv", [
        "evaluate_rgbd_model", "--dataset", "unused", "--split", "test", "--output", "unused",
    ])
    assert evaluate.main() == 0
    assert captured[0].resolve() == CURRENT_FREEZE


@pytest.mark.parametrize("explicit_model", [None, "custom-vision-model"])
def test_linux_start_environment_matches_default_and_keeps_overrides(
    explicit_model: str | None,
) -> None:
    env = {key: value for key, value in os.environ.items() if key not in MODEL_ENV}
    if explicit_model:
        env["BIGSMALL_VLM_MODEL"] = explicit_model
    result = subprocess.run([
        "bash", "-c", 'source scripts/linux/env.sh\nprintf "%s" "${BIGSMALL_VLM_FROZEN_DIR-}"',
    ], env=env, cwd=ROOT, capture_output=True, text=True, check=True, timeout=10)
    if explicit_model:
        assert result.stdout == ""
    else:
        assert Path(result.stdout).resolve() == CURRENT_FREEZE


def test_s01_semantic_reference_matches_current_asset_and_rejects_unknown_profile() -> None:
    from cloud_edge_robot_arm.vision.task_semantics import evaluate_s01_task_semantics

    current = evaluate_s01_task_semantics("将红色方块放到绿色区域")
    assert current["semantic_reference"]["asset_sha256"] == hashlib.sha256(
        (ROOT / "assets/robots/franka_panda/scene.xml").read_bytes()
    ).hexdigest()
    assert current["semantic_reference"]["grasp_profile"] == "mujoco_upright_box_v2"
    assert current["semantic_criteria_version"] == "s01-task-semantics-v2"
    old = evaluate_s01_task_semantics(
        "将红色方块放到绿色区域", grasp_profile="mujoco_upright_box_v1",
    )
    assert old["semantic_reference"]["asset_sha256"].startswith("182fb2bc")
    unknown = evaluate_s01_task_semantics("将红色方块放到绿色区域", grasp_profile="unconfigured")
    assert unknown["semantic_status"] == "UNKNOWN"
    assert unknown["semantic_success"] is False
