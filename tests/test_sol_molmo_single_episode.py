"""单场景入口必须保留执行阻塞、原始证据和零调用默认值。"""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.vision.capture import CapturedFrame
from tests.test_pose_marker_evidence import observation, registration


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_single_episode")


def test_default_prepares_one_fixed_scene_without_runtime_or_model(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("dry-run contacted a runtime/model/secret")

    module = api()
    monkeypatch.setattr(module, "_run_observed_scene", forbidden)
    result = module.run_single_episode(output=tmp_path / "out", seed=42001)
    assert result["status"] == "PREPARED"
    assert result["success"] is False and result["physical_success"] is None
    assert result["model_calls"] == result["executed_actions"] == 0
    assert result["physics_steps"] == 0
    assert result["marker_before"]["status"] == "NOT_RUN"
    assert result["formal_research"] == "NOT_ACCEPTED"
    saved = json.loads((tmp_path / "out/result.json").read_text())
    assignment = json.loads((tmp_path / "out/scene-assignment.json").read_text())
    assert saved == result
    assert assignment["seed"] == 42001
    assert assignment["marker"]["marker_size_m"] == 0.045
    assert assignment["scene_sampling"] == "FIXED_REGISTERED_SCENE"
    assert assignment["independent_random_scene"] is False


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "result.json"
    sentinel.write_bytes(b"frozen failure\n")
    with pytest.raises(FileExistsError):
        api().run_single_episode(output=output)
    assert sentinel.read_bytes() == b"frozen failure\n"


@pytest.mark.parametrize("seed", [True, -1, 1.5, "42001"])
def test_invalid_seed_has_no_output_side_effect(tmp_path, seed):
    with pytest.raises(ValueError):
        api().run_single_episode(output=tmp_path / "out", seed=seed)
    assert not (tmp_path / "out").exists()


def test_unknown_marker_family_has_no_output_side_effect(tmp_path):
    with pytest.raises(ValueError):
        api().run_single_episode(output=tmp_path / "out", marker_family_id="invented")
    assert not (tmp_path / "out").exists()


def test_execute_requires_explicit_paid_model_configuration_before_side_effects(
    tmp_path, monkeypatch
):
    module = api()
    monkeypatch.setattr(
        module, "_run_observed_scene", lambda *a, **k: pytest.fail("unqualified execution")
    )
    with pytest.raises(ValueError, match="execute.*allow-paid"):
        module.run_single_episode(output=tmp_path / "out", mode="execute")
    assert not (tmp_path / "out").exists()


def test_registered_asset_and_bridge_preflight_is_not_a_hardcoded_refusal():
    assignment = api().scene_assignment(42001, "outboard_id7_45mm_v3")
    assert api().execution_blockers(assignment) == []
    assignment["grasp_profile"] = "mujoco_upright_box_v1"
    assert api().execution_blockers(assignment)


def test_component_diagnostic_cannot_be_enabled_outside_execute(tmp_path):
    with pytest.raises(ValueError, match="component.*execute"):
        api().run_single_episode(output=tmp_path / "out", component_diagnostic=True)
    assert not (tmp_path / "out").exists()


def test_component_success_is_revoked_when_final_source_check_fails(tmp_path, monkeypatch):
    module = api()
    original_sha = module._sha
    finished = False

    def observed(assignment, output, result, **kwargs):
        nonlocal finished
        result.update(
            status="COMPONENTS_COMPLETED",
            physical_success=True,
            outcome={"diagnostic_complete": True},
        )
        finished = True

    def changed_sha(path):
        return "0" * 64 if finished else original_sha(path)

    monkeypatch.setattr(module, "_run_observed_scene", observed)
    monkeypatch.setattr(module, "_sha", changed_sha)
    result = module.run_single_episode(
        output=tmp_path / "out",
        mode="execute",
        component_diagnostic=True,
        profile_id="software-only",
        model_control_db=tmp_path / "db",
        model_directory=tmp_path / "model",
        asset_manifest=tmp_path / "manifest",
        allow_paid=True,
    )
    assert result["status"] == "FAILED"
    assert result["physical_success"] is True
    assert result["component_success"] is False


def test_completed_component_file_cannot_override_failed_real_worker(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker, TimedOut
    from tests.test_sol_molmo_worker_integration import RGBPointFixture

    module = api()
    database, profile, secrets = selected_profile(tmp_path)
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(database), secret_store=secrets
    )
    assignment = module.scene_assignment(42001, "side_y_plus_id7_75mm_component_v1")
    assignment["component_diagnostic"] = True
    output = tmp_path / "out"
    output.mkdir()
    planner, binding = module.create_molmo_opencv_bridge(
        service=service,
        profile_id=profile.profile_id,
        points=RGBPointFixture(),
        assignment=assignment,
        output=output,
        asset_manifest_sha256="a" * 64,
    )

    def failed_after_component(self, job, *, start_monotonic):
        module._write(
            output / "component/episode.json",
            {
                "success": False,
                "physical_success": True,
                "diagnostic_complete": True,
                "online_reported_complete": None,
                "executed_actions": 8,
                "model_calls": 5,
                "terminal_reason": None,
                "observation_count": 20,
                "execution_scope": "MUJOCO_COMPONENT_DIAGNOSTIC",
                "status": "COMPONENTS_COMPLETED",
                "physics_steps": 5000,
                "episode_id": "SOFTWARE_ONLY_STATUS_FIXTURE",
            },
        )
        raise TimedOut("injected timeout after component archive")

    monkeypatch.setattr(SimulationWorker, "_run", failed_after_component)
    result = {}
    module.run_worker_episode(assignment, output, result, planner=planner, binding=binding)
    assert result["worker_status"] == "TIMED_OUT"
    assert result["physical_success"] is True
    assert result["status"] == "FAILED"
    assert result["terminal_reason"] == "WORKER_TERMINAL_TIMED_OUT"


def test_qualified_execute_does_not_spend_on_known_missing_native_qualification(
    tmp_path, monkeypatch
):
    module = api()
    monkeypatch.setattr(
        module, "_run_observed_scene", lambda *a, **k: pytest.fail("unqualified paid attempt")
    )
    result = module.run_single_episode(
        output=tmp_path / "out",
        mode="execute",
        profile_id="explicit-profile",
        model_control_db=tmp_path / "db",
        model_directory=tmp_path / "model",
        asset_manifest=tmp_path / "manifest",
        allow_paid=True,
    )
    assert result["status"] == "BLOCKED"
    assert result["blocking_reasons"] == [
        "native_action_metric_and_motion_qualification_unavailable"
    ]
    assert result["model_calls"] == result["executed_actions"] == 0


class CaptureFixture:
    def __init__(self, current):
        self.current = current

    def capture_with_instances(self):
        current = self.current
        return CapturedFrame(
            current, (-1,) * (current.width * current.height), {}, "a" * 64, ("a" * 64,) * 3
        )


@pytest.mark.parametrize("depth,want", [(1.0, "OBSERVED"), (0.0, "UNKNOWN")])
def test_marker_validation_uses_real_decoder_and_preserves_reason(tmp_path, depth, want):
    current = observation(depth=depth)
    result = api().validate_marker_visibility(
        CaptureFixture(current), tmp_path / "frame", registration()
    )
    assert result["status"] == want
    assert result["observation_checksum_sha256"] == current.checksum_sha256
    assert result["continuous_visibility_proven"] is False
    assert (tmp_path / "frame/rgb.png").is_file()
    assert (tmp_path / "frame/marker-validation.json").is_file()
    if want == "UNKNOWN":
        assert result["reason"] == "marker_metric_depth_unavailable"
        assert result["marker_center_world_m"] is None


def test_first_frame_survives_later_failure_without_claiming_task_success(tmp_path, monkeypatch):
    module = api()

    def fail_after_marker(assignment, output, result, **kwargs):
        result["marker_before"] = module.validate_marker_visibility(
            CaptureFixture(observation()), output / "before", registration()
        )
        raise RuntimeError("private token must not enter public failure summary")

    monkeypatch.setattr(module, "_run_observed_scene", fail_after_marker)
    result = module.run_single_episode(output=tmp_path / "out", mode="check-marker")
    assert result["status"] == "FAILED"
    assert result["error_type"] == "RuntimeError"
    assert result["marker_before"]["status"] == "OBSERVED"
    assert result["marker_after"]["status"] == "NOT_RUN"
    assert result["success"] is False
    assert "private token" not in (tmp_path / "out/result.json").read_text()
    manifest = json.loads((tmp_path / "out/evidence-manifest.json").read_text())
    assert any(row["path"] == "before/marker-validation.json" for row in manifest["files"])


def test_plan_only_requires_explicit_credentials_before_render_or_load(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setattr(
        module, "_run_observed_scene", lambda *a, **k: pytest.fail("missing authorization")
    )
    with pytest.raises(ValueError):
        module.run_single_episode(output=tmp_path / "out", mode="plan-only")
    assert not (tmp_path / "out").exists()


def test_cli_default_exits_zero_but_reports_task_not_run(tmp_path):
    module = importlib.import_module("scripts.run_sol_molmo_single_episode")
    assert module.main(["--seed", "42001", "--output", str(tmp_path / "out")]) == 0
    result = json.loads((tmp_path / "out/result.json").read_text())
    assert result["status"] == "PREPARED"
    assert result["success"] is False


def test_deleted_pinned_source_still_publishes_failed_result(tmp_path, monkeypatch):
    import shutil

    module = api()
    root = tmp_path / "source"
    root.mkdir()
    family = module.marker_family("outboard_id7_45mm_v3")
    asset = root / family.asset_path
    asset.parent.mkdir(parents=True)
    shutil.copyfile(module.ROOT / family.asset_path, asset)
    pinned = root / "entry.py"
    pinned.write_text("# pinned source\n")
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "SOURCE_PATHS", ("entry.py",))

    def remove_source(*args, **kwargs):
        pinned.unlink()

    monkeypatch.setattr(module, "_run_observed_scene", remove_source)
    result = module.run_single_episode(output=tmp_path / "out", mode="check-marker")
    assert result["status"] == "FAILED"
    assert result["error_type"] == "SourceDrift"
    assert result["changed_source_paths"] == ["entry.py"]
    assert (tmp_path / "out/evidence-manifest.json").is_file()


def test_interrupt_keeps_explicit_incomplete_state_and_reraises(tmp_path, monkeypatch):
    module = api()

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "_run_observed_scene", interrupt)
    with pytest.raises(KeyboardInterrupt):
        module.run_single_episode(output=tmp_path / "out", mode="check-marker")
    result = json.loads((tmp_path / "out/result.json").read_text())
    assert result["status"] == "INTERRUPTED"
    assert result["error_type"] == "KeyboardInterrupt"
    assert result["success"] is False
    assert (tmp_path / "out/evidence-manifest.json").is_file()


