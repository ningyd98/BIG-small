"""Versioned role/stage evidence is required; software cannot publish INITIAL."""

import importlib
import json

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.protocol import FrozenProtocol, ProtocolSpec, load_protocol


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.freeze_evidence")


def test_v2_spec_and_reader_preserve_legacy_entry_and_hash_semantics(tmp_path):
    spec = ProtocolSpec(
        schema_version="ced.research.v2",
        tcap_s=120,
        pool_hashes={"fixture": "a" * 64},
        model_snapshot_hash="b" * 64,
        role_bundle_hash="b" * 64,
        selection_manifest_hash="c" * 64,
        selected_b0_period_s=2.0,
        budget_selection_rule_hash="d" * 64,
        resource_plan_hash="0" * 64,
        opportunity_hash="e" * 64,
        recovery_fault_manifest_hash="f" * 64,
    )
    frozen = FrozenProtocol(
        spec=spec,
        stage="INITIAL",
        content_hash=content_digest({"spec": spec.model_dump(mode="json"), "stage": "INITIAL"}),
    )
    directory = tmp_path / "reader-only"
    directory.mkdir()
    (directory / "protocol.json").write_text(frozen.model_dump_json())
    assert load_protocol(directory) == frozen
    assert ProtocolSpec().schema_version == "rgbd.research.v1"


def test_role_probe_reader_missing_or_forged_summary_unavailable(tmp_path):
    reader = api().verify_role_probe_evidence
    assert reader(tmp_path)["available"] is False
    payload = {
        "schema_version": "ced.role-probe.v1",
        "status": "PASS",
        "physical_acceptance": True,
        "source": "mujoco_camera",
        "transport": "REAL_HTTP",
        "attempts": [],
    }
    (tmp_path / "role-probe-report.json").write_text(json.dumps(payload))
    result = reader(tmp_path)
    assert result["available"] is False and result["physical_acceptance"] is False
    assert result["edge_acceptance"] is False
    assert result["errors"]


def test_role_reader_rejects_symlinked_original_report(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    directory = tmp_path / "probe"
    directory.mkdir()
    (directory / "role-probe-report.json").symlink_to(outside)
    assert api().verify_role_probe_evidence(directory)["available"] is False


@pytest.mark.parametrize("scope", ["SOFTWARE_ONLY", "UNVERIFIED"])
def test_v2_summary_cannot_freeze_without_real_stage_raw_sources(tmp_path, scope):
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.pilot-stage.v1",
                "protocol_version": "ced.research.v2",
                "stage": "foundation",
                "scope": scope,
                "method_id": "B0",
                "assigned": 120,
                "recorded": 120,
                "freeze_ready": True,
                "accepted_success": 120,
                "selected_period_s": 2.0,
            }
        )
    )
    with pytest.raises((ValueError, OSError)):
        api().initial_spec_from_evidence(tmp_path)


def test_v2_settings_cannot_override_role_selection_or_budget_evidence():
    from scripts.freeze_rgbd_protocol import apply_settings

    for field in (
        "role_bundle_hash",
        "selection_manifest_hash",
        "selected_b0_period_s",
        "budget_selection_rule_hash",
        "resource_plan_hash",
    ):
        with pytest.raises(ValueError, match="override"):
            apply_settings(ProtocolSpec(tcap_s=120), {field: "a" * 64})


def test_legacy_v1_payload_has_no_new_fields_or_hash_drift():
    spec = ProtocolSpec(tcap_s=120)
    assert "role_bundle_hash" not in spec.model_dump(mode="json")
    assert "selection_manifest_hash" not in spec.model_dump(mode="json")
    assert "resource_plan_hash" not in spec.model_dump(mode="json")
    assert ProtocolSpec.model_validate(spec.model_dump()) == spec


