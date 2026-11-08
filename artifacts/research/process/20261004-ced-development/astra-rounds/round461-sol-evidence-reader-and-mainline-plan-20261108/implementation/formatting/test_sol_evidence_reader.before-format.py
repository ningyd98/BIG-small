"""SOFTWARE_ONLY_READER_TEST: synthetic bytes, no probe or physical qualification.

Production schema labels inside tmp_path are deliberately parsed as test data.
The outer fixture marker always records that HTTP, rendering and physics are zero.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import shutil
import socket
import struct
import urllib.request
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest
from PIL import Image
from scripts import probe_rgbd_roles as probe

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.research import freeze_evidence as reader
from cloud_edge_robot_arm.research.protocol_evidence import _observation
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_evidence,
    sample_physical_observation,
)
from cloud_edge_robot_arm.vision.capture import CapturedFrame, save_captured_frame
from cloud_edge_robot_arm.vision.messages import build_visual_messages
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot, resolve_visual_planner
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter, VisualDecision, compatible_messages
from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    RoleProviderSnapshot,
    cloud_request_settings,
    configuration_hash,
)
from cloud_edge_robot_arm.vision.supervision import SupervisionContext
from tests.test_protocol_evidence_generation import episode_header, fixture_scope, inputs
from tests.test_raw_episode_v3 import state
from tests.test_rgbd_normalized_protocol import REQUIRED_SKILLS

MODEL = "gpt-6.1-sol"
INSTRUCTION = "Move the red block to the green region."
NOW = datetime(2026, 11, 8, tzinfo=UTC)
ROUTES = (
    ("https://api.openai.com", "/v1/chat/completions"),
    ("https://api.openai.com/v1", "/chat/completions"),
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@pytest.fixture(autouse=True)
def _no_external_effects(monkeypatch):
    import mujoco

    def forbidden(*args, **kwargs):
        pytest.fail("SOFTWARE_ONLY_READER_TEST attempted network/renderer/engine")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(urllib.request, "build_opener", forbidden)
    monkeypatch.setattr(MuJoCoPhysicsBackend, "__init__", forbidden)
    for name in ("Renderer", "MjModel", "MjData", "mj_step", "mj_forward"):
        monkeypatch.setattr(mujoco, name, forbidden)


def _frame(index=0):
    # Seven-pixel top patch at z=.28, ring support at z=.20; no instance
    # information enters the production grounder. IDs are offline checks only.
    image = Image.new("RGB", (320, 240), (100, 100, 100))
    depths = [1.08] * (320 * 240)
    ids = [0] * (320 * 240)
    for y in range(117, 124):
        for x in range(77, 84):
            image.putpixel((x, y), (220, 30, 20))
            depths[y * 320 + x] = 1.0
            ids[y * 320 + x] = 11
    for y in range(114, 127):
        for x in range(233, 246):
            image.putpixel((x, y), (20, 220, 30))
            ids[y * 320 + x] = 12
    png = io.BytesIO()
    image.save(png, format="PNG")
    observation = RGBDObservation(
        frame_id=f"software-reader-{index}",
        episode_id="software-reader-episode",
        scene_id="SOFTWARE_ONLY_READER_TEST",
        calibration_version="SOFTWARE_ONLY_READER_TEST",
        captured_at=NOW,
        sim_time_s=0,
        width=320,
        height=240,
        rgb_png_base64=base64.b64encode(png.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<76800f", *depths)).decode(),
        intrinsics=(300, 300, 160, 120),
        camera_to_world=(1, 0, 0, .3, 0, -1, 0, .1, 0, 0, -1, 1.28, 0, 0, 0, 1),
        source="mujoco_camera",
    )
    return CapturedFrame(
        observation,
        tuple(ids),
        {0: "table", 11: "object_geom", 12: "target_region_geom"},
        "software-state",
        ("software-state",) * 3,
    )


def _snapshot(model=MODEL, generation=None, route=ROUTES[0]):
    return ModelConfigSnapshot(
        provider="openai_compatible",
        model=model,
        endpoint=route[0],
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters=(
            {"reasoning_effort": "low", "max_completion_tokens": 4096}
            if generation is None else generation
        ),
        timeout_s=180,
        coordinate_system="normalized_1000",
        grasp_profile="mujoco_upright_box_v2",
    )


def _planner(snapshot=None, route=ROUTES[0]):
    return resolve_visual_planner(
        snapshot or _snapshot(route=route), chat_path=route[1], api_key="", allow_paid=True
    )


def _request(frame):
    return InitialPlanningRequest(
        request_id="SOFTWARE_ONLY_READER_TEST",
        user_instruction=INSTRUCTION,
        scene=SceneSummary(scene_version=1, updated_at=NOW),
        observation=frame.observation,
    )


def _wire(monkeypatch):
    rows = []
    reply = json.dumps({
        "choices": [{"message": {"content": json.dumps({
            "target_pixel": [250, 500],
            "destination_pixel": [750, 500],
            "target_label": "red block",
            "reported_confidence": .9,
            "skills": REQUIRED_SKILLS,
            "reason": "SOFTWARE_ONLY_READER_TEST visible surfaces",
        })}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32},
    }).encode()

    class Boundary:
        def open(self, request, timeout):
            rows.append(request.data)
            return io.BytesIO(reply)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Boundary())
    return rows


def _seal(directory, report):
    _write(directory / "role-probe-report.json", report)
    (directory / "role-probe-report.sha256").write_text(
        _sha((directory / "role-probe-report.json").read_bytes()) + "\n"
    )


def _nominal(directory, monkeypatch, *, snapshot=None, route=ROUTES[0]):
    directory.mkdir()
    _write(directory / "SOFTWARE_ONLY_READER_TEST.json", {
        "scope": "SOFTWARE_ONLY_READER_TEST", "actual_HTTP": 0,
        "engine": 0, "render": 0, "physical_acceptance": False,
        "internal_schema_labels": "synthetic parser inputs, never real probe evidence",
    })
    planner = _planner(snapshot, route)
    settings = cloud_request_settings(planner)
    config = probe.read_role_config(probe.ROOT / "configs/research/ced_roles.yaml")
    config["cloud"]["model_family"] = settings["model"]
    config["probe"]["instruction"] = INSTRUCTION
    config_path = directory / "software-config.json"
    _write(config_path, config)  # JSON is valid YAML; frozen as a tmp_path fixture.
    cloud = RoleProviderSnapshot(
        role="CLOUD", provider_id="SOFTWARE_ONLY_READER_TEST",
        provider_location="REMOTE_SERVICE", model_id=settings["model"],
        revision=None, weight_digest=None, quantization=None,
        request_config_hash=configuration_hash(settings), source_hashes=probe.source_fingerprints(),
    )
    edge_config = config["edge"]
    edge = RoleProviderSnapshot(
        role="EDGE", provider_id=edge_config["provider_id"], provider_location="LOCAL_HOST",
        model_id=None, revision=None, weight_digest=None, quantization=None,
        request_config_hash=configuration_hash(edge_config["policy"]),
        source_hashes=probe._hash_sources(edge_config["source_paths"]),
    )
    sources = probe._hash_sources(config["device"]["source_paths"])
    bundle = RoleModelBundle(cloud, edge.provider_id, edge.digest(), configuration_hash(sources))
    rows = _wire(monkeypatch)
    attempts = [
        probe._attempt(planner, _request(frame), frame, directory, i, cloud)
        for i in range(4) for frame in [_frame(i)]
    ]
    assert len(rows) == 4
    for attempt in attempts:
        assert attempt["status"] == "COMPLETE", attempt
        assert all(attempt[k] for k in ("parsed", "grounded", "target_hit", "destination_hit")), (
            attempt.get("observation_evidence"), attempt.get("parse_error")
        )
        assert attempt["observation_evidence"]["estimated_object_height_m"] == pytest.approx(.08)
    report = dict(
        schema_version="ced.role-probe.v1", status="PASS", scope="NOMINAL_PROBE_ONLY",
        source="mujoco_camera", transport="REAL_HTTP", physical_acceptance=False,
        edge_acceptance=False, dispatch=False,
        config_path=str(config_path), config_sha256=_sha(config_path.read_bytes()),
        probe_config=config["probe"], bundle=bundle.evidence(), bundle_hash=bundle.digest(),
        edge_snapshot=edge.evidence(), edge_policy=edge_config["policy"],
        device_source_hashes=sources, request_settings=settings, final_request_settings=settings,
        capture={"synchronized": True, "image_size": [320, 240]}, attempts=attempts,
        planned_attempt_count=4, unexecuted_attempt_count=0,
    )
    assert probe.can_accept_role_probe(report), "complete synthetic fixture failed production gate"
    _write(directory / "roles-frozen.json", bundle.evidence())
    _seal(directory, report)
    return report


def _clone(source, destination):
    shutil.copytree(source, destination)
    return json.loads((destination / "role-probe-report.json").read_text())


def _persist_attempt(directory, report):
    _write(directory / "attempt-00/attempt.json", report["attempts"][0])
    _seal(directory, report)


def _rewrite_request(directory, report, body):
    raw = json.dumps(body).encode()
    attempt = report["attempts"][0]
    (directory / "attempt-00/request.raw").write_bytes(raw)
    _write(directory / "attempt-00/request.json", body)
    attempt["request_sha256"] = _sha(raw)
    attempt["serialized_sent_bytes"] = len(raw)
    attempt["request_summary"] = probe.summarize_role_request(body)
    attempt["expected_request_summary"] = attempt["request_summary"]
    costs = attempt["cost_ledger"]
    row = costs["requests"][0]
    costs["summary"]["application_bytes"] += len(raw) - row["serialized_sent_bytes"]
    row["serialized_sent_bytes"] = len(raw)
    _persist_attempt(directory, report)


def _planner_body(observation, settings):
    messages = build_visual_messages(
        INSTRUCTION, observation, image_size=(320, 240), coordinate_system="normalized_1000",
        decision_schema=VisualDecision.model_json_schema(),
    )
    generation = settings["generation_parameters"]
    fields = (
        dict(generation) if settings["model"] == MODEL
        else {"temperature": generation["temperature"], "max_tokens": generation["num_predict"]}
    )
    if "think" in generation:
        fields["enable_thinking"] = generation["think"]
    return {"model": settings["model"], "messages": compatible_messages(messages),
            **fields, "response_format": {"type": "json_object"}}


def _supervisor_body(observation, snapshot, route=ROUTES[0]):
    context = SupervisionContext(
        episode_id=observation.episode_id, observation_id=observation.observation_id,
        captured_at=observation.captured_at, task_instruction=INSTRUCTION,
        plan_version=1, state_version=1, next_step_id="step-1", next_skill="HOME",
        proprioception={"gripper_open": True},
    )
    captured = []

    class Captured(Exception):
        pass

    class Compiler(RGBDPlannerAdapter):
        def _request_visual(self, messages, decision_schema):
            captured.append(compatible_messages(messages))
            raise Captured

    compiler = Compiler(
        model=snapshot.model, provider=snapshot.provider, base_url=route[0],
        chat_path=route[1], model_snapshot=snapshot, allow_paid=False, api_key="",
    )
    with pytest.raises(Captured):
        compiler.supervise(observation, context)
    assert len(captured) == 1
    body = _planner_body(observation, cloud_request_settings(_planner(snapshot, route)))
    body["messages"] = captured[0]
    return body


def _ced_case(directory, body, probe_report, observation):
    """Complete synthetic failed episode: audits run, no physical success is invented."""
    directory.mkdir()
    _write(directory / "SOFTWARE_ONLY_READER_TEST.json", {"physics": 0, "scope": "SOFTWARE_ONLY"})
    base = inputs(directory)["formal"][0]
    parameters = copy.deepcopy(base["scene"]["scene_parameters"])
    parameters["target"].update(color_name="red", rgba=[.9, .12, .08, 1.0])
    registered = SceneSpec.from_parameters(parameters, base["scene"]["asset_family_hash"], base["scene"]["seed"])
    base.update(scene=registered.model_dump(), scene_hash=registered.scene_hash)
    scene = base["scene"]["scene_parameters"]
    assignment = {"base_assignment": base, "stratum_id": "STATIC_RTT0", "period_s": 1.0}
    joints = [-.8, 0, 0, 0, 0, 0, 0]
    raw = []
    for i in range(122):
        row = state(i)
        row.update(
            episode_id=observation.episode_id, sim_time_s=i * .002,
            object_position_m=scene["target"]["position"],
            object_geom_position_m=scene["target"]["position"],
            object_half_extent_m=scene["target"]["half_size"],
            region_center_m=scene["destination"]["position"],
            region_half_extent_m=scene["destination"]["half_size"],
            joint_positions_rad=joints,
            self_collision_distances_m=[(a, b, .1) for a, b in fixture_scope()],
        )
        raw.append(row)
    header = episode_header(base, raw) | {
        "pilot_assignment_hash": content_digest(assignment),
        "role_bundle_hash": probe_report["bundle_hash"],
        "evaluation_start_step": 120,
        "initial_controller_targets": {"joints_rad": joints, "fingers_m": [.039, .039]},
        "actuator_delay_steps": 0,
    }
    samples = [sample_physical_observation(_observation(row), CompletionCriteria("object", "target_region"))
               for row in raw[120:]]
    outcome = evaluate_evidence(samples, CompletionCriteria("object", "target_region"), evaluation_start_step=120)
    assert outcome.success is False
    request_raw = json.dumps(body).encode()
    response_raw = b'{"SOFTWARE_ONLY_READER_TEST": true}'
    version = reader._model_evidence_hash(probe_report["request_settings"])
    cost = dict(
        request_id="software-ced-wire", model_role="PLANNER", provider_version=version,
        sent_at=NOW.isoformat(), finished_at=NOW.isoformat(), is_cloud_model=True,
        deployment="CLOUD", provider_location="REMOTE_SERVICE", status="SUCCESS",
        serialized_sent_bytes=len(request_raw), serialized_received_bytes=len(response_raw),
        monetary_cost=None,
    )
    costs = {"requests": [cost], "summary": {
        "cloud_model_requests": 1, "application_bytes": len(request_raw) + len(response_raw)
    }}
    result = dict(scope="REAL_RUNTIME", status=outcome.status, success=False,
                  costs=costs["summary"], cloud_requests=1, wall_duration_s=1.0)
    wire = dict(
        request_id=cost["request_id"], model_role="PLANNER", provider_version=version,
        request_path="request.raw", response_path="response.raw", response_present=True,
        request_sha256=_sha(request_raw), response_sha256=_sha(response_raw),
        serialized_sent_bytes=len(request_raw), serialized_received_bytes=len(response_raw),
        response_request_id=cost["request_id"], response_model_role="PLANNER",
        response_provider_version=version,
    )
    for name, value in {
        "assignment": assignment, "case-result": result, "context": header,
        "physical-observations": raw, "commands": [],
        "actuator-steps": [dict(
            physics_step=i, episode_id=observation.episode_id, sim_time_s=(i-1)*.002,
            pre_joint_positions_rad=joints, actuator_gains=[1.0]*7,
            actuator_ctrl_ranges=[[-2.8, 2.8]]*7, pre_gravity_bias_nm=[0.0]*7,
            control_rad=joints, applied_joint_targets_rad=joints,
            finger_control_targets_m=[.039, .039],
        ) for i in range(1, 122)],
        "physical-evidence": [asdict(s) for s in samples], "physical-outcome": asdict(outcome),
        "episode": dict(
            episode_id=observation.episode_id, physical_success=False, status=outcome.status,
            online_reported_complete=False, terminal_reason="software fixture incomplete",
            success=False, verification_records=[dict(
                layer="OBSERVATION", observation_id=observation.observation_id,
                checksum_sha256=observation.checksum_sha256,
            )],
        ),
        "policy": dict(
            instruction=INSTRUCTION, device_pipeline="OPENCV", model_snapshot_hash=version,
            role_binding={k: probe_report[k] for k in (
                "bundle", "edge_snapshot", "device_source_hashes", "edge_policy")},
            verification_budget=probe_report["edge_policy"]["verification_budget"],
            supervision_period_s=1.0, advance_physics_during_wait=True,
        ),
        "wire-index": [wire], "costs": costs,
    }.items():
        _write(directory / f"{name}.json", value)
    (directory / "request.raw").write_bytes(request_raw)
    (directory / "response.raw").write_bytes(response_raw)
    frames = directory / "frames/frame-0"
    frames.mkdir(parents=True)
    save_captured_frame(replace(_frame(), observation=observation), frames)
    return assignment, result


def test_sol_nominal_reader_reconstructs_original_wire(tmp_path, monkeypatch):
    # Catches obsolete generation reconstruction or a placeholder Sol identity.
    source = tmp_path / "nominal"
    _nominal(source, monkeypatch)
    result = reader.verify_role_probe_evidence(source)
    assert result["available"], result["errors"]
    assert len(result["report"]["attempts"]) == 4
    assert result["scope"] == "NOMINAL_PROBE_ONLY"
    assert result["physical_acceptance"] is result["edge_acceptance"] is False
    for damage in ("request.raw", "response.raw", "rgb.png", "passes", "cost"):
        damaged = tmp_path / damage
        report = _clone(source, damaged)
        case = damaged / "attempt-00"
        if damage in {"request.raw", "response.raw", "rgb.png"}:
            with (case / damage).open("ab") as stream:
                stream.write(b"corrupt")
        elif damage == "passes":
            metadata = json.loads((case / "observation.json").read_text())
            metadata["pass_state_hashes"][1] = "foreign"
            _write(case / "observation.json", metadata)
        else:
            report["attempts"][0]["cost_ledger"]["requests"][0]["provider_version"] = "foreign"
            _persist_attempt(damaged, report)
        assert not reader.verify_role_probe_evidence(damaged)["available"], damage


def test_sol_b0_planner_reconstructs_original_wire():
    # Catches subset matching and any replacement of prompt/image/model bytes.
    observation = _frame().observation
    settings = cloud_request_settings(_planner())
    body = _planner_body(observation, settings)
    assert reader._verify_b0_request_body(body, "PLANNER", observation, INSTRUCTION, settings) is None
    for damage in ("task", "image", "model", "extra"):
        bad = copy.deepcopy(body)
        if damage == "task":
            bad["messages"][1]["content"][0]["text"] += " foreign task"
        elif damage == "image":
            bad["messages"][1]["content"][1]["image_url"]["url"] = "data:image/png;base64,AAAA"
        elif damage == "model":
            bad["model"] = "foreign-model"
        else:
            bad["unknown_field"] = True
        with pytest.raises(ValueError):
            reader._verify_b0_request_body(bad, "PLANNER", observation, INSTRUCTION, settings)


def test_sol_b0_supervisor_compiles_without_transport(monkeypatch):
    # Catches the compiler's default Ollama/localhost identity before transport.
    observation = _frame().observation
    transports = []

    def forbidden_post(*args, **kwargs):
        transports.append(args)
        pytest.fail("reader compilation reached transport")

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", forbidden_post)
    for route in ROUTES:
        snapshot = _snapshot(route=route)
        settings = cloud_request_settings(_planner(snapshot, route))
        body = _supervisor_body(observation, snapshot, route)
        assert reader._verify_b0_request_body(body, "SUPERVISOR", observation, INSTRUCTION, settings) is None
        for field, value in (
            ("observation_id", "foreign-frame"), ("episode_id", "foreign-episode"),
            ("task_instruction", "foreign instruction"),
        ):
            bad = copy.deepcopy(body)
            text = bad["messages"][1]["content"][0]["text"]
            prefix = "Inspect the current task and robot state. "
            context, end = json.JSONDecoder().raw_decode(text[len(prefix):])
            context[field] = value
            bad["messages"][1]["content"][0]["text"] = prefix + json.dumps(context) + text[len(prefix)+end:]
            with pytest.raises(ValueError):
                reader._verify_b0_request_body(bad, "SUPERVISOR", observation, INSTRUCTION, settings)
        with pytest.raises(ValueError):
            reader._verify_b0_request_body(body, "PLANNER", observation, INSTRUCTION, settings)
    assert transports == []


def test_recorded_generation_gate_rejects_effective_field_drift(tmp_path, monkeypatch):
    # Catches default-filled missing evidence and a CED gate that ignores extra fields.
    fields = getattr(reader, "_recorded_chat_fields", None)
    assert callable(fields), "new narrowly scoped helper absent: _recorded_chat_fields"
    for effort, budget in (("low", 4096), ("medium", 8192), ("high", 1), ("xhigh", 32768), ("max", 512)):
        settings = cloud_request_settings(_planner(_snapshot(generation={
            "reasoning_effort": effort, "max_completion_tokens": budget,
        })))
        assert fields(settings) == {
            "model": MODEL, "reasoning_effort": effort, "max_completion_tokens": budget,
            "response_format": {"type": "json_object"},
        }
    settings = cloud_request_settings(_planner())
    for generation in ({}, {"reasoning_effort": "low"}, {"max_completion_tokens": 4096},
                       {"reasoning_effort": "low", "max_completion_tokens": True},
                       {"reasoning_effort": "low", "max_completion_tokens": 4096, "temperature": 0}):
        bad = copy.deepcopy(settings)
        bad["generation_parameters"] = generation
        with pytest.raises((ValueError, KeyError, TypeError)):
            fields(bad)
    for response_format in (None, {"type": "text"}, {"type": "json_object", "extra": True}):
        with pytest.raises(ValueError):
            fields(settings | {"response_format": response_format})
    for index, generation in enumerate((
        {"reasoning_effort": "low", "max_completion_tokens": 4096},
        {"reasoning_effort": "medium", "max_completion_tokens": 8192},
    )):
        snapshot = _snapshot(generation=generation)
        source = tmp_path / f"nominal-{index}"
        report = _nominal(source, monkeypatch, snapshot=snapshot)
        assert reader.verify_role_probe_evidence(source)["available"]
        observation = _frame().observation
        settings = report["request_settings"]
        planner_body = _planner_body(observation, settings)
        supervisor_body = _supervisor_body(observation, snapshot)
        case = tmp_path / f"ced-{index}"
        assignment, row = _ced_case(case, planner_body, report, observation)
        assert reader._audit_ced_case(case, assignment, row, report)["success"] is False
        mutations = {
            "reasoning_effort": "high", "max_completion_tokens": generation["max_completion_tokens"]+1,
            "temperature": 0, "max_tokens": 512, "enable_thinking": False, "extra": True,
        }
        for field, value in mutations.items():
            for role, original in (("PLANNER", planner_body), ("SUPERVISOR", supervisor_body)):
                bad = copy.deepcopy(original) | {field: value}
                with pytest.raises(ValueError):
                    reader._verify_b0_request_body(bad, role, observation, INSTRUCTION, settings)
            damaged = tmp_path / f"nominal-drift-{index}-{field}"
            copied = _clone(source, damaged)
            original = json.loads((damaged / "attempt-00/request.raw").read_bytes())
            _rewrite_request(damaged, copied, original | {field: value})
            rejected = reader.verify_role_probe_evidence(damaged)
            assert not rejected["available"] and any("frozen frame/prompt/settings" in e for e in rejected["errors"])
            # Rebuild every surrounding wire hash/length/cost to force semantic rejection.
            mutated = copy.deepcopy(planner_body) | {field: value}
            raw = json.dumps(mutated).encode()
            (case / "request.raw").write_bytes(raw)
            wire = json.loads((case / "wire-index.json").read_text())
            costs = json.loads((case / "costs.json").read_text())
            difference = len(raw) - costs["requests"][0]["serialized_sent_bytes"]
            wire[0].update(request_sha256=_sha(raw), serialized_sent_bytes=len(raw))
            costs["requests"][0]["serialized_sent_bytes"] = len(raw)
            costs["summary"]["application_bytes"] += difference
            row["costs"] = costs["summary"]
            _write(case / "wire-index.json", wire)
            _write(case / "costs.json", costs)
            _write(case / "case-result.json", row)
            with pytest.raises(ValueError, match="actual model wire differs"):
                reader._audit_ced_case(case, assignment, row, report)


def test_offline_sol_identity_binds_official_route(tmp_path, monkeypatch):
    # Catches replacing a recorded bad identity with a valid but unrelated URL.
    kwargs_for = getattr(reader, "_offline_reader_adapter_kwargs", None)
    assert callable(kwargs_for), "new narrowly scoped helper absent: _offline_reader_adapter_kwargs"
    for index, route in enumerate(ROUTES):
        snapshot = _snapshot(route=route)
        settings = cloud_request_settings(_planner(snapshot, route))
        kwargs = kwargs_for(settings)
        assert kwargs == {
            "model": MODEL, "provider": "openai_compatible", "base_url": route[0],
            "chat_path": route[1], "api_key": "", "allow_paid": False,
        }
        original = tmp_path / f"route-{index}"
        _nominal(original, monkeypatch, snapshot=snapshot, route=route)
        assert reader.verify_role_probe_evidence(original)["available"]
        observation = _frame().observation
        body = _supervisor_body(observation, snapshot, route)
        assert reader._verify_b0_request_body(body, "SUPERVISOR", observation, INSTRUCTION, settings) is None
        for change in (
            {"endpoint_hash": "a"*64}, {"chat_path": ROUTES[1-index][1]},
            {"provider": "ollama"}, {"endpoint_hash": _sha(b"https://unofficial.example")},
        ):
            with pytest.raises(ValueError):
                kwargs_for(settings | change)
            with pytest.raises(ValueError):
                reader._verify_b0_request_body(body, "SUPERVISOR", observation, INSTRUCTION, settings | change)
            damaged = tmp_path / f"bad-route-{index}-{len(list(tmp_path.iterdir()))}"
            report = _clone(original, damaged)
            report["request_settings"] |= change
            _seal(damaged, report)
            assert not reader.verify_role_probe_evidence(damaged)["available"]


def test_qwen_reader_retains_think_and_raw_cost_checks(tmp_path, monkeypatch):
    # Catches losing enable_thinking while keeping legacy raw/cost/source guards.
    for think in (False, None):
        generation = {"temperature": 0, "num_predict": 512}
        if think is not None:
            generation["think"] = think
        snapshot = _snapshot(model="qwen3.8-max", generation=generation)
        source = tmp_path / f"qwen-{think}"
        report = _nominal(source, monkeypatch, snapshot=snapshot)
        result = reader.verify_role_probe_evidence(source)
        assert result["available"], result["errors"]
        settings = report["request_settings"]
        observation = _frame().observation
        body = _planner_body(observation, settings)
        assert reader._verify_b0_request_body(body, "PLANNER", observation, INSTRUCTION, settings) is None
        # The preexisting direct B0 fixture omits chat_path.
        legacy_settings = dict(settings)
        legacy_settings.pop("chat_path")
        assert reader._verify_b0_request_body(body, "PLANNER", observation, INSTRUCTION, legacy_settings) is None
        for missing in ("temperature", "num_predict"):
            changed = copy.deepcopy(settings)
            changed["generation_parameters"].pop(missing)
            with pytest.raises((ValueError, KeyError)):
                reader._recorded_chat_fields(changed)
        for damage in ("thinking", "identity", "length", "response", "source"):
            damaged = tmp_path / f"qwen-{think}-{damage}"
            copied = _clone(source, damaged)
            if damage == "thinking":
                _rewrite_request(damaged, copied, body | {"enable_thinking": True})
            elif damage == "response":
                (damaged / "attempt-00/response.raw").unlink()
            elif damage == "source":
                copied["bundle"]["cloud_snapshot"]["source_hashes"]["scripts/probe_rgbd_roles.py"] = "a"*64
                _write(damaged / "roles-frozen.json", copied["bundle"])
                _seal(damaged, copied)
            else:
                row = copied["attempts"][0]["cost_ledger"]["requests"][0]
                row["model_role" if damage == "identity" else "serialized_sent_bytes"] = (
                    "SUPERVISOR" if damage == "identity" else row["serialized_sent_bytes"]+1
                )
                _persist_attempt(damaged, copied)
            assert not reader.verify_role_probe_evidence(damaged)["available"], damage
