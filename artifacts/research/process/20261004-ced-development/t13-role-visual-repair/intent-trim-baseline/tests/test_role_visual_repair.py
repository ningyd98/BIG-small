"""SOFTWARE_ONLY MockTransport: no live cloud, geometry, dispatch or acceptance."""

import hashlib
import importlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    cloud_request_settings,
    configuration_hash,
)
from tests.test_replan_activation import NOW

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_PATH = "src/cloud_edge_robot_arm/cloud/replanning/role_visual_repair.py"
ADAPTER_PATH = "src/cloud_edge_robot_arm/cloud/replanning/role_visual_adapter.py"
REQUIRED_SOURCES = (
    PROVIDER_PATH,
    ADAPTER_PATH,
    "src/cloud_edge_robot_arm/cloud/replanning/visual_repair.py",
    "src/cloud_edge_robot_arm/cloud/replanning/visual_dependencies.py",
    "src/cloud_edge_robot_arm/vision/planner.py",
    "src/cloud_edge_robot_arm/vision/messages.py",
)


def api():
    return importlib.import_module("cloud_edge_robot_arm.cloud.replanning.role_visual_repair")


def adapter_api():
    return importlib.import_module("cloud_edge_robot_arm.cloud.replanning.role_visual_adapter")


class MockTransport:
    """urllib boundary fixture; actual body bytes, zero live sockets."""

    def __init__(self, change=None):
        self.requests = []
        self.change = change

    def open(self, request, timeout):
        del timeout
        body = json.loads(request.data)
        self.requests.append(request.data)
        user = body["messages"][1]["content"][0]["text"]
        envelope = json.loads(user.split("\nROLE_REPAIR_CONTEXT=")[1].split("\n")[0])
        decision = {
            "schema_version": "role.visual-repair-intent.v1",
            "binding_hash": envelope["binding_hash"],
            "replacements": [
                {
                    "step_id": step["step_id"],
                    "skill": step["skill"],
                    "target_pixel": [0, 0],
                    "destination_pixel": [0, 0],
                }
                for step in envelope["authorized_steps"]
            ],
        }
        if self.change:
            self.change(decision)
        payload = json.dumps({"choices": [{"message": {"content": json.dumps(decision)}}]}).encode()
        return Response(payload)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, limit):
        return self.payload[:limit]