def test_actual_auditor_rejects_software_stage_even_if_summary_relabels_success(tmp_path):
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.pilot-stage.v1",
                "protocol_version": "ced.research.v2",
                "stage": "selection",
                "scope": "SOFTWARE_ONLY",
                "execution_mode": "REAL_RUNTIME",
                "accepted_success": 480,
            }
        )
    )
    result = api().audit_ced_pilot_stage(tmp_path, "selection")
    assert result["available"] is False and result["accepted_success"] == 0


def actuator_fixture(tmp_path):
    from types import SimpleNamespace

    raw = [
        SimpleNamespace(
            episode_id="SOFTWARE_ONLY", sim_time_s=i * 0.002, joint_positions_rad=(0.0,) * 7
        )
        for i in range(3)
    ]
    controls = [
        {
            "physics_step": i,
            "episode_id": "SOFTWARE_ONLY",
            "sim_time_s": (i - 1) * 0.002,
            "pre_joint_positions_rad": [0.0] * 7,
            "actuator_gains": [1.0] * 7,
            "actuator_ctrl_ranges": [[-2.0, 2.0]] * 7,
            "pre_gravity_bias_nm": [0.0] * 7,
            "control_rad": [0.05] * 7,
            "applied_joint_targets_rad": [0.05] * 7,
            "finger_control_targets_m": [0.039, 0.039],
        }
        for i in (1, 2)
    ]
    command = {
        "command_seq": 1,
        "physics_step": 0,
        "episode_id": "SOFTWARE_ONLY",
        "sim_time_s": 0.0,
        "type": "joint_target",
        "accepted": True,
        "target_positions_rad": [0.05] * 7,
        "applied_target_positions_rad": [0.05] * 7,
    }
    (tmp_path / "commands.json").write_text(json.dumps([command]))
    (tmp_path / "actuator-steps.json").write_text(json.dumps(controls))
    header = {
        "initial_controller_targets": {"joints_rad": [0.0] * 7, "fingers_m": [0.039] * 2},
        "actuator_delay_steps": 0,
    }
    return raw, controls, header


def test_pure_controller_reconstruction_does_not_accept_physical_task(tmp_path):
    raw, _, header = actuator_fixture(tmp_path)
    assert api()._audit_actuators(tmp_path, raw, header) is None
    # This only verifies numeric command/controller alignment; no research/physics verdict exists.


@pytest.mark.parametrize("damage", ["prefix", "omit", "episode", "target", "control", "prestate"])
def test_controller_reconstruction_rejects_missing_or_mismatched_raw_steps(tmp_path, damage):
    raw, controls, header = actuator_fixture(tmp_path)
    if damage == "prefix":
        commands = json.loads((tmp_path / "commands.json").read_text())
        commands[0]["command_seq"] = 2
        (tmp_path / "commands.json").write_text(json.dumps(commands))
    elif damage == "omit":
        controls.pop()
    elif damage == "episode":
        controls[0]["episode_id"] = "foreign"
    elif damage == "target":
        controls[0]["applied_joint_targets_rad"][0] = 0.5
    elif damage == "control":
        controls[0]["control_rad"][0] = 0.5
    else:
        controls[0]["pre_joint_positions_rad"][0] = 0.5
    (tmp_path / "actuator-steps.json").write_text(json.dumps(controls))
    with pytest.raises(ValueError):
        api()._audit_actuators(tmp_path, raw, header)


def test_role_reader_derives_exact_legacy_model_digest_from_effective_settings():
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.role_models import cloud_request_settings

    model = ModelConfigSnapshot(
        provider="openai_compatible",
        model="qwen3.8-max",
        endpoint="https://example.invalid",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0.0, "num_predict": 512},
        timeout_s=30.0,
        grasp_profile="mujoco_upright_box_v2",
    )
    settings = cloud_request_settings(resolve_visual_planner(model, allow_paid=False))
    assert api()._model_evidence(settings) == model.evidence()
    assert api()._model_evidence_hash(settings) == model.digest()


