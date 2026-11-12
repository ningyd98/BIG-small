"""Registered coordinates retain the original collection conditions and authority boundary."""

from dataclasses import replace

import pytest

from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.vision import owner_registration as owner
from cloud_edge_robot_arm.vision import worker_owner
from tests.test_registered_grounding_binding import binding_data


def collection_type():
    assert hasattr(owner, "RegisteredCollectionStepBinding"), "collection source binding missing"
    return owner.RegisteredCollectionStepBinding


def test_collection_binding_api():
    assert collection_type()


@pytest.mark.parametrize(
    "skill",
    [
        SkillName.MOVE_ABOVE,
        SkillName.APPROACH,
        SkillName.GRASP,
        SkillName.LIFT,
        SkillName.MOVE_TO_REGION,
        SkillName.PLACE,
        SkillName.RELEASE,
        SkillName.RETREAT,
    ],
)
def test_collection_binding_preserves_constraints_without_becoming_legacy(
    tmp_path, monkeypatch, skill
):
    data = binding_data(tmp_path, monkeypatch, skill)
    prepared = owner.prepare_registered_step_binding(**data)
    result = collection_type().from_prepared(
        prepared, collection_policy_id="registered-model-collection-v1"
    )
    payload = result.to_payload()
    assert payload["schema_version"] == "registered.collection.binding.v1"
    assert payload["execution_authority"] is False
    assert payload["native_authority"] == "UNAVAILABLE"
    assert result.prepared.to_payload() == prepared.to_payload()
    assert result.prepared.to_payload()["prepare_only"] is True
    assert result.grounded_step.parameters == prepared.grounded_step.parameters
    assert result.grounded_step.timeout_ms == 10000
    assert not isinstance(result, owner.StepGroundingBinding)
    assert not isinstance(result, owner.RegisteredPreparedStepBinding)
    effect = worker_owner.registered_collection_effect_conditions(data["original"], result)
    assert [c.name for c in effect] == [
        c.name for c in data["original"].requirements["move"].postconditions
    ]
    for condition in effect:
        if condition.name == "tcp_at_resolved_target":
            assert [condition.tolerances["target_" + a] for a in "xyz"] == [
                prepared.grounded_step.parameters["target_pose"][a] for a in "xyz"
            ]
    with pytest.raises(ValueError, match="concrete"):
        worker_owner.grounded_worker_effect_conditions(data["original"], result)
    saved = result.digest()
    payload["prepared"]["grounded_step"]["parameters"]["object_id"] = "foreign"
    assert result.digest() == saved
    assert type(result).from_payload(result.to_payload()).digest() == saved


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_authority", True),
        ("native_authority", "AVAILABLE"),
        ("collection_policy_id", "rgbd-top-grasp-v1"),
        ("extra", "unregistered"),
    ],
)
def test_collection_binding_rejects_authority_relabelling(tmp_path, monkeypatch, field, value):
    data = binding_data(tmp_path, monkeypatch)
    cls = collection_type()
    result = cls.from_prepared(
        owner.prepare_registered_step_binding(**data),
        collection_policy_id="registered-model-collection-v1",
    )
    payload = result.to_payload()
    payload[field] = value
    with pytest.raises((ValueError, TypeError)):
        cls.from_payload(payload)


def test_collection_effect_rejects_foreign_original(tmp_path, monkeypatch):
    data = binding_data(tmp_path, monkeypatch)
    result = collection_type().from_prepared(
        owner.prepare_registered_step_binding(**data),
        collection_policy_id="registered-model-collection-v1",
    )
    foreign = replace(data["original"], proposal_hash="f" * 64)
    with pytest.raises(ValueError, match="binding"):
        worker_owner.registered_collection_effect_conditions(foreign, result)


def test_collection_binding_never_accepts_a_plain_mapping(tmp_path, monkeypatch):
    data = binding_data(tmp_path, monkeypatch)
    prepared = owner.prepare_registered_step_binding(**data)
    with pytest.raises(TypeError):
        collection_type().from_prepared(
            prepared.to_payload(), collection_policy_id="registered-model-collection-v1"
        )


def test_protocol_api():
    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api

    assert hasattr(protocol_api, "prepare_registered_collection_protocol"), "v7 protocol missing"


def test_collection_consumer_api():
    from cloud_edge_robot_arm.research import native_collection_grounding as collection

    assert hasattr(collection, "registered_collection_step"), (
        "registered collection producer missing"
    )


def test_protocol_does_not_release_an_assignment_or_create_runtime(tmp_path):
    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api
    from cloud_edge_robot_arm.research.native_collection_application import (
        NativeCollectionApplication,
    )

    destination = tmp_path / "protocol"
    protocol_api.prepare_registered_collection_protocol(output=destination)
    recipe = protocol_api.read_protocol(destination)
    assert recipe["schema_version"] == "native.calibration.operational.v7"
    assert recipe["assignments"] == recipe["released_assignments"] == []
    assert not any(recipe["authorized_actual_budget"].values())
    assert recipe["collection_policy_id"] == "registered-model-collection-v1"
    with pytest.raises(ValueError, match="release"):
        NativeCollectionApplication.from_startup(
            destination, assignment_id="native-r595-0001", output=tmp_path / "run"
        )
    assert not (tmp_path / "run").exists()
    assert not (destination / "claims").exists()