def setup(tmp_path, monkeypatch, *, change=None, full_remaining=False):
    from cloud_edge_robot_arm.contracts.models import replan_payload_hash
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract, VisualEvidence
    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from tests.test_ced_runtime_binding import role_binding
    from tests.test_visual_repair_builder import fixture

    planner, binding = role_binding(tmp_path)
    planner.allow_paid = True
    planner._api_key = "MOCK-secret-never-live"
    planner.model_role = "REPLANNER"
    ledger = CostLedger()
    planner.cost_ledger = ledger
    sources = {}
    for relative in REQUIRED_SOURCES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
        sources[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    cloud = replace(
        binding.bundle.cloud_snapshot,
        source_hashes=sources,
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
    request, context, window, observation = fixture()
    context = replace(
        context,
        online_evidence=replace(
            context.online_evidence, context_hash=context.checkpoint.checkpoint_hash
        ),
    )
    contracts = {}
    for step in context.active_contract.steps:
        if step.step_id in context.checkpoint.completed_step_ids:
            continue
        pre = (ConditionSpec("target_visible", "obj-1"),)
        post = (ConditionSpec("object_held", "obj-1"),)
        visual = VisualEvidence(
            observation.observation_id,
            observation.calibration_version,
            observation.captured_at,
            0.001,
            0.0,
            "CONFIRMED",
            "VALID",
        )
        contracts[step.step_id] = ActionEvidenceContract(
            visual,
            max(step.timeout_ms, step.expected_duration_ms) / 1000,
            0.01,
            ("rgbd",),
            pre,
            post,
            1,
            1,
            context.checkpoint.checkpoint_hash,
        )
    source = api().RoleVisualRepairSource(context, contracts, evidence_scope="SOFTWARE_ONLY")

    def grounding(decision, original, observation, context, binding_hash):
        del decision, observation, context
        return api().GroundedRepairStep(
            original.model_copy(deep=True),
            contracts[original.step_id],
            binding_hash,
            payload_hash=replan_payload_hash(original),
        )

    transport = MockTransport(change)
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: transport)
    adapter = adapter_api().RoleVisualReplannerAdapter(
        planner=planner,
        binding=binding,
        source_provider=lambda *_: source,
        grounding_provider=grounding,
        full_remaining=full_remaining,
        clock=lambda: NOW + timedelta(seconds=0.2),
    )
    return adapter, transport, planner, binding, source, request, window, observation, ledger


def test_role_repair_wire_has_two_images_replanner_cost_and_only_authorized_replacement(
    tmp_path, monkeypatch
):
    adapter, wire, planner, binding, source, request, window, observation, ledger = setup(
        tmp_path, monkeypatch
    )
    result = adapter.replan(request)
    assert result.outcome == "REPLANNED" and not result.validation_errors
    assert [step.step_id for step in result.new_steps] == ["grasp", "telemetry"]
    assert len(wire.requests) == 1
    body = json.loads(wire.requests[0])
    assert (
        len([part for part in body["messages"][1]["content"] if part["type"] == "image_url"]) == 2
    )
    assert body["model"] == planner.model_name
    assert body["response_format"] == {"type": "json_object"}
    assert result.planner_name == "role-visual-repair-software"


@pytest.mark.parametrize("missing", ["binding", "source", "grounding", "key", "inventory"])
def test_missing_actual_prerequisite_is_unavailable_with_zero_calls(tmp_path, monkeypatch, missing):
    adapter, wire, planner, binding, source, request, *_ = setup(tmp_path, monkeypatch)
    if missing == "binding":
        adapter.binding = None
    elif missing == "source":
        adapter.source_provider = None
    elif missing == "grounding":
        adapter.grounding_provider = None
    elif missing == "key":
        planner._api_key = ""
    else:
        cloud = replace(
            binding.bundle.cloud_snapshot,
            source_hashes={
                k: v
                for k, v in binding.bundle.cloud_snapshot.source_hashes.items()
                if k != PROVIDER_PATH
            },
        )
        adapter.binding = replace(
            binding,
            bundle=replace(binding.bundle, cloud_snapshot=cloud),
            edge_policy=binding.evidence()["edge_policy"],
        )
        planner.role_snapshot = cloud
    result = adapter.replan(request)
    assert result.outcome != "REPLANNED" and result.new_steps == []
    assert wire.requests == []


@pytest.mark.parametrize("change", ["wrong_hash", "completed", "duplicate", "missing", "skill"])
def test_remote_parsed_candidate_cannot_change_bound_ids_or_skills(tmp_path, monkeypatch, change):
    def mutate(decision):
        if change == "wrong_hash":
            decision["binding_hash"] = "f" * 64
        elif change == "completed":
            decision["replacements"][0]["step_id"] = "approach"
        elif change == "duplicate":
            decision["replacements"].append(decision["replacements"][0])
        elif change == "missing":
            decision["replacements"] = []
        else:
            decision["replacements"][0]["skill"] = "HOME"

    adapter, wire, _, _, _, request, *_ = setup(tmp_path, monkeypatch, change=mutate)
    result = adapter.replan(request)
    assert len(wire.requests) == 1
    assert result.outcome != "REPLANNED" and result.new_steps == []


def test_b4_expansion_keeps_same_failure_frame_and_source_bindings(tmp_path, monkeypatch):
    adapter, wire, _, _, _, request, *_ = setup(tmp_path, monkeypatch)
    local = adapter.replan(request)
    adapter.full_remaining = True
    full = adapter.replan(request)
    assert local.outcome == full.outcome == "REPLANNED"
    contexts = [
        json.loads(
            json.loads(body)["messages"][1]["content"][0]["text"]
            .split("\nROLE_REPAIR_CONTEXT=")[1]
            .split("\n")[0]
        )
        for body in wire.requests
    ]
    assert contexts[0]["request"] == contexts[1]["request"]
    assert contexts[0]["frame"] == contexts[1]["frame"]
    assert contexts[0]["source_hash"] == contexts[1]["source_hash"]
    assert [step["step_id"] for step in contexts[0]["authorized_steps"]] == ["grasp"]
    assert [step["step_id"] for step in contexts[1]["authorized_steps"]] == ["grasp", "telemetry"]
    assert all(
        "approach" not in [step["step_id"] for step in context["authorized_steps"]]
        for context in contexts
    )


def test_direct_provider_cannot_expand_its_authorized_window(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import RepairWindow

    adapter, wire, _, _, source, request, window, observation, _ = setup(tmp_path, monkeypatch)
    provider = api().RoleVisualRepairProvider(
        planner=adapter.planner,
        binding=adapter.binding,
        source=source,
        grounding_provider=adapter.grounding_provider,
        clock=lambda: NOW + timedelta(seconds=0.2),
    )
    expanded = RepairWindow("grasp", ("grasp", "telemetry"), ("approach",), 1, 1)
    with pytest.raises(api().RoleVisualRepairUnavailable):
        provider(request, expanded, observation, source.context)
    assert wire.requests == []


def test_b4_missing_expanded_step_geometry_is_unavailable_before_any_call(tmp_path, monkeypatch):
    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch, full_remaining=True)
    source = api().RoleVisualRepairSource(
        source.context, {"grasp": source.action_evidence["grasp"]}, evidence_scope="SOFTWARE_ONLY"
    )
    adapter.source_provider = lambda *_: source
    result = adapter.replan(request)
    assert result.outcome == "MORE_OBSERVATION_REQUIRED" and result.new_steps == []
    assert wire.requests == []


@pytest.mark.parametrize(
    "changed", ["plan_id", "robot_id", "failed_step_id", "completed", "future", "bytes"]
)
def test_direct_provider_revalidates_complete_request_and_frame_before_paid_call(
    tmp_path, monkeypatch, changed
):
    adapter, wire, _, _, source, request, window, observation, _ = setup(tmp_path, monkeypatch)
    updates = {
        "plan_id": "other",
        "robot_id": "other",
        "failed_step_id": "approach",
        "completed_step_ids": [],
        "requested_at": NOW + timedelta(seconds=1),
    }
    if changed == "completed":
        request = request.model_copy(update={"completed_step_ids": []})
    elif changed == "future":
        request = request.model_copy(update={"requested_at": updates["requested_at"]})
    elif changed == "bytes":
        observation = observation.model_copy(update={"rgb_png_base64": "Y2hhbmdlZA=="})
    else:
        request = request.model_copy(update={changed: updates[changed]})
    provider = api().RoleVisualRepairProvider(
        planner=adapter.planner,
        binding=adapter.binding,
        source=source,
        grounding_provider=adapter.grounding_provider,
        clock=lambda: NOW + timedelta(seconds=0.2),
    )
    with pytest.raises(api().RoleVisualRepairUnavailable):
        provider(request, window, observation, source.context)
    assert wire.requests == []


def test_grounder_nested_execution_output_cannot_become_repair_candidate(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.contracts.models import replan_payload_hash

    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)

    def grounding(decision, original, observation, context, binding_hash):
        del decision, observation, context
        step = original.model_copy(update={"parameters": {"nested": {"joint_angles": [1, 2, 3]}}})
        return api().GroundedRepairStep(
            step, source.action_evidence[original.step_id], binding_hash, replan_payload_hash(step)
        )

    adapter.grounding_provider = grounding
    result = adapter.replan(request)
    assert len(wire.requests) == 1
    assert result.outcome != "REPLANNED" and result.new_steps == []


def test_source_provider_receives_detached_service_context(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.cloud.replanning.context import ReplanningContext

    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)
    visual = source.context
    service_context = ReplanningContext(
        visual.active_contract.model_copy(deep=True),
        visual.active_contract.steps[1].model_copy(deep=True),
        [visual.active_contract.steps[0].model_copy(deep=True)],
        visual.checkpoint.model_copy(deep=True),
    )
    before = api().digest(service_context)

    def source_provider(received_request, received_context):
        del received_request
        received_context.active_contract.steps.clear()
        return source

    adapter.source_provider = source_provider
    result = adapter.replan(request, service_context)
    assert api().digest(service_context) == before
    assert wire.requests == [] and result.new_steps == []


@pytest.mark.parametrize("bad", ["duplicate_precondition", "duplicate_postcondition"])
def test_ambiguous_frozen_conditions_reject_before_paid_call(tmp_path, monkeypatch, bad):
    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)
    proofs = dict(source.action_evidence)
    proof = proofs["grasp"]
    field = "preconditions" if bad == "duplicate_precondition" else "postconditions"
    proofs["grasp"] = replace(proof, **{field: getattr(proof, field) * 2})
    changed = api().RoleVisualRepairSource(source.context, proofs, "SOFTWARE_ONLY")
    adapter.source_provider = lambda *_: changed
    result = adapter.replan(request)
    assert wire.requests == [] and result.new_steps == []


