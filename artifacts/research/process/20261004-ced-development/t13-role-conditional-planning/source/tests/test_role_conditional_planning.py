"""SOFTWARE_ONLY paired-image MockTransport; no actual owner or execution acceptance."""

import hashlib
import importlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.cost_ledger import CostLedger
from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    cloud_request_settings,
    configuration_hash,
)
from tests.test_ced_runtime_binding import role_binding
from tests.test_conditional_repair_intent import inputs
from tests.test_role_visual_repair import Response

ROOT = Path(__file__).resolve().parents[1]
PATH = "src/cloud_edge_robot_arm/cloud/replanning/role_conditional_planning.py"
SOURCES = (
    PATH,
    "src/cloud_edge_robot_arm/cloud/replanning/conditional_intent.py",
    "src/cloud_edge_robot_arm/cloud/replanning/visual_dependencies.py",
    "src/cloud_edge_robot_arm/vision/owner_registration.py",
    "src/cloud_edge_robot_arm/vision/planner.py",
    "src/cloud_edge_robot_arm/vision/messages.py",
    "src/cloud_edge_robot_arm/vision/runtime_binding.py",
    "src/cloud_edge_robot_arm/research/cost_ledger.py",
)


def api():
    return importlib.import_module(
        "cloud_edge_robot_arm.cloud.replanning.role_conditional_planning"
    )


class ConditionalMockTransport:
    """Real urllib body construction; zero network sockets or actual API evidence."""

    def __init__(self, change=None, after=None):
        self.requests = []
        self.change = change
        self.after = after

    def open(self, request, timeout):
        del timeout
        self.requests.append(request.data)
        body = json.loads(request.data)
        text = body["messages"][1]["content"][0]["text"]
        envelope = json.loads(text.split("\nROLE_CONDITIONAL_CONTEXT=")[1])
        decision = {
            "schema_version": "role.conditional-repair-planning.v1",
            "binding_hash": envelope["binding_hash"],
            "replacements": [
                {
                    "step_id": item["step_id"],
                    "skill": item["skill"],
                    "target_pixel": [1, 1],
                    "destination_pixel": None,
                }
                for item in envelope["authorized_steps"]
            ],
        }
        content = None
        if self.change:
            content = self.change(decision)
        content = content if isinstance(content, str) else json.dumps(decision)
        if self.after:
            self.after()
        return Response(
            json.dumps(
                {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
            ).encode()
        )


def setup(
    tmp_path,
    monkeypatch,
    *,
    change=None,
    after=None,
    coordinate_system="pixel",
    image_size=(320, 240),
):
    module = api()
    planner, binding = role_binding(tmp_path)
    planner.model_role = "REPLANNER"
    planner.allow_paid = True
    planner._api_key = "SOFTWARE_ONLY-secret-never-live"
    planner.cost_ledger = CostLedger()
    planner.model_snapshot = replace(
        planner.model_snapshot, coordinate_system=coordinate_system, image_size=image_size
    )
    hashes = {}
    for relative in SOURCES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    software = tmp_path / "src/software_grounding.py"
    software.write_text("# SOFTWARE_ONLY source fixture\n")
    hashes["src/software_grounding.py"] = hashlib.sha256(software.read_bytes()).hexdigest()
    cloud = replace(
        binding.bundle.cloud_snapshot,
        source_hashes=hashes,
        request_config_hash=configuration_hash(cloud_request_settings(planner)),
    )
    bundle = RoleModelBundle(
        cloud,
        binding.edge_snapshot.provider_id,
        binding.edge_snapshot.digest(),
        binding.bundle.device_pipeline_hash,
    )
    binding = replace(binding, bundle=bundle, edge_policy=binding.evidence()["edge_policy"])
    planner.role_snapshot = cloud
    data = inputs()
    owner = importlib.import_module("cloud_edge_robot_arm.vision.owner_registration")
    old = data["original"]
    requirements = {
        name: owner.OriginalActionRequirements(
            r.original_step,
            r.preconditions,
            r.postconditions,
            r.allowed_error_m,
            r.sensor_requirements,
            r.ordinary_ttl_s,
            r.expected_duration_s,
            {"src/software_grounding.py": hashes["src/software_grounding.py"]},
        )
        for name, r in old.requirements.items()
    }
    data["original"] = owner.freeze_original_visual_plan(
        **{
            **old.freeze_inputs(),
            "role_bundle_hash": bundle.digest(),
            "source_hashes": hashes,
            "compiler_source_hashes": {
                "src/software_grounding.py": hashes["src/software_grounding.py"]
            },
            "requirements": requirements,
        }
    )
    now = [data.pop("now")]
    source = module.RoleConditionalPlanningSource(**data, source_scope="SOFTWARE_ONLY")
    transport = ConditionalMockTransport(change, after)
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: transport)
    provider = module.RoleConditionalPlanningProvider(
        planner=planner, binding=binding, source=source, clock=lambda: now[0]
    )
    return provider, transport, planner, binding, data, now