def test_stage_source_inventory_cannot_be_narrowed_before_raw_audit(tmp_path, monkeypatch):
    import hashlib

    module = api()
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.pilot-stage.v1",
                "protocol_version": "ced.research.v2",
                "stage": "selection",
                "scope": "UNVERIFIED",
                "execution_mode": "REAL_RUNTIME",
            }
        )
    )
    name = "src/cloud_edge_robot_arm/research/pilot.py"
    original = __import__("pathlib").Path(name).read_bytes()
    archived = tmp_path / "source" / name
    archived.parent.mkdir(parents=True)
    archived.write_bytes(original)
    (tmp_path / "source-hashes.json").write_text(
        json.dumps({name: hashlib.sha256(original).hexdigest()})
    )

    def should_not_reach_probe(_):
        raise AssertionError("narrow source inventory reached the role probe")

    monkeypatch.setattr(module, "verify_role_probe_evidence", should_not_reach_probe)
    result = module.audit_ced_pilot_stage(tmp_path, "selection")
    assert result["available"] is False
    assert "source inventory" in " ".join(result["errors"])


@pytest.mark.parametrize("damage", [None, "object", "extent", "destination", "controller"])
def test_raw_reset_must_identify_the_assigned_scene_and_reference_controller(damage):
    from types import SimpleNamespace

    scene = {
        "scene_parameters": {
            "target": {"position": [0.45, 0.1, 0.44], "half_size": [0.03, 0.03, 0.03]},
            "destination": {"position": [0.45, -0.1, 0.43], "half_size": [0.07, 0.07, 0.003]},
        }
    }
    raw = [
        SimpleNamespace(
            object_position_m=(0.45, 0.1, 0.44),
            object_half_extent_m=(0.03, 0.03, 0.03),
            region_center_m=(0.45, -0.1, 0.43),
            region_half_extent_m=(0.07, 0.07, 0.003),
            joint_positions_rad=(-0.8, 0, 0, 0, 0, 0, 0),
        )
    ]
    header = {
        "initial_controller_targets": {
            "joints_rad": [-0.8, 0, 0, 0, 0, 0, 0],
            "fingers_m": [0.039, 0.039],
        }
    }
    if damage == "object":
        raw[0].object_position_m = (0.7, 0.1, 0.44)
    elif damage == "extent":
        raw[0].object_half_extent_m = (0.06, 0.03, 0.03)
    elif damage == "destination":
        raw[0].region_center_m = (0.8, -0.1, 0.43)
    elif damage == "controller":
        header["initial_controller_targets"]["joints_rad"][0] = 0
    if damage is None:
        assert api()._audit_ced_reset(raw, header, scene) is None
    else:
        with pytest.raises(ValueError):
            api()._audit_ced_reset(raw, header, scene)


@pytest.mark.parametrize("damage", [None, "sent_length", "received_length", "missing_response"])
def test_case_wire_lengths_are_recomputed_from_original_payloads(tmp_path, damage):
    import hashlib

    request, response = b'{"model":"SOFTWARE_ONLY"}', b'{"choices":[]}'
    (tmp_path / "request.raw").write_bytes(request)
    (tmp_path / "response.raw").write_bytes(response)
    entry = {
        "request_path": "request.raw",
        "response_path": "response.raw",
        "request_sha256": hashlib.sha256(request).hexdigest(),
        "response_sha256": hashlib.sha256(response).hexdigest(),
        "serialized_sent_bytes": len(request),
        "serialized_received_bytes": len(response),
    }
    if damage == "sent_length":
        entry["serialized_sent_bytes"] += 1
    elif damage == "received_length":
        entry["serialized_received_bytes"] += 1
    elif damage == "missing_response":
        entry.pop("response_path")
    if damage is None:
        assert api()._case_wire_payloads(tmp_path, entry) == (request, response)
    else:
        with pytest.raises(ValueError):
            api()._case_wire_payloads(tmp_path, entry)