@pytest.mark.parametrize(
    "bad", ["scope", "duration", "motion", "estop", "collision", "disconnected"]
)
def test_incomplete_or_unsafe_actual_source_is_unavailable_before_paid_call(
    tmp_path, monkeypatch, bad
):
    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)
    proofs = dict(source.action_evidence)
    context = source.context
    scope = "SOFTWARE_ONLY"
    if bad == "scope":
        scope = "ACTUAL_SOURCE"
    elif bad == "duration":
        proofs["grasp"] = replace(proofs["grasp"], expected_duration_s=0.001)
    elif bad == "motion":
        proofs["grasp"] = replace(
            proofs["grasp"], evidence=replace(proofs["grasp"].evidence, motion_bound_m_s=None)
        )
    else:
        changes = {
            "estop": {"estop_engaged": True},
            "collision": {"collision_detected": True},
            "disconnected": {"connected": False},
        }[bad]
        context = replace(
            context,
            online_evidence=replace(
                context.online_evidence,
                robot_state=context.online_evidence.robot_state.model_copy(update=changes),
            ),
        )
    changed = api().RoleVisualRepairSource(context, proofs, scope)
    adapter.source_provider = lambda *_: changed
    result = adapter.replan(request)
    assert wire.requests == [] and result.new_steps == []


