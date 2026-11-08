"""R486 CPU behavior: saved profiles retain current simulator image calibration."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PIL import Image

from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
from cloud_edge_robot_arm.simulation import config as simulator_config
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.vision import capture as capture_module
from cloud_edge_robot_arm.vision import top_grasp
from cloud_edge_robot_arm.vision.defaults import REPOSITORY_ROOT
from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
from tests.test_sol_evidence_reader import _frame, _request, _wire


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    import mujoco

    def forbidden(*args, **kwargs):
        pytest.fail("R486 software-only test attempted network or simulator execution")

    for target, name in (
        (socket, "create_connection"),
        (socket, "getaddrinfo"),
        (socket.socket, "connect"),
        (urllib.request, "urlopen"),
        (urllib.request, "build_opener"),
        (MuJoCoPhysicsBackend, "__init__"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    for name in ("Renderer", "MjModel", "MjData", "mj_step", "mj_forward"):
        monkeypatch.setattr(mujoco, name, forbidden)


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGSMALL_VLM_ALLOW_PAID_CALL", "true")
    instance = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "software-only-models.db"),
        secret_store=InMemorySecretStore(),
    )
    profile = instance.create_profile(
        display_name="SOFTWARE_ONLY_R486",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.openai.com",
        model_name="gpt-6.1-sol",
        api_key="fictional-r486-test-secret",
        max_tokens=4096,
        timeout_seconds=30,
    )
    instance.activate_profile(profile.profile_id)
    return instance


def test_saved_sol_profile_grounds_current_simulator_frame(service, monkeypatch):
    """Missing calibration, wrong coordinate scaling, or a square resize breaks grounding."""
    rows = _wire(monkeypatch)
    fake_opener = urllib.request.build_opener
    transport = []

    def observe_opener(*handlers):
        boundary = fake_opener(*handlers)
        fake_open = boundary.open

        def observe_open(request, timeout):
            transport.append((request.full_url, timeout))
            return fake_open(request, timeout)

        boundary.open = observe_open
        return boundary

    monkeypatch.setattr(urllib.request, "build_opener", observe_opener)
    observation = _frame().observation
    draft = service.visual_planner(trusted_default_capture=True).plan(_request(_frame()))

    assert draft.observed_scene is not None, draft.parsed_json
    assert draft.parse_error is None
    assert "_sentinel" not in draft.parsed_json
    assert draft.parsed_json["task_target"]["object_class"] == "red block"
    assert draft.parsed_json["task_target"]["target_region_id"] == "visual_destination"
    evidence = draft.observation_evidence
    assert evidence["original_pixel_target"] == [80, 120]
    assert evidence["original_pixel_destination"] == [240, 120]
    assert evidence["grasp_profile"] == "mujoco_upright_box_v2"
    assert evidence["top_grasp_offset_status"] == "CALIBRATED_RGBD_TOP_GRASP_V1"
    assert evidence["grounded_target"] == pytest.approx({"x": 1 / 30, "y": 0.1, "z": 0.28})
    assert evidence["grounded_destination"] == pytest.approx({"x": 0.588, "y": 0.1, "z": 0.2})
    assert evidence["resolved_top_grasp_tcp"] == pytest.approx({"x": 1 / 30, "y": 0.1, "z": 0.25})
    assert evidence["grounded_target"] == observation.world_point((80, 120)).model_dump()
    assert evidence["grounded_destination"] == observation.world_point((240, 120)).model_dump()
    calibrated = top_grasp.resolve_top_grasp(observation, (80, 120), 0.2)
    assert evidence["resolved_top_grasp_tcp"] == pytest.approx(calibrated["resolved_top_grasp_tcp"])
    assert transport == [("https://api.openai.com/v1/chat/completions", 30)]
    assert len(rows) == 1
    body = json.loads(rows[0])
    assert {key: value for key, value in body.items() if key != "messages"} == {
        "model": "gpt-6.1-sol",
        "reasoning_effort": "low",
        "max_completion_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    images = [
        base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
        for message in body["messages"]
        if isinstance(message["content"], list)
        for part in message["content"]
        if part["type"] == "image_url"
    ]
    assert len(images) == 2 and images[0] != images[1]
    assert [Image.open(io.BytesIO(raw)).size for raw in images] == [(320, 240), (320, 240)]


@pytest.mark.parametrize("trusted", [False, True])
def test_saved_profile_preserves_paid_call_guard(service, monkeypatch, trusted):
    monkeypatch.delenv("BIGSMALL_VLM_ALLOW_PAID_CALL")
    rows = _wire(monkeypatch)
    with pytest.raises(RGBDModelUnavailable, match="BIGSMALL_VLM_ALLOW_PAID_CALL"):
        service.visual_planner(trusted_default_capture=trusted).plan(_request(_frame()))
    assert rows == []


@pytest.mark.parametrize("source", ["rgbd_camera", "isaac_camera"])
def test_saved_profile_does_not_calibrate_other_camera_sources(service, monkeypatch, source):
    _wire(monkeypatch)
    frame = _frame()
    observation = RGBDObservation.model_validate(
        {**frame.observation.model_dump(), "source": source, "checksum_sha256": ""}
    )
    frame = replace(frame, observation=observation)
    draft = service.visual_planner(trusted_default_capture=True).plan(_request(frame))
    assert draft.observed_scene is None
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert "trusted MuJoCo" in draft.parsed_json["_reason"]


@pytest.mark.parametrize("asset", ["missing", "changed", "unregistered"])
def test_saved_profile_rejects_untrusted_default_asset(service, monkeypatch, tmp_path, asset):
    rows = _wire(monkeypatch)
    if asset == "unregistered":
        monkeypatch.setattr(top_grasp, "calibration_asset_sha256", lambda profile: None)
    else:
        path = tmp_path / "software-only-scene.xml"
        if asset == "changed":
            path.write_text("<mujoco/>")
        monkeypatch.setattr(
            simulator_config, "SimulatorConfig", lambda: SimpleNamespace(model_path=str(path))
        )
    with pytest.raises(RGBDModelUnavailable, match="calibration"):
        service.visual_planner(trusted_default_capture=True)
    assert rows == []


def test_saved_profile_normalized_center_preserves_non_square_image(service):
    snapshot = service.visual_planner().model_snapshot
    assert model_to_observation_pixel(
        (500, 500),
        _frame().observation,
        image_size=snapshot.image_size,
        coordinate_system=snapshot.coordinate_system,
    ) == (160, 120)


def test_active_profile_switch_keeps_running_snapshot(service):
    running = service.visual_planner()
    original_hash = running.model_snapshot.digest()
    other = service.create_profile(
        display_name="SOFTWARE_ONLY_R486_SECOND",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.openai.com/v1",
        chat_completions_path="/chat/completions",
        model_name="gpt-6.1-sol",
        max_tokens=8192,
        timeout_seconds=45,
    )
    service.activate_profile(other.profile_id)
    later = service.visual_planner()
    assert running.model_snapshot.digest() == original_hash
    assert running.model_snapshot.generation_parameters["max_completion_tokens"] == 4096
    assert running.model_snapshot.timeout_s == 30
    assert later.model_snapshot.generation_parameters["max_completion_tokens"] == 8192
    assert later.model_snapshot.timeout_s == 45
    assert later.model_snapshot.digest() != original_hash


def test_no_active_profile_uses_existing_environment_path(tmp_path, monkeypatch):
    instance = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "empty.db"),
        secret_store=InMemorySecretStore(),
    )
    marker = object()
    monkeypatch.setattr(RGBDPlannerAdapter, "from_environment", lambda: marker)
    assert instance.visual_planner() is marker


@pytest.mark.parametrize("kind", [PlannerProviderKind.MOCK, PlannerProviderKind.RULE_BASED])
def test_legacy_profile_cannot_claim_visual_calibration(service, kind):
    legacy = service.create_profile(
        display_name="SOFTWARE_ONLY_LEGACY", provider_kind=kind, model_name="legacy"
    )
    service.activate_profile(legacy.profile_id)
    with pytest.raises(RGBDModelUnavailable, match="legacy text/Mock"):
        service.visual_planner()


def test_generic_saved_profile_rejects_untrusted_mujoco_observation(service, monkeypatch):
    """An intact default XML does not calibrate a caller's different MuJoCo scene."""
    asset = REPOSITORY_ROOT / "assets/robots/franka_panda/scene.xml"
    original_digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    assert original_digest == "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
    _wire(monkeypatch)
    frame = _frame()
    observation = RGBDObservation.model_validate(
        {
            **frame.observation.model_dump(),
            "scene_id": "SOFTWARE_ONLY_CUSTOM_MUJOCO_SCENE",
            "calibration_version": "SOFTWARE_ONLY_DIFFERENT_GRIPPER",
            "checksum_sha256": "",
        }
    )
    draft = service.visual_planner().plan(_request(replace(frame, observation=observation)))
    assert draft.observed_scene is None, "Unrelated default XML must not authorize this observation"
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert "trusted MuJoCo" in draft.parsed_json["_reason"]
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == original_digest


