"""Optional timeout metadata preserves legacy payloads and frozen-plan digests."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from cloud_edge_robot_arm.contracts import TaskContract
from cloud_edge_robot_arm.research.native_calibration_collection import canonical
from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
from cloud_edge_robot_arm.vision.owner_registration import VisualOriginalPlan
from tests.test_phase0_contracts import _future_contract
from tests.test_visual_owner_registration import values


@pytest.mark.parametrize("mode", ["python", "json"])
@pytest.mark.parametrize("explicit_none", [False, True])
def test_legacy_contract_metadata_does_not_change_serialized_payload(mode, explicit_none):
    payload = _future_contract(datetime(2026, 11, 21, tzinfo=UTC)).model_dump(mode=mode)
    payload.pop("metadata", None)
    for step in payload["steps"]:
        step.pop("metadata", None)
    expected = deepcopy(payload)
    if explicit_none:
        payload["metadata"] = None
        for step in payload["steps"]:
            step["metadata"] = None
    assert TaskContract.model_validate(payload).model_dump(mode=mode) == expected


@pytest.mark.parametrize("metadata", [{}, {"timeout_basis": "PHYSICS_STEPS"}])
def test_present_metadata_survives_nested_contract_serialization(metadata):
    contract = _future_contract(datetime(2026, 11, 21, tzinfo=UTC))
    contract.metadata = metadata
    contract.steps[0].metadata = metadata
    for payload in (
        contract.model_dump(),
        json.loads(contract.model_dump_json()),
        contract.model_dump(exclude_unset=True, exclude_defaults=True),
    ):
        assert payload["metadata"] == metadata
        assert payload["steps"][0]["metadata"] == metadata
    assert contract.model_dump(include={"metadata": True}) == {"metadata": metadata}
    without_metadata = contract.model_dump(exclude={"steps": {"__all__": {"metadata"}}})
    assert "metadata" not in without_metadata["steps"][0]


def test_contract_and_step_keep_structured_serialization_schema():
    schema = TaskContract.model_json_schema(mode="serialization")
    assert schema["properties"]["steps"]["items"]["$ref"] == "#/$defs/TaskStep"
    assert {"task_id", "steps", "task_target"} <= set(schema["required"])
    step = schema["$defs"]["TaskStep"]
    assert step["properties"]["timeout_ms"]["exclusiveMinimum"] == 0
    assert "metadata" not in schema["required"]
    assert "metadata" not in step["required"]


def test_legacy_original_reader_preserves_payload_and_digest():
    payload = values()["original"].to_payload()
    payload["contract"].pop("metadata", None)
    for step in payload["contract"]["steps"]:
        step.pop("metadata", None)
    expected_digest = sha256(canonical(payload)).hexdigest()
    original = _owner_decode(VisualOriginalPlan, payload)
    assert original.to_payload() == payload
    assert original.digest() == expected_digest