def test_initial_source_failure_is_archived_before_any_observed_run(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setattr(module, "SOURCE_PATHS", ("entry-file-that-does-not-exist.py",))
    monkeypatch.setattr(
        module, "_run_observed_scene", lambda *a, **k: pytest.fail("unbound source entered runtime")
    )
    result = module.run_single_episode(output=tmp_path / "out", mode="check-marker")
    assert result["status"] == "FAILED"
    assert result["error_type"] == "FileNotFoundError"
    assert result["source_snapshot_status"] == "INCOMPLETE"
    assert result["model_calls"] == result["executed_actions"] == 0
    assert (tmp_path / "out/result.json").is_file()
    assert (tmp_path / "out/evidence-manifest.json").is_file()


def selected_profile(tmp_path, *, model="gpt-6.1-sol"):
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    database = tmp_path / "models.db"
    secrets = InMemorySecretStore()
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(database), secret_store=secrets
    )
    profile = service.create_profile(
        display_name="software-only",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name=model,
        base_url="https://api.openai.com",
        api_key="SOFTWARE_ONLY_FIXTURE",
        max_retries=0,
    )
    return database, profile, secrets


def test_selected_sol_database_is_read_only_and_profile_is_not_activated(tmp_path, monkeypatch):
    database, profile, secrets = selected_profile(tmp_path)
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "cloud_edge_robot_arm.model_control.secret_store.create_secret_store", lambda path: secrets
    )
    service = api().selected_sol_service(database, profile.profile_id)
    assert service.get_profile(profile.profile_id).model_name == "gpt-6.1-sol"
    assert service.repository.get_active_profile_id() == ""
    assert hashlib.sha256(database.read_bytes()).hexdigest() == digest