@pytest.mark.parametrize("bad", ["binding", "timeout", "retry", "frame", "conditions"])
def test_grounded_step_must_preserve_full_bound_proof_and_frozen_parameters(
    tmp_path, monkeypatch, bad
):
    from cloud_edge_robot_arm.contracts.models import replan_payload_hash

    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)

    def grounding(decision, original, observation, context, binding_hash):
        del decision, observation, context
        proof = source.action_evidence[original.step_id]
        if bad == "binding":
            binding_hash = "f" * 64
        elif bad == "timeout":
            original = original.model_copy(update={"timeout_ms": 1})
        elif bad == "retry":
            original = original.model_copy(update={"retry_limit": original.retry_limit + 1})
        elif bad == "frame":
            proof = replace(proof, evidence=replace(proof.evidence, observation_id="old-frame"))
        else:
            proof = replace(proof, postconditions=())
        return api().GroundedRepairStep(
            original, proof, binding_hash, replan_payload_hash(original)
        )

    adapter.grounding_provider = grounding
    result = adapter.replan(request)
    assert len(wire.requests) == 1 and result.new_steps == [] and result.outcome != "REPLANNED"


def test_wire_observer_and_cost_ledger_preserve_actual_mock_body_bytes(tmp_path, monkeypatch):
    adapter, wire, planner, _, _, request, *_rest, ledger = setup(tmp_path, monkeypatch)
    seen = []
    planner.raw_transport_observer = lambda phase, path, data: seen.append((phase, path, data))
    result = adapter.replan(request)
    assert result.outcome == "REPLANNED"
    assert [phase for phase, _, _ in seen] == ["REQUEST", "RESPONSE"]
    assert seen[0][2] == wire.requests[0]
    rows = ledger.requests()
    assert len(rows) == 1 and rows[0].model_role == "REPLANNER"
    assert rows[0].provider_location == "REMOTE_SERVICE" and rows[0].is_cloud_model
    assert rows[0].status == "SUCCESS"
    assert rows[0].serialized_sent_bytes == len(seen[0][2])
    assert rows[0].serialized_received_bytes == len(seen[1][2])
    assert planner._api_key.encode() not in seen[0][2]
    assert ledger.snapshot().cloud_model_requests == 1