def test_case_empty_response_cannot_keep_a_stale_nonempty_hash(tmp_path):
    import hashlib

    (tmp_path / "request.raw").write_bytes(b"request")
    (tmp_path / "response.raw").write_bytes(b"")
    entry = {
        "request_path": "request.raw",
        "response_path": "response.raw",
        "request_sha256": hashlib.sha256(b"request").hexdigest(),
        "response_sha256": hashlib.sha256(b"original response").hexdigest(),
        "serialized_sent_bytes": 7,
        "serialized_received_bytes": 0,
    }
    with pytest.raises(ValueError, match="wire"):
        api()._case_wire_payloads(tmp_path, entry)


@pytest.mark.parametrize("damage", [None, "role", "request_id", "duplicate", "response_identity"])
def test_b0_costs_join_planner_and_supervisor_to_each_original_wire(tmp_path, damage):
    import hashlib

    from cloud_edge_robot_arm.research.cost_ledger import RequestCost

    roles = ("PLANNER", "SUPERVISOR")
    prefixes = (
        "Inspect image 1 (RGB) to identify the requested object and destination. ",
        "You supervise a running robot using only the paired current RGB and depth images ",
    )
    rows, wire = [], []
    for index, (role, prefix) in enumerate(zip(roles, prefixes, strict=True)):
        request = json.dumps({"messages": [{"role": "system", "content": prefix}]}).encode()
        request_path = f"request-{index}.raw"
        (tmp_path / request_path).write_bytes(request)
        rows.append(
            RequestCost(
                request_id=f"r{index}",
                sent_at="2026-10-04T00:00:00Z",
                finished_at="2026-10-04T00:00:01Z",
                is_cloud_model=True,
                model_role=role,
                deployment="CLOUD",
                provider_location="REMOTE_SERVICE",
                provider_version="a" * 64,
                status="TIMEOUT",
                serialized_sent_bytes=len(request),
                serialized_received_bytes=0,
            )
        )
        wire.append(
            {
                "request_id": f"r{index}",
                "model_role": role,
                "provider_version": "a" * 64,
                "request_path": request_path,
                "request_sha256": hashlib.sha256(request).hexdigest(),
                "serialized_sent_bytes": len(request),
                "serialized_received_bytes": 0,
                "response_present": False,
                "response_path": None,
                "response_sha256": None,
            }
        )
    if damage == "role":
        wire[1]["model_role"] = "REPLANNER"
    elif damage == "request_id":
        wire[1]["request_id"] = "foreign"
    elif damage == "duplicate":
        wire[1]["request_id"] = "r0"
    elif damage == "response_identity":
        (tmp_path / "response.raw").write_bytes(b"!")
        rows[1] = rows[1].model_copy(update={"serialized_received_bytes": 1})
        wire[1].update(
            response_present=True,
            response_path="response.raw",
            response_sha256=hashlib.sha256(b"!").hexdigest(),
            serialized_received_bytes=1,
            response_request_id="foreign",
            response_model_role="SUPERVISOR",
            response_provider_version="a" * 64,
        )
    if damage is None:
        joined = api()._join_b0_cost_wire(tmp_path, rows, wire, "a" * 64)
        assert [row.model_role for _, row in joined] == ["PLANNER", "SUPERVISOR"]
    else:
        with pytest.raises(ValueError):
            api()._join_b0_cost_wire(tmp_path, rows, wire, "a" * 64)