def test_wrong_model_profile_is_rejected_before_reading_credentials(tmp_path, monkeypatch):
    database, profile, _ = selected_profile(tmp_path, model="qwen3.8-max")
    monkeypatch.setattr(
        "cloud_edge_robot_arm.model_control.secret_store.create_secret_store",
        lambda path: pytest.fail("wrong model must not touch credentials"),
    )
    with pytest.raises(ValueError, match="Sol"):
        api().selected_sol_service(database, profile.profile_id)


def test_plan_uses_actual_pipeline_refresh_and_separate_task_result(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_molmo_grounded_planner import SKILLS, request_scene

    database, profile, secrets = selected_profile(tmp_path)
    monkeypatch.setattr(
        "cloud_edge_robot_arm.model_control.secret_store.create_secret_store", lambda path: secrets
    )
    service = api().selected_sol_service(database, profile.profile_id)
    original = request_scene()

    class Points:
        def point(self, observation, phrase):
            coords = "150 410" if phrase == "visible top center of red block" else "650 425"
            return BoundPointResult(
                parse_native_point(f'<points coords="1 1 {coords}">requested support</points>'),
                observation.checksum_sha256,
                observation.evidence()["rgb_sha256"],
                hashlib.sha256(phrase.encode()).hexdigest(),
                {"evidence_scope": "SOFTWARE_ONLY_BOUNDARY_FIXTURE"},
            )

    class PlanCapture:
        def __init__(self):
            self.count = 0
            self._backend = SimpleNamespace(step=self.unexpected_step)

        @staticmethod
        def unexpected_step(**kwargs):
            raise RuntimeError("paused planning refresh must not advance physics")

        def capture(self):
            self.count += 1
            data = original.observation.model_dump() | {
                "frame_id": f"cpu-{self.count}",
                "observation_id": f"cpu-{self.count}",
                "captured_at": datetime.now(UTC),
                "sim_time_s": 0.5,
                "scene_id": "SOFTWARE_ONLY_S01",
                "checksum_sha256": "",
            }
            return RGBDObservation.model_validate(data)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit):
            return json.dumps(
                {
                    "choices": [{"message": {"content": json.dumps({"skills": SKILLS})}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                }
            ).encode()

    class Opener:
        def open(self, request, **kwargs):
            payload = json.loads(request.data)
            assert payload["model"] == "gpt-6.1-sol"
            assert "image_url" not in request.data.decode()
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    result = {"success": False, "cloud_request_reservations": 0}
    capture = PlanCapture()
    api()._plan(
        capture,
        {"instruction": original.user_instruction, "grasp_profile": "mujoco_upright_box_v2"},
        tmp_path / "run",
        result,
        service=service,
        profile_id=profile.profile_id,
        points=Points(),
    )
    assert result["status"] == "PLANNED" and result["planning_passed"] is True
    assert result["success"] is False
    assert result["cloud_requests"] == result["cloud_request_reservations"] == 1
    assert capture.count == 2
    response = json.loads((tmp_path / "run/planning-response.json").read_text())
    assert response["validation"]["passed"] is True
    assert len(response["contract"]["steps"]) == 10
    assert (tmp_path / "run/post-cloud-observation/observation.json").is_file()