def test_future_fail_is_planning_only_with_two_images_and_replanner_cost(tmp_path, monkeypatch):
    provider, wire, planner, _, data, _ = setup(tmp_path, monkeypatch)
    intent = provider.plan()
    assert intent.scope == "PLANNING_ONLY"
    assert intent.execution_admitted is False and intent.method_admitted is False
    assert intent.replacements[1].current_preconditions[0][1] == "FAIL"
    assert [r.step_id for r in intent.replacements] == ["grasp", "lift"]
    for r in intent.replacements:
        assert r.original_requirements.digest() == data["original"].requirements[r.step_id].digest()
    assert intent.valid_until <= data["original"].effective_deadline_at
    assert not hasattr(intent, "steps") and not hasattr(intent, "activation_token")
    assert len(wire.requests) == 1
    body = json.loads(wire.requests[0])
    assert len([p for p in body["messages"][1]["content"] if p["type"] == "image_url"]) == 2
    assert body["model"] == planner.model_name
    assert planner.cost_ledger.snapshot().requests_by_role == {"REPLANNER": 1}
    assert planner.cost_ledger.requests()[0].monetary_cost is None


def test_remote_text_contains_only_minimum_intent_context(tmp_path, monkeypatch):
    provider, wire, _, _, _, _ = setup(tmp_path, monkeypatch)
    provider.plan()
    body = json.loads(wire.requests[0])
    text = body["messages"][0]["content"] + body["messages"][1]["content"][0]["text"]
    for forbidden in (
        "robot_state",
        "visual_facts",
        "ConditionSpec",
        "remaining_retries",
        "task_deadline_at",
        "allowed_error_m",
        "gripper_holding",
        "metres",
        "target_pose",
    ):
        assert forbidden not in text
    envelope = json.loads(text.split("\nROLE_CONDITIONAL_CONTEXT=")[1])
    assert set(envelope) == {
        "schema_version",
        "binding_hash",
        "frame_binding_hash",
        "window_binding_hash",
        "source_binding_hash",
        "bundle_hash",
        "schema_hash",
        "authorized_steps",
    }


@pytest.mark.parametrize(
    "missing",
    [
        "binding",
        "source",
        "key",
        "paid",
        "ledger",
        "inventory",
        "snapshot",
        "role",
        "original_bundle",
    ],
)
def test_missing_prerequisite_makes_zero_requests_and_zero_reservations(
    tmp_path, monkeypatch, missing
):
    provider, wire, planner, binding, _, _ = setup(tmp_path, monkeypatch)
    ledger = planner.cost_ledger
    if missing == "binding":
        provider.binding = None
    elif missing == "source":
        provider.source = None
    elif missing == "key":
        planner._api_key = ""
    elif missing == "paid":
        planner.allow_paid = False
    elif missing == "ledger":
        planner.cost_ledger = None
    elif missing == "snapshot":
        planner.model_snapshot = None
    elif missing == "role":
        planner.model_role = "PLANNER"
    elif missing == "original_bundle":
        provider.source = replace(
            provider.source, original=replace(provider.source.original, role_bundle_hash="0" * 64)
        )
    else:
        cloud = replace(
            binding.bundle.cloud_snapshot,
            source_hashes={
                k: v for k, v in binding.bundle.cloud_snapshot.source_hashes.items() if k != PATH
            },
        )
        provider.binding = replace(
            binding,
            bundle=replace(binding.bundle, cloud_snapshot=cloud),
            edge_policy=binding.evidence()["edge_policy"],
        )
        planner.role_snapshot = cloud
    with pytest.raises((api().RoleConditionalPlanningUnavailable, ValueError)):
        provider.plan()
    assert not wire.requests and not ledger.requests()