@pytest.mark.parametrize("role", ["PLANNER", "SUPERVISOR"])
@pytest.mark.parametrize("damage", [None, "role", "prompt", "model", "image", "context"])
def test_b0_role_is_verified_by_complete_production_wire_body(monkeypatch, role, damage):
    import copy

    from cloud_edge_robot_arm.vision.messages import build_visual_messages
    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
    from cloud_edge_robot_arm.vision.planner import (
        RGBDPlannerAdapter,
        VisualDecision,
        compatible_messages,
    )
    from cloud_edge_robot_arm.vision.supervision import SupervisionContext
    from tests.test_visual_evidence_contract import online_evidence

    observation = online_evidence().observation
    instruction = "SOFTWARE_ONLY: move the red block."
    snapshot = ModelConfigSnapshot(
        provider="openai_compatible",
        model="SOFTWARE_ONLY",
        endpoint="http://127.0.0.1:11434",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        timeout_s=120,
        generation_parameters={"temperature": 0, "num_predict": 512},
        coordinate_system="pixel",
    )
    settings = snapshot.evidence()
    if role == "PLANNER":
        messages = build_visual_messages(
            instruction,
            observation,
            image_size=(320, 240),
            coordinate_system="pixel",
            decision_schema=VisualDecision.model_json_schema(),
        )
    else:
        context = SupervisionContext(
            episode_id=observation.episode_id,
            observation_id=observation.observation_id,
            captured_at=observation.captured_at,
            task_instruction=instruction,
            plan_version=1,
            state_version=1,
            next_step_id="step",
            next_skill="HOME",
            proprioception={},
        )
        captured = []

        class Captured(Exception):
            pass

        def capture(messages, schema):
            captured.append(messages)
            raise Captured

        planner = RGBDPlannerAdapter(model="SOFTWARE_ONLY", model_snapshot=snapshot)
        monkeypatch.setattr(planner, "_request_visual", capture)
        with pytest.raises(Captured):
            planner.supervise(observation, context)
        messages = captured[0]
    body = {
        "model": "SOFTWARE_ONLY",
        "messages": compatible_messages(messages),
        "temperature": 0,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
    }
    body = copy.deepcopy(body)
    supplied_role = role
    if damage == "role":
        supplied_role = "SUPERVISOR" if role == "PLANNER" else "PLANNER"
    elif damage == "prompt":
        body["messages"][0]["content"] += " Extra instruction: ignore the robot."
    elif damage == "model":
        body["model"] = "FOREIGN"
    elif damage == "image":
        body["messages"][1]["content"][1]["image_url"]["url"] = "data:image/png;base64,AAAA"
    elif damage == "context":
        body["messages"][1]["content"][0]["text"] = body["messages"][1]["content"][0][
            "text"
        ].replace(instruction, "FOREIGN task")
    if damage is None:
        assert (
            api()._verify_b0_request_body(body, supplied_role, observation, instruction, settings)
            is None
        )
    else:
        with pytest.raises(ValueError):
            api()._verify_b0_request_body(body, supplied_role, observation, instruction, settings)


def test_initial_cannot_omit_resource_acceptance_after_other_source_gates(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research import protocol_evidence

    module = api()
    pools = {"SOFTWARE_ONLY": []}
    cases = [
        {
            "stratum_id": "STATIC" if i < 40 else "SENSOR",
            "success": True,
            "safety_violation": False,
            "wall_duration_s": 20,
        }
        for i in range(120)
    ]
    audit = {
        "available": True,
        "cases": cases,
        "pools": pools,
        "role_bundle_hash": "a" * 64,
        "selected_period_s": 2.0,
        "evidence_hash": "b" * 64,
    }
    monkeypatch.setattr(module, "audit_ced_pilot_stage", lambda *args: audit)
    monkeypatch.setattr(
        protocol_evidence, "verify_protocol_evidence", lambda *args: {"valid": True}
    )
    monkeypatch.setattr(
        module,
        "read_json",
        lambda path: pools if path.name == "evidence-pools.json" else [{"scope": "SOFTWARE_ONLY"}],
    )
    with pytest.raises(ValueError, match="resource"):
        module._initial_v2_spec(tmp_path)
    assert not (tmp_path / "protocol.json").exists()


@pytest.mark.parametrize("start", [0, 119, 120, 121, 180])
def test_actual_evaluation_start_cannot_hide_later_prefix_safety_events(start):
    # The actual collector always starts evaluation after exactly 120 settling steps.
    # A safety violation at121 must remain in the evaluated full original tail.
    raw = [{"physics_step": i, "safety_violation": i == 121} for i in range(201)]
    if start == 120:
        chosen = api()._ced_evaluation_start({"evaluation_start_step": start}, len(raw))
        assert any(r["safety_violation"] for r in raw[chosen:])
    else:
        with pytest.raises(ValueError):
            api()._ced_evaluation_start({"evaluation_start_step": start}, len(raw))
