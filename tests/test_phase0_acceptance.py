from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError
from scripts.validate_contract_examples import validate_contract_examples

from cloud_edge_robot_arm.contracts import (
    ActionResult,
    CloudCommand,
    CommandAck,
    EdgeEvent,
    FailureSummary,
    Pose,
    RobotState,
    TaskContract,
    Telemetry,
)

ROOT = Path(__file__).resolve().parents[1]


def test_phase_zero_models_export_json_schema() -> None:
    models: list[type[BaseModel]] = [
        TaskContract,
        Telemetry,
        CloudCommand,
        CommandAck,
        EdgeEvent,
        FailureSummary,
        RobotState,
        ActionResult,
        Pose,
    ]

    for model in models:
        schema = model.model_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema

    task_schema = TaskContract.model_json_schema()
    assert {"task_id", "plan_version", "command_seq", "timestamp"}.issubset(
        task_schema["properties"]
    )


def test_contract_example_directories_have_five_valid_and_five_invalid_examples() -> None:
    valid_examples = sorted((ROOT / "contracts" / "examples" / "valid").glob("*.json"))
    invalid_examples = sorted((ROOT / "contracts" / "examples" / "invalid").glob("*.json"))

    assert len(valid_examples) >= 5
    assert len(invalid_examples) >= 5


def test_valid_and_invalid_contract_examples_are_classified_correctly() -> None:
    result = validate_contract_examples(ROOT / "contracts" / "examples")

    assert result.valid_total >= 5
    assert result.invalid_total >= 5
    assert result.valid_failures == []
    assert result.invalid_failures == []


def test_invalid_contract_examples_fail_pydantic_or_edge_validation() -> None:
    invalid_examples = sorted((ROOT / "contracts" / "examples" / "invalid").glob("*.json"))

    for path in invalid_examples:
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            TaskContract.model_validate(payload)
        except ValidationError:
            continue
        assert validate_contract_examples(ROOT / "contracts" / "examples").invalid_failures == []