@pytest.mark.parametrize("stop", ["estop_engaged", "collision_detected", "disconnected"])
def test_hard_stop_is_not_a_future_condition_fail_and_never_debits(tmp_path, monkeypatch, stop):
    provider, wire, planner, _, _, _ = setup(tmp_path, monkeypatch)
    robot = provider.source.online.robot_state.model_copy(
        update={
            "connected" if stop == "disconnected" else stop: False
            if stop == "disconnected"
            else True
        }
    )
    provider.source = replace(
        provider.source, online=replace(provider.source.online, robot_state=robot)
    )
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert not wire.requests and not planner.cost_ledger.requests()


@pytest.mark.parametrize(
    "change",
    [
        "extra",
        "duplicate",
        "reorder",
        "skill",
        "binding",
        "command",
        "token",
        "bool",
        "pixel",
        "nan",
        "duplicate_key",
    ],
)
def test_strict_remote_intent_rejects_without_any_execution_shape(tmp_path, monkeypatch, change):
    def mutate(d):
        if change == "extra":
            d["execution_admitted"] = True
        elif change == "duplicate":
            d["replacements"][1] = dict(d["replacements"][0])
        elif change == "reorder":
            d["replacements"].reverse()
        elif change == "skill":
            d["replacements"][1]["skill"] = "RELEASE"
        elif change == "binding":
            d["binding_hash"] = "0" * 64
        elif change == "command":
            d["replacements"][0]["joint_angles"] = [0] * 7
        elif change == "token":
            d["activation_token"] = "forged"
        elif change == "bool":
            d["replacements"][0]["target_pixel"] = [True, 0]
        elif change == "pixel":
            d["replacements"][0]["target_pixel"] = [9999, 0]
        elif change == "nan":
            d["replacements"][0]["target_pixel"] = [float("nan"), 0]
        else:
            return '{"binding_hash":"0",' + json.dumps(d)[1:]

    provider, wire, planner, *_ = setup(tmp_path, monkeypatch, change=mutate)
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert len(wire.requests) == 1 and len(planner.cost_ledger.requests()) == 1


@pytest.mark.parametrize("drift", ["clock", "source", "profile", "hardstop", "role"])
def test_post_response_clock_source_profile_robot_drift_cannot_return_intent(
    tmp_path, monkeypatch, drift
):
    provider, wire, planner, binding, _, now = setup(tmp_path, monkeypatch)

    def after():
        if drift == "clock":
            now[0] += timedelta(seconds=6)
        elif drift == "source":
            (binding.root / PATH).write_text("# changed after paid request\n")
        elif drift == "profile":
            planner.timeout_s += 1
        elif drift == "role":
            planner.model_role = "PLANNER"
        else:
            provider.source.online.robot_state.estop_engaged = True

    wire.after = after
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert len(wire.requests) == 1


def test_normalized_coordinates_are_converted_before_pure_builder(tmp_path, monkeypatch):
    def selected(d):
        d["replacements"][0]["target_pixel"] = [1000, 1000]

    provider, _, _, _, data, _ = setup(
        tmp_path, monkeypatch, change=selected, coordinate_system="normalized_1000"
    )
    result = provider.plan()
    frame = data["online"].observation
    assert result.replacements[0].target_pixel == (frame.width - 1, frame.height - 1)


def test_detached_original_source_inputs_cannot_change_request(tmp_path, monkeypatch):
    provider, _, _, _, data, _ = setup(tmp_path, monkeypatch)
    data["source_checkpoint"].robot_state["external_mutation"] = True
    data["online"].robot_state.estop_engaged = True
    result = provider.plan()
    assert result.scope == "PLANNING_ONLY"
    assert "external_mutation" not in provider.source.source_checkpoint.robot_state