def test_generic_saved_profile_does_not_read_default_calibration_asset(service, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Generic observations cannot infer calibration from the default XML")

    monkeypatch.setattr(top_grasp, "calibration_asset_sha256", forbidden)
    assert service.visual_planner().model_snapshot.grasp_profile == "unconfigured"


def test_default_capture_dry_run_uses_trusted_calibration(service, monkeypatch):
    rows = _wire(monkeypatch)
    captures = []
    drafts = []
    original_plan = RGBDPlannerAdapter.plan

    def capture(*args, **kwargs):
        assert args == () and kwargs == {}
        observation = RGBDObservation.model_validate(
            {
                **_frame().observation.model_dump(),
                "captured_at": datetime.now(UTC),
                "checksum_sha256": "",
            }
        )
        captures.append(observation)
        return observation

    def observe_plan(planner, request):
        draft = original_plan(planner, request)
        drafts.append(draft)
        return draft

    monkeypatch.setattr(capture_module, "capture_simulated_observation", capture)
    monkeypatch.setattr(RGBDPlannerAdapter, "plan", observe_plan)
    result = service.planner_dry_run(
        user_instruction="pick the red cube and place it in the green target region",
        sample_scene="S01_NORMAL_STATIC",
        control_mode="PCSC",
    )
    assert result["parse_result"] == "PLANNED", result
    assert len(captures) == len(drafts) == len(rows) == 1
    assert drafts[0].observed_scene is not None
    evidence = drafts[0].observation_evidence
    assert evidence["grasp_profile"] == "mujoco_upright_box_v2"
    assert evidence["original_pixel_target"] == [80, 120]
    assert evidence["original_pixel_destination"] == [240, 120]
    assert evidence["grounded_target"] == captures[0].world_point((80, 120)).model_dump()
    assert evidence["grounded_destination"] == captures[0].world_point((240, 120)).model_dump()
    assert result["final_contract"]["task_target"]["object_class"] == "red block"
    assert result["final_contract"]["task_target"]["target_region_id"] == "visual_destination"
    assert result["validation_errors"] == []
    assert result["dispatch"] is False and result["hardware_execution"] is False
    assert result["evaluation_scope"] == "RGBD_PLANNING_ONLY"


@pytest.mark.parametrize("asset", ["missing", "changed"])
def test_trusted_capture_checks_actual_working_directory_asset(
    service, monkeypatch, tmp_path, asset
):
    repository_asset = REPOSITORY_ROOT / "assets/robots/franka_panda/scene.xml"
    assert hashlib.sha256(repository_asset.read_bytes()).hexdigest() == (
        "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
    )
    if asset == "changed":
        other = tmp_path / "assets/robots/franka_panda/scene.xml"
        other.parent.mkdir(parents=True)
        other.write_text("<mujoco/>")
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted default asset must be rejected before capture")

    monkeypatch.setattr(capture_module, "capture_simulated_observation", forbidden)
    assert service.visual_planner().model_snapshot.grasp_profile == "unconfigured"
    with pytest.raises(RGBDModelUnavailable, match="calibration"):
        service.visual_planner(trusted_default_capture=True)
    result = service.planner_dry_run(
        user_instruction="pick cube", sample_scene="S01_NORMAL_STATIC", control_mode="PCSC"
    )
    assert result["parse_result"] == "BLOCKED_BY_ENV"
    assert result["reason"] == "RGBDModelUnavailable"