@pytest.mark.parametrize("error", ["http", "timeout", "invalid_json"])
def test_failed_mock_transport_is_counted_once_without_secret_response_or_fallback(
    tmp_path, monkeypatch, error
):
    import io
    import urllib.error

    adapter, wire, planner, _, _, request, *_rest, ledger = setup(tmp_path, monkeypatch)
    secret = planner._api_key
    encoded = "".join(f"\\u{ord(c):04x}" for c in secret).encode()
    seen = []
    planner.raw_transport_observer = lambda phase, path, data: seen.append((phase, path, data))

    def fail(received, timeout):
        del timeout
        wire.requests.append(received.data)
        if error == "http":
            raise urllib.error.HTTPError(received.full_url, 503, "failed", {}, io.BytesIO(encoded))
        if error == "timeout":
            raise TimeoutError(secret)
        return Response(encoded)

    wire.open = fail
    result = adapter.replan(request)
    assert len(wire.requests) == 1 and result.new_steps == [] and result.outcome != "REPLANNED"
    assert secret not in result.model_dump_json()
    assert len(ledger.requests()) == 1
    row = ledger.requests()[0]
    assert row.status == ("TIMEOUT" if error == "timeout" else "ERROR")
    assert row.serialized_sent_bytes == len(wire.requests[0])
    assert row.serialized_received_bytes == (0 if error == "timeout" else len(encoded))
    if error != "timeout":
        assert seen[-1][2] == encoded


def test_missing_cost_accounting_rejects_before_paid_request(tmp_path, monkeypatch):
    adapter, wire, planner, _, _, request, *_ = setup(tmp_path, monkeypatch)
    planner.cost_ledger = None
    result = adapter.replan(request)
    assert result.new_steps == [] and wire.requests == []


@pytest.mark.parametrize("changed", ["expired", "source_drift"])
def test_post_wire_revalidation_rejects_expiration_or_source_drift_without_second_call(
    tmp_path, monkeypatch, changed
):
    adapter, wire, _, _, _, request, *_ = setup(tmp_path, monkeypatch)

    def change(_):
        if changed == "expired":
            adapter.clock = lambda: NOW + timedelta(seconds=10)
        else:
            (tmp_path / PROVIDER_PATH).write_bytes(b"changed-source")

    wire.change = change
    # Provider captures the callable; advance its returned value instead of replacing it.
    times = [NOW + timedelta(seconds=0.2)]
    adapter.clock = lambda: times[0]
    if changed == "expired":
        wire.change = lambda _: times.__setitem__(0, NOW + timedelta(seconds=10))
    result = adapter.replan(request)
    assert len(wire.requests) == 1 and result.new_steps == [] and result.outcome != "REPLANNED"