@pytest.mark.parametrize("change", ["release", "budget", "schema", "source"])
def test_v7_recipe_cannot_be_relabelled_or_relaxed(tmp_path, change):
    import json

    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api

    destination = tmp_path / "protocol"
    protocol_api.prepare_registered_collection_protocol(output=destination)
    recipe = protocol_api.read_protocol(destination)
    if change == "release":
        recipe["execution_release"] = "RELEASED"
    elif change == "budget":
        recipe["authorized_actual_budget"]["actions"] = 1
    elif change == "schema":
        recipe["schema_version"] = "native.calibration.operational.v2"
    else:
        recipe["source_hashes"].pop(next(iter(recipe["source_hashes"])))
        recipe["source_generation"] = protocol_api.digest(recipe["source_hashes"])
    (destination / "protocol.json").write_text(json.dumps(recipe))
    with pytest.raises(ValueError):
        protocol_api.read_protocol(destination)


def consumer_context(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api
    from cloud_edge_robot_arm.research import native_collection_application as application
    from cloud_edge_robot_arm.research import native_collection_grounding as collection
    from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
    from tests.test_registered_grounding_preparation import ROOT, context

    protocol_path, args, clock = context(tmp_path, monkeypatch)
    monkeypatch.setattr(collection, "datetime", application.datetime)
    protocol_api.prepare_registered_collection_protocol(output=tmp_path / "v7")
    protocol = protocol_api.read_protocol(tmp_path / "v7")
    legacy, evidence = collection.bootstrap_collection_tracker(
        args["reference_observation"], protocol["geometry"]
    )
    registered = collection.bootstrap_registered_collection_tracker_v1(
        args["reference_observation"],
        NativeGeometryRegistration(protocol["geometry"]),
        source_root=ROOT,
        source_hashes=protocol["source_hashes"],
    )
    records = []
    live = SimpleNamespace(
        repository=args["repository"],
        original=args["original"],
        tracker=legacy,
        registered_tracker=registered,
        grounding_evidence=evidence,
        robot=SimpleNamespace(get_state=lambda: args["robot_state"]),
        recorder=SimpleNamespace(
            record_grounding=records.append,
            acquisition_source=lambda: {
                "acquisition_id": "synthetic-current",
                "path": "synthetic",
                "sha256": "a" * 64,
            },
        ),
    )

    def consume():
        return {
            "live_owner": {
                "lease": application._registered_lease(
                    live.repository, live.original.identity
                ).to_payload()
            }
        }

    return application, collection, live, protocol, args, clock, records, consume


def test_actual_collection_helper_uses_new_model_binding_and_preserves_old_unknown(
    tmp_path, monkeypatch
):
    application, _, live, protocol, args, _, records, consume = consumer_context(
        tmp_path, monkeypatch
    )
    _, step, binding, online, checkpoint = application._collect_grounded_step(
        live, 0, args["observation"], protocol, consume_capture=consume
    )
    assert type(binding) is collection_type()
    assert step.parameters["target_pose"]["z"] > 0.1
    assert online.visual_facts == {}
    assert checkpoint.current_step_id == "move"
    assert records[0]["binding"]["schema_version"] == "registered.collection.binding.v1"
    assert records[0]["lease_source"]["lease_id"] == live.original.identity.lease_id
    assert records[0]["inputs"]["object_surface_visibility"] == "UNKNOWN"
    from cloud_edge_robot_arm.edge.evidence.conditions import (
        ConditionSpec,
        OnlineEvidenceSnapshot,
        evaluate_conditions,
    )

    facts = live.tracker.facts(args["observation"], args["robot_state"])
    verdict = evaluate_conditions(
        [ConditionSpec("target_visible", "object")],
        OnlineEvidenceSnapshot(args["observation"], args["robot_state"], facts),
        now=args["observation"].captured_at,
    )[0]
    assert verdict.status.value == "UNKNOWN"


@pytest.mark.parametrize("problem", ["expired", "cancelled", "source", "write"])
def test_registered_collection_does_not_publish_invalid_or_unwritten_binding(
    tmp_path, monkeypatch, problem
):
    from datetime import timedelta

    application, _, live, protocol, args, clock, records, consume = consumer_context(
        tmp_path, monkeypatch
    )
    if problem == "expired":
        clock[0] = args["observation"].captured_at + timedelta(seconds=5)
    elif problem == "cancelled":
        live.repository.request_cancel(live.original.identity.job_id)
    elif problem == "source":
        protocol["source_hashes"] = {**protocol["source_hashes"], "src/foreign.py": "f" * 64}
    else:

        def full_disk(_value):
            raise OSError("synthetic full disk")

        live.recorder.record_grounding = full_disk
    with pytest.raises((ValueError, RuntimeError, OSError)):
        application._collect_grounded_step(
            live, 0, args["observation"], protocol, consume_capture=consume
        )
    assert records == []


def test_registered_collection_cli_prepares_only_its_distinct_protocol(
    tmp_path, monkeypatch, capsys
):
    import json
    import sys

    from scripts.collect_native_calibration import main

    from cloud_edge_robot_arm.research.native_calibration_collection import read_protocol

    output = tmp_path / "cli"
    monkeypatch.setattr(
        sys,
        "argv",
        ["collect", "--prepare-registered-collection-protocol", "--output", str(output)],
    )
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["execution_admitted"] is False
    assert read_protocol(output)["schema_version"] == "native.calibration.operational.v7"
    assert not list(output.rglob("*.db"))


def test_registered_collection_cli_rejects_execution_arguments_before_output(tmp_path, monkeypatch):
    import sys

    from scripts.collect_native_calibration import main

    output = tmp_path / "rejected"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--prepare-registered-collection-protocol",
            "--assignment-id",
            "native-r595-0001",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output.exists()