def test_unavailable_or_forged_actual_scope_never_enables_transport(tmp_path, monkeypatch):
    provider, wire, planner, _, _, _ = setup(tmp_path, monkeypatch)
    for scope in ("UNAVAILABLE", "ACTUAL_SOURCE"):
        with pytest.raises((api().RoleConditionalPlanningUnavailable, ValueError)):
            provider.source = replace(provider.source, source_scope=scope)
            provider.plan()
    assert not wire.requests and not planner.cost_ledger.requests()


@pytest.mark.parametrize(
    "invalid",
    ["stale", "future", "deadline", "foreign", "checkpoint", "scene", "version", "bool_generation"],
)
def test_invalid_current_frame_context_before_request_has_zero_cost(tmp_path, monkeypatch, invalid):
    provider, wire, planner, _, _, now = setup(tmp_path, monkeypatch)
    source = provider.source
    if invalid == "stale":
        now[0] += timedelta(seconds=6)
    elif invalid == "future":
        now[0] = source.online.observation.captured_at - timedelta(microseconds=1)
    elif invalid == "deadline":
        now[0] = source.original.effective_deadline_at
    elif invalid == "foreign":
        provider.source = replace(
            source, current_identity=replace(source.current_identity, owner_epoch="foreign-owner")
        )
    elif invalid == "checkpoint":
        provider.source = replace(
            source,
            source_checkpoint=source.source_checkpoint.model_copy(
                update={"checkpoint_hash": "0" * 64}
            ),
        )
    elif invalid == "scene":
        provider.source = replace(
            source,
            source_checkpoint=source.source_checkpoint.model_copy(update={"scene_version": 2}),
        )
    elif invalid == "version":
        provider.source = replace(source, online=replace(source.online, command_seq=2))
    else:
        provider.source = replace(source, state_generation=True)
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert not wire.requests and not planner.cost_ledger.requests()


def test_completed_effect_remains_original_and_cannot_be_requested(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest

    provider, wire, _, _, _, _ = setup(tmp_path, monkeypatch)
    source = provider.source
    cp = source.source_checkpoint.model_copy(
        update={
            "completed_step_ids": ["grasp"],
            "pending_step_ids": ["lift"],
            "current_step_index": 1,
            "current_step_id": "lift",
            "checkpoint_hash": "",
        },
        deep=True,
    )
    cp = cp.model_copy(update={"checkpoint_hash": checkpoint_digest(cp)})
    provider.source = replace(
        source, source_checkpoint=cp, online=replace(source.online, context_hash=cp.checkpoint_hash)
    )
    intent = provider.plan()
    assert [r.step_id for r in intent.replacements] == ["lift"]
    assert intent.preserved_original_steps["grasp"] == source.original.contract.steps[0].model_dump(
        mode="json"
    )
    assert (
        "grasp"
        not in json.loads(wire.requests[0])["messages"][1]["content"][0]["text"].split(
            "authorized_steps"
        )[1]
    )


def test_backwards_post_response_clock_cannot_extend_planning(tmp_path, monkeypatch):
    provider, wire, _, _, _, now = setup(tmp_path, monkeypatch)
    wire.after = lambda: now.__setitem__(0, now[0] - timedelta(seconds=0.05))
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()


def test_resized_pixel_is_converted_from_sent_image_not_reinterpreted_as_original(
    tmp_path, monkeypatch
):
    def selected(d):
        for item in d["replacements"]:
            item["target_pixel"] = [0, 0]

    provider, wire, _, _, _, _ = setup(tmp_path, monkeypatch, change=selected, image_size=(1, 1))
    intent = provider.plan()
    assert intent.replacements[0].target_pixel == (1, 1)  # Actual synthetic 2x2 -> sent 1x1 center.
    assert len(wire.requests) == 1


def test_symlinked_role_source_root_cannot_become_current_by_resolving_alias(tmp_path, monkeypatch):
    provider, wire, planner, binding, _, _ = setup(tmp_path, monkeypatch)
    alias = tmp_path.parent / (tmp_path.name + "-source-alias")
    alias.symlink_to(tmp_path, target_is_directory=True)
    provider.binding = replace(binding, root=alias, edge_policy=binding.evidence()["edge_policy"])
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert not wire.requests and not planner.cost_ledger.requests()