def test_source_detaches_original_context_and_nested_condition_tolerances(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    adapter, _, _, _, source, _, *_ = setup(tmp_path, monkeypatch)
    context = source.context
    tolerance = {"nested": {"values": [1, 2]}}
    proof = source.action_evidence["grasp"]
    proof = replace(proof, preconditions=(ConditionSpec("target_visible", "obj-1", tolerance),))
    snapshot = api().RoleVisualRepairSource(context, {"grasp": proof}, "SOFTWARE_ONLY")
    before = snapshot.source_hash
    context.active_contract.steps.clear()
    tolerance["nested"]["values"].append(3)
    assert api().digest(snapshot.payload()) == before
    assert snapshot.context.active_contract.steps


def test_existing_service_creates_candidate_only_without_ack_activation_or_execution(
    tmp_path, monkeypatch
):
    from cloud_edge_robot_arm.cloud.replanning.service import LocalReplanningService
    from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
    from cloud_edge_robot_arm.contracts.models import replan_payload_hash
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )
    from tests.test_replan_activation import setup_replan

    adapter, wire, _, _, source, _, *_ = setup(tmp_path, monkeypatch)
    repo = InMemoryEventAutonomyRepository()
    request, _ = setup_replan(repo)
    active = repo.get_active_contract("task")
    checkpoint = repo.get_latest_execution_checkpoint("task")
    assert active is not None and checkpoint is not None
    data = checkpoint.model_dump(mode="json")
    data["checkpoint_hash"] = ""
    online = replace(source.context.online_evidence, context_hash=replan_payload_hash(data))
    context = replace(
        source.context,
        active_contract=active.contract,
        checkpoint=checkpoint,
        online_evidence=online,
        dependencies=(
            StepDependency("approach", (), (), None, True),
            StepDependency("grasp", ("approach",), ("lost",), "grasp-effect", False),
            *(
                StepDependency(step.step_id, (), (), None, False)
                for step in active.contract.steps[2:]
            ),
        ),
        completed_effect_conditions={},
    )
    proof = replace(source.action_evidence["grasp"], context_hash=replan_payload_hash(data))
    actual_source = api().RoleVisualRepairSource(context, {"grasp": proof}, "SOFTWARE_ONLY")
    adapter.source_provider = lambda *_: actual_source
    adapter.grounding_provider = lambda intent, original, observation, current, binding_hash: (
        api().GroundedRepairStep(original, proof, binding_hash, replan_payload_hash(original))
    )
    service = LocalReplanningService(
        adapter=adapter, repository=repo, clock=lambda: NOW + timedelta(seconds=0.2)
    )
    result = service.process(request, apply=True, dispatch=False)
    assert result.outcome == "REPLANNED" and len(wire.requests) == 1, result.model_dump()
    prepared = repo.get_replan_apply_record_for_request(request.request_id)
    assert prepared is not None and prepared.status == "PREPARED"
    assert prepared.stage_ack is None and prepared.resume_ack is None
    assert prepared.start_receipt is None and not prepared.activation_token
    assert repo.get_active_contract("task").contract.plan_version == 1


@pytest.mark.parametrize(
    "key", ["joint_positions", "trajectory", "disable_safety", "bypass_safety", "ignore_collision"]
)
def test_grounding_cannot_embed_execution_or_safety_override(tmp_path, monkeypatch, key):
    from cloud_edge_robot_arm.contracts.models import replan_payload_hash

    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)

    def grounding(intent, original, observation, context, binding_hash):
        del intent, observation, context
        step = original.model_copy(update={"parameters": {"nested": [{key: True}]}})
        return api().GroundedRepairStep(
            step, source.action_evidence[original.step_id], binding_hash, replan_payload_hash(step)
        )

    adapter.grounding_provider = grounding
    result = adapter.replan(request)
    assert len(wire.requests) == 1 and result.new_steps == [] and result.outcome != "REPLANNED"


def test_grounder_mutation_of_supplied_context_cannot_become_candidate(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.contracts.models import replan_payload_hash

    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)
    before = source.source_hash

    def grounding(intent, original, observation, context, binding_hash):
        del intent, observation
        context.active_contract.steps.clear()
        return api().GroundedRepairStep(
            original,
            source.action_evidence[original.step_id],
            binding_hash,
            replan_payload_hash(original),
        )

    adapter.grounding_provider = grounding
    result = adapter.replan(request)
    assert len(wire.requests) == 1 and result.new_steps == [] and result.outcome != "REPLANNED"
    assert api().digest(source.payload()) == before


def test_wire_context_contains_exact_current_state_and_full_frozen_condition_specs(tmp_path, monkeypatch):
    adapter, wire, _, _, source, request, *_ = setup(tmp_path, monkeypatch)
    result = adapter.replan(request)
    assert result.outcome == 'REPLANNED'
    body = json.loads(wire.requests[0])
    envelope = json.loads(body['messages'][1]['content'][0]['text']
        .split('\nROLE_REPAIR_CONTEXT=')[1].split('\n')[0])
    current = envelope['current_context']
    assert current['checkpoint'] == api().plain(source.context.checkpoint)
    assert current['robot_state'] == api().plain(source.context.online_evidence.robot_state)
    assert current['visual_facts'] == api().plain(source.context.online_evidence.visual_facts)
    assert current['completed_effect_conditions'] == api().plain(source.context.completed_effect_conditions)
    assert envelope['action_evidence']['grasp'] == api().plain(source.action_evidence['grasp'])
    assert envelope['evidence_scope'] == 'SOFTWARE_ONLY'
    hashed = {k:v for k,v in envelope.items() if k not in {'binding_hash','authorized_steps'}}
    assert api().digest(hashed) == envelope['binding_hash']
