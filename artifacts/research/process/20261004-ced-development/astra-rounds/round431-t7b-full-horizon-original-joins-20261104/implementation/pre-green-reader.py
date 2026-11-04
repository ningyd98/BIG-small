"""Offline full-S original-byte structural audit; never a producer or admission.

The new schema deliberately cannot use a step120 prefix receipt as full-action
authority. Publicly constructed bytes, including the test fixture's synthetic
COMMAND D rows, remain SOFTWARE_ONLY even when every structural join succeeds.
JSON owner seconds use the exact decimal representation of their decoded number;
non-integral ns are unsupported rather than rounded. No filesystem is consulted.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime
from fractions import Fraction
from typing import Any, cast

from cloud_edge_robot_arm.contracts import ActionResult, TaskStep
from cloud_edge_robot_arm.research.native_clock_source_v2 import ClockTupleV2
from cloud_edge_robot_arm.research.operational_prefix_schema_v1 import (
    validate_operational_originals_v1,
)
from cloud_edge_robot_arm.research.raw_episode_v3 import (
    FrameAcquisitionV3,
    RawCommandV3,
    RawIntervalV3,
    RawPhysicsStepV3,
    TypedActionSpanV3,
    _annotations,
    _camera_hash,
    _checked,
    _digest,
    _identifier,
    _number,
    _owner_decode,
    _snapshot,
    _sources,
    _transform,
    _vector,
)
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.vision.native_completion_horizon import (
    RationalCompletionHorizonV1,
    completion_horizon_rational_v1,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame
from cloud_edge_robot_arm.vision.owner_registration import VisualOriginalPlan

_CONTROLLER = "src/cloud_edge_robot_arm/edge/runtime/skill_executor.py"
_RECIPE = set(
    (
        "skill dt_numerator dt_denominator registered_dt_s original_timeout_ns "
        "original_expected_ns "
        "compiled_timeout_ns compiled_expected_ns effective_owner_required_ns "
        "builtin_tail_included "
        "registered_wait_steps"
    ).split()
)
_SIDE = set(
    (
        "schema_version source_session_id episode_id domain_sha256 span_id capture_acquisition_id "
        "terminal_acquisition_id recipe originals open_boundary close_boundary hold_interval_ids "
        "wait_interval_ids"
    ).split()
)
_PREREG = set(
    (
        "schema_version source_session_id episode_id domain_sha256 span_id recipe step_id attempt "
        "original_plan_sha256 executed_step_sha256 owner_requirements_sha256 "
        "controller_source_sha256 "
        "tail_inclusion_basis"
    ).split()
)
_RAW = set(
    (
        "schema_version source_session_id domain_sha256 operational_ledger "
        "backend_operation_ledger "
        "pending_operation_ids incomplete_operation_ids legacy_operations "
        "legacy_intervals legacy_clock_pairs "
        "legacy_reset_journal legacy_reset_metadata legacy_reset_result "
        "legacy_reset_count legacy_physics "
        "legacy_commands legacy_frames legacy_frame_aux legacy_actions legacy_purpose_allocations "
        "last_captured_frame explicit_acquisitions observed_episode_id "
        "observed_total_physics_steps source_hashes"
    ).split()
)
_BOUNDARY_SLIM = set("operation_id kind phase episode_id physics_step error_type error".split())
_QUALIFICATION = ("same_session_private_producer_unavailable", "execution_deadline_guards_unproven")
_RECORDS = (
    ("legacy_intervals", "interval", RawIntervalV3),
    ("legacy_physics", "physics", RawPhysicsStepV3),
    ("legacy_commands", "command", RawCommandV3),
    ("legacy_actions", "action", TypedActionSpanV3),
    ("legacy_frames", "frame", FrameAcquisitionV3),
)


@dataclass(frozen=True, slots=True)
class FullHorizonOriginalAuditV1:
    source_sha256: str
    preregistration_sha256: str
    sidecar_sha256: str
    source_session_id: str
    episode_id: str
    span_id: str
    horizon: RationalCompletionHorizonV1
    dispatch_step: int | None
    return_step: int | None
    terminal_step: int | None
    execution_steps: tuple[int, ...]
    hold_steps: tuple[int, ...]
    wait_steps: tuple[int, ...]
    allocated_action_count: int
    allocated_acquisition_count: int
    recorded_physics_count: int
    original_failures: tuple[str, ...]
    structural_reasons: tuple[str, ...]
    coverage_status: str
    schema_version: str = field(default="native.completion.full-horizon-audit.v1", init=False)
    qualification_reasons: tuple[str, ...] = field(default=_QUALIFICATION, init=False)
    producer_status: str = field(default="UNAVAILABLE", init=False)
    guard_status: str = field(default="NOT_PROVEN", init=False)
    evidence_scope: str = field(default="SOFTWARE_ONLY", init=False)
    native_authority: str = field(default="UNAVAILABLE", init=False)
    qualification: str = field(default="UNKNOWN", init=False)


def _shape(value: Any, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("exact original schema keys required")
    return cast(dict[str, Any], value)


def _integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("original built-in integer required")
    return cast(int, value)


def _text(value: Any) -> str:
    if type(value) is not str or not value:
        raise ValueError("nonempty original identity required")
    return cast(str, value)


def _sha(value: Any) -> str:
    text = _text(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError("lowercase SHA256 required")
    return text


def _decode(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate original JSON key")
            result[key] = value
        return result

    def finite(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("nonfinite original JSON number")
        return number

    if type(raw) is not bytes:
        raise ValueError("immutable original bytes required")
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_float=finite, parse_constant=finite)
    except (UnicodeDecodeError, RecursionError) as error:
        raise ValueError("bounded UTF-8 original JSON required") from error
    if type(value) is not dict:
        raise ValueError("original object required")
    return cast(dict[str, Any], value)


def _files(side: dict[str, Any], originals: Mapping[str, bytes]) -> dict[str, bytes]:
    if not isinstance(originals, Mapping):
        raise ValueError("original bytes mapping required")
    roles = _shape(side["originals"], {"partial_attempts", "preregistration"})
    result = {}
    paths = set()
    for role, pin in roles.items():
        _shape(pin, {"path", "bytes", "sha256"})
        path = _text(pin["path"])
        if (
            path.startswith("/")
            or "\\" in path
            or any(p in {"", ".", ".."} for p in path.split("/"))
            or path in paths
        ):
            raise ValueError("unique safe relative original path required")
        paths.add(path)
        data = originals.get(path)
        if (
            type(data) is not bytes
            or len(data) != _integer(pin["bytes"], 1)
            or hashlib.sha256(data).hexdigest() != _sha(pin["sha256"])
        ):
            raise ValueError("original bytes/size/SHA256 missing or changed")
        result[role] = data
    if set(originals) != paths:
        raise ValueError("exact two original file roles required")
    return result


def _legacy_pair(value: Any) -> list[Any]:
    if type(value) is not list or len(value) != 4:
        raise ValueError("complete four-field original clock tuple required")
    _integer(value[0], 1)
    _integer(value[1])
    _integer(value[3])
    stamp = datetime.fromisoformat(_text(value[2]))
    offset = stamp.utcoffset()
    if stamp.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError("aware UTC original sample required")
    if value[1] > value[3]:
        raise ValueError("reversed original clock bracket")
    return cast(list[Any], value)


def _earlier(first: Any, second: Any) -> bool:
    a, b = _legacy_pair(first), _legacy_pair(second)
    return bool(a[0] < b[0] and a[3] <= b[1])


def _command_payload(value: Any) -> None:
    common = set(
        (
            "type accepted reason after_emergency_stop sim_time_s "
            "episode_id physics_step command_seq"
        ).split()
    )
    if type(value) is not dict:
        raise ValueError("original command mapping required")
    kind = value.get("type")
    if kind in {"joint_target", "hold_current_joints"}:
        extra = {"target_positions_rad", "applied_target_positions_rad"}
        if kind == "joint_target" and value.get("accepted") is False:
            extra.remove("applied_target_positions_rad")
    elif kind == "gripper":
        extra = {"target_open"}
    elif kind == "emergency_stop":
        extra = set()
    else:
        raise ValueError("unknown command kind")
    _shape(value, common | extra)
    if (
        type(value["accepted"]) is not bool
        or type(value["after_emergency_stop"]) is not bool
        or type(value["reason"]) is not str
    ):
        raise ValueError("strict command boolean/reason required")
    _identifier(value["episode_id"])
    _integer(value["physics_step"])
    _integer(value["command_seq"], 1)
    if _number(value["sim_time_s"]) < 0:
        raise ValueError("negative command sim time")
    if kind == "gripper":
        if type(value["target_open"]) is not bool:
            raise ValueError("strict target_open required")
    else:
        for key in extra:
            _vector(value[key], 7)


def _action_result(value: Any) -> None:
    result = _shape(value, set(ActionResult.model_fields))
    if type(result["success"]) is not bool:
        raise ValueError("strict result success required")
    _integer(result["duration_ms"])
    for key in ("action_id", "action_type"):
        _identifier(result[key])
    for key in ("error_code", "error_message"):
        if result[key] is not None and type(result[key]) is not str:
            raise ValueError("strict optional error string required")
    for key in ("state_before", "state_after", "details"):
        if type(result[key]) is not dict:
            raise ValueError("complete result mapping required")
    stamps = [datetime.fromisoformat(_text(result[key])) for key in ("started_at", "finished_at")]
    if (
        any(stamp.tzinfo is None or stamp.utcoffset() is None for stamp in stamps)
        or stamps[0] > stamps[1]
    ):
        raise ValueError("ordered aware action timestamps required")
    if "physics_steps" in result["details"]:
        _integer(result["details"]["physics_steps"])
    ActionResult.model_validate(result)


def _record_values(row: dict[str, Any], kind: str) -> None:
    """RawV3 semantic rules that do not require an invented episode identity."""
    _integer(row["record_seq"], 1)
    if kind == "interval":
        _identifier(row["interval_id"])
        _legacy_pair(row["start"])
        if row["start_sim_time_s"] < 0:
            raise ValueError("negative interval simulation time")
        ends = [row[key] for key in ("end", "end_step", "end_sim_time_s")]
        if any(value is None for value in ends):
            if row["disposition"] == "COMPLETE" or not all(value is None for value in ends):
                raise ValueError("partial end fields must all be absent")
        elif (
            not _earlier(row["start"], row["end"])
            or row["end_step"] < row["start_step"]
            or row["end_sim_time_s"] < row["start_sim_time_s"]
        ):
            raise ValueError("reversed interval")
        if row["disposition"] != "COMPLETE" and not row["error"]:
            raise ValueError("incomplete interval reason required")
    elif kind == "physics":
        _integer(row["physics_step"], 1)
        _sha(row["previous_state_hash"])
        _snapshot(row["post_state_payload"])
        _snapshot(row["control_payload"], control=True)
        for key in ("physics_interval_id", "control_interval_id", "purpose_interval_id"):
            _identifier(row[key])
    elif kind == "command":
        _integer(row["command_seq"], 1)
        for key in ("interval_id", "parent_interval_id"):
            _identifier(row[key])
        if row["owner_action_span_id"] is not None:
            _identifier(row["owner_action_span_id"])
        _command_payload(row["command_payload"])
        if row["effective_from_step"] is not None and not row["command_payload"]["accepted"]:
            raise ValueError("rejected command cannot have an effective step")
    elif kind == "action":
        for key in ("span_id", "step_id", "interval_id"):
            _identifier(row[key])
        _integer(row["attempt"], 1)
        _integer(row["command_seq_start"], 1)
        if row["command_seq_end"] < row["command_seq_start"]:
            raise ValueError("reversed half-open command range")
        original = _owner_decode(VisualOriginalPlan, row["original_plan"])
        if row["step_id"] not in original.requirements:
            raise ValueError("action requirements missing")
        if row["executed_step_payload"] is not None:
            step = _shape(row["executed_step_payload"], set(TaskStep.model_fields))
            for key in ("timeout_ms", "expected_duration_ms"):
                _integer(step[key], 1)
            _integer(step["retry_limit"])
            TaskStep.model_validate(step)
        if row["returned_result"] is not None:
            _action_result(row["returned_result"])
        if row["disposition"] != "RETURNED" and not row["error"]:
            raise ValueError("incomplete action reason required")
    else:
        for key in ("acquisition_id", "interval_id"):
            _identifier(row[key])
        if row["camera_state_payload"] is not None:
            _camera_hash(row["camera_state_payload"])
        if row["joined_physics_observation_hash"] is not None:
            _sha(row["joined_physics_observation_hash"])
        for digest in row["pass_state_hashes"]:
            _sha(digest)
        for key in ("file_hashes", "transform_source_hashes"):
            _sources(row[key], allow_empty=True)
        if row["observation_payload"] is not None:
            observation = _shape(row["observation_payload"], set(RGBDObservation.model_fields))
            _integer(observation["width"], 1)
            _integer(observation["height"], 1)
            _number(observation["sim_time_s"])
            for key in ("intrinsics", "camera_to_world"):
                for value in observation[key]:
                    _number(value)
            RGBDObservation.model_validate(observation)
        if row["source_acquisition_id"] is not None:
            _identifier(row["source_acquisition_id"])
            if (
                row["input_role"] != "ONLINE"
                or not row["transform_payload"]
                or not row["transform_source_hashes"]
            ):
                raise ValueError("derived capture source/transform missing")
            _transform(row["transform_payload"])
        elif row["transform_payload"] is not None or row["transform_source_hashes"]:
            raise ValueError("transform lacks source acquisition")


class _Audit:
    def __init__(
        self,
        side: dict[str, Any],
        raw: dict[str, Any],
        prereg: dict[str, Any],
        horizon: RationalCompletionHorizonV1,
    ) -> None:
        self.side, self.raw, self.prereg, self.horizon = side, raw, prereg, horizon
        self.reasons: list[str] = []
        self.failures: list[str] = []
        self.events: dict[int, dict[str, Any]] = {}
        self.intervals: dict[str, dict[str, Any]] = {}
        self.states: dict[int, dict[str, Any]] = {}
        self.dispatch: int | None = None
        self.returned: int | None = None
        self.terminal: int | None = None
        self.execution: list[int] = []
        self.hold: list[int] = []
        self.wait: list[int] = []

    def check(self, good: bool, reason: str) -> bool:
        if not good and reason not in self.reasons:
            self.reasons.append(reason)
        return good

    def failure(self, value: Any) -> None:
        self.failures.append(json.dumps(value, sort_keys=True))

    def strict_records(self) -> None:
        for key, kind, record_type in _RECORDS:
            annotations = _annotations(record_type)
            keys = {item.name for item in fields(record_type)} - {"identity"}
            for index, original in enumerate(self.raw[key]):
                name = "schema"
                try:
                    row = _shape(original, keys)
                    if kind == "action":
                        if type(row["attempt"]) is not int or row["attempt"] < 1:
                            self.check(False, "invalid_action_attempt")
                        if row["returned_result"] is not None:
                            try:
                                _action_result(row["returned_result"])
                            except (ValueError, TypeError, KeyError) as error:
                                self.check(False, "invalid_action_result")
                                raise ValueError("invalid complete ActionResult") from error
                    for name in sorted(keys):
                        if kind == "interval" and name in {"start", "end"}:
                            if row[name] is not None:
                                _legacy_pair(row[name])
                        else:
                            _checked(row[name], annotations[name], decode=True)
                    name = "semantics"
                    _record_values(row, kind)
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    IndexError,
                    AttributeError,
                    OverflowError,
                ) as error:
                    self.check(False, f"invalid_{kind}_record:{index}:{name}")
                    self.failure(
                        {
                            "record_kind": kind,
                            "index": index,
                            "field": name,
                            "error": str(error),
                            "original": original,
                        }
                    )

    def complete_inventory(self) -> None:
        """Every original return and capture is part of the denominator."""
        commands = self.raw["legacy_commands"]
        returned: list[tuple[int, int, dict[str, Any]]] = []
        recorded: list[tuple[int, int, dict[str, Any]]] = []
        for row in commands:
            try:
                event = self.event_for(row["interval_id"], "COMMAND")
                recorded.append((event["operation_id"], row["command_seq"], row["command_payload"]))
            except (ValueError, KeyError, TypeError) as error:
                self.check(False, "command_result_inventory_mismatch")
                self.failure({"unmatched_command": row, "error": str(error)})
        for event in self.events.values():
            if event["kind"] != "COMMAND":
                continue
            number = event["operation_id"]
            try:
                result = _shape(event["end"]["result"], {"physics_state", "command_records"})
                _snapshot(result["physics_state"])
                if not self.check(
                    result["physics_state"] == self.states[event["end"]["physics_step"]],
                    "command_physics_original_mismatch",
                ):
                    self.failure(
                        {"operation_id": number, "command_physics_state": result["physics_state"]}
                    )
                if type(result["command_records"]) is not list:
                    raise ValueError("complete returned command list required")
                for payload in result["command_records"]:
                    try:
                        _command_payload(payload)
                        item = (number, payload["command_seq"], payload)
                        returned.append(item)
                        if (
                            item not in recorded
                            or payload["accepted"] is not True
                            or payload["after_emergency_stop"]
                            or payload["type"] == "emergency_stop"
                        ):
                            self.failure(
                                {"operation_id": number, "original_command_return": payload}
                            )
                        self.check(
                            payload["accepted"] is True
                            and not payload["after_emergency_stop"]
                            and payload["type"] != "emergency_stop",
                            "original_rejected_or_emergency_command",
                        )
                    except (ValueError, KeyError, TypeError) as error:
                        self.check(False, "command_result_inventory_mismatch")
                        self.failure(
                            {
                                "operation_id": number,
                                "invalid_command_return": payload,
                                "error": str(error),
                            }
                        )
            except (ValueError, KeyError, TypeError) as error:
                self.check(False, "command_result_inventory_mismatch")
                self.failure(
                    {"operation_id": number, "original_command_event": event, "error": str(error)}
                )
        returned_keys = [(op, sequence) for op, sequence, _ in returned]
        self.check(
            returned == recorded and len(set(returned_keys)) == len(returned_keys),
            "command_result_inventory_mismatch",
        )
        self.check(
            [sequence for _, sequence, _ in returned] == list(range(1, len(returned) + 1)),
            "command_result_inventory_mismatch",
        )
        captures = [event for event in self.events.values() if event["kind"] == "CAPTURE"]
        event_ids = [event["acquisition_id"] for event in captures]
        frame_ids = [
            frame.get("acquisition_id")
            for frame in self.raw["legacy_frames"]
            if type(frame) is dict
        ]
        allocations = self.raw["operational_ledger"]["allocated_acquisition_ids"]
        self.check(
            event_ids == frame_ids == allocations and len(set(event_ids)) == len(event_ids),
            "capture_event_inventory_mismatch",
        )
        for event in captures:
            number, acquisition = event["operation_id"], event["acquisition_id"]
            frames = [
                frame
                for frame in self.raw["legacy_frames"]
                if type(frame) is dict and frame.get("acquisition_id") == acquisition
            ]
            try:
                if (
                    len(frames) != 1
                    or allocations.count(acquisition) != 1
                    or frames[0]["interval_id"] != f"operation-{number}"
                ):
                    raise ValueError("unique allocated original capture frame missing")
                if frames[0]["source_acquisition_id"] is not None:
                    self.check(False, "unsupported_derived_capture")
                    raise ValueError("derived input cannot substitute for direct CAPTURE")
                self.frame(acquisition, event["end"]["physics_step"])
            except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
                self.check(False, "capture_event_inventory_mismatch")
                self.failure(
                    {
                        "operation_id": number,
                        "acquisition_id": acquisition,
                        "missing_or_invalid_capture": str(error),
                    }
                )

    def legacy_time(self) -> None:
        """Use MONOTONIC pair order only; D association is by operation ID."""
        pairs = self.raw["legacy_clock_pairs"]
        by_sequence: dict[int, list[Any]] = {}
        domains = set()
        previous = -1
        for expected, original in enumerate(pairs, 1):
            pair = ClockTupleV2.from_payload(original)
            domains.add(pair.clock_domain_id)
            self.check(
                pair.sequence == expected
                and pair.sequence not in by_sequence
                and previous <= pair.mono_before_ns,
                "legacy_clock_tee_order_mismatch",
            )
            previous = pair.mono_after_ns
            by_sequence[pair.sequence] = [
                pair.sequence,
                pair.mono_before_ns,
                original["utc_at"],
                pair.mono_after_ns,
            ]
        self.check(len(domains) == 1, "legacy_clock_domain_mismatch")
        referenced = set()
        for interval in self.raw["legacy_intervals"]:
            for key in ("start", "end"):
                pair = _legacy_pair(interval[key])
                self.check(
                    pair == by_sequence.get(pair[0]) and pair[0] not in referenced,
                    "legacy_interval_clock_tee_mismatch",
                )
                referenced.add(pair[0])
        previous_end = None
        for event in self.events.values():
            if event["kind"] == "RESET":
                continue
            operation = self.raw["legacy_operations"][str(event["operation_id"])]
            row = operation["row"]
            if previous_end is not None:
                self.check(
                    _earlier(previous_end, row["start"]), "legacy_D_operation_order_mismatch"
                )
            previous_end = row["end"]
            if operation["parent"] != "unbracketed-operations":
                parent = self.intervals[operation["parent"]]
                self.check(
                    parent["kind"]
                    in {
                        "EXECUTOR_ATTEMPT",
                        "SETTLE",
                        "WAIT",
                        "VERIFY_ADVANCE",
                        "HOLD",
                        "TERMINATION",
                    }
                    and _earlier(parent["start"], row["start"])
                    and _earlier(row["end"], parent["end"]),
                    "purpose_clock_containment_mismatch",
                )
        selected = [
            row for row in self.raw["legacy_actions"] if row["span_id"] == self.side["span_id"]
        ]
        if len(selected) != 1:
            raise ValueError("unique attempt clock source missing")
        attempt = self.intervals[selected[0]["interval_id"]]
        before = self.intervals[f"operation-{self.side['open_boundary']['operation_id']}"]
        terminal = self.intervals[f"operation-{self.side['close_boundary']['operation_id']}"]
        self.check(
            _earlier(before["end"], attempt["start"]), "preopen_attempt_clock_order_mismatch"
        )
        self.check(
            _earlier(attempt["start"], attempt["end"])
            and _earlier(attempt["end"], terminal["start"]),
            "purpose_clock_containment_mismatch",
        )
        previous_end = attempt["end"]
        purposes = [
            self.intervals[name]
            for name in self.side["hold_interval_ids"] + self.side["wait_interval_ids"]
        ]
        for purpose in sorted(purposes, key=lambda row: row["start_step"]):
            self.check(
                _earlier(previous_end, purpose["start"])
                and _earlier(purpose["end"], terminal["start"]),
                "purpose_clock_containment_mismatch",
            )
            previous_end = purpose["end"]

    def retain_failures(self) -> None:
        ledger = self.raw["operational_ledger"]
        for key in ("failures", "backend_observer_failures", "super_audit_failures"):
            self.failures.extend(json.dumps(row, sort_keys=True) for row in ledger[key])
        for key in ("pending_operation_ids", "incomplete_operation_ids"):
            if self.raw[key]:
                self.failures.append(json.dumps({key: self.raw[key]}, sort_keys=True))
        for group in (
            ledger["events"],
            self.raw["legacy_actions"],
            self.raw["legacy_intervals"],
            self.raw["backend_operation_ledger"],
        ):
            for row in group:
                result = row.get("returned_result")
                if (
                    row.get("error")
                    or row.get("error_type")
                    or (
                        "returned_result" in row
                        and (result is None or result.get("success") is not True)
                    )
                    or row.get("disposition") in {"PARTIAL", "ABORTED", "REJECTED"}
                ):
                    self.failures.append(json.dumps(row, sort_keys=True))
        self.check(not self.failures, "original_failures_or_pending_operations")

    def operations(self) -> None:
        raw, side = self.raw, self.side
        ledger = raw["operational_ledger"]
        for obj in (raw, ledger, self.prereg):
            self.check(
                all(obj[key] == side[key] for key in ("source_session_id", "domain_sha256")),
                "source_session_or_domain_mismatch",
            )
        self.check(
            raw["observed_episode_id"] == side["episode_id"] == self.prereg["episode_id"],
            "episode_mismatch",
        )
        expected_backend, seqs, tokens = [], [], set()
        previous_upper = -1
        for index, event in enumerate(ledger["events"], 1):
            number = event["operation_id"]
            self.check(
                number not in self.events and event["attempt_seq"] == index,
                "duplicate_or_reordered_D_operations",
            )
            self.events[number] = event
            self.check(
                event["source_session_id"] == side["source_session_id"]
                and event["domain_sha256"] == side["domain_sha256"],
                "D_source_domain_mismatch",
            )
            begin, end = event["begin"], event["end"]
            if not self.check(
                begin is not None and end is not None and event["bracket"] is not None,
                "incomplete_D_boundaries",
            ):
                continue
            for phase, boundary in (("BEGIN", begin), ("END", end)):
                self.check(
                    boundary["operation_id"] == number
                    and boundary["kind"] == event["kind"]
                    and boundary["phase"] == phase,
                    "D_boundary_identity_mismatch",
                )
                self.check(
                    boundary["error"] is None and boundary["error_type"] is None,
                    "failed_original_boundary",
                )
                expected_backend.append({key: boundary[key] for key in _BOUNDARY_SLIM})
            self.check(
                end["episode_id"] == side["episode_id"]
                and (event["kind"] == "RESET" or begin["episode_id"] == side["episode_id"]),
                "foreign_operation_episode",
            )
            self.check(begin["parameters"] == end["parameters"], "changed_operation_parameters")
            bracket = event["bracket"]
            self.check(
                bracket["domain_sha256"] == side["domain_sha256"]
                and bracket["event_identity"] == event["token_identity"]
                and event["token_identity"] not in tokens,
                "D_bracket_identity_mismatch",
            )
            tokens.add(event["token_identity"])
            self.check(
                event["begin_ns"] == bracket["lower_ns"]
                and previous_upper <= bracket["lower_ns"] <= bracket["upper_ns"],
                "unordered_D_brackets",
            )
            previous_upper = bracket["upper_ns"]
            seqs.extend([event["begin_seq"], event["mark_seq"], event["end_seq"]])
        self.check(
            all(type(v) is int and v >= 1 for v in seqs)
            and all(
                type(a) is int and type(b) is int and a < b
                for a, b in zip(seqs, seqs[1:], strict=False)
            ),
            "D_sequence_gap_or_reorder",
        )
        self.check(
            expected_backend == raw["backend_operation_ledger"],
            "backend_D_full_denominator_mismatch",
        )
        rows = raw["legacy_intervals"]
        self.intervals = {row["interval_id"]: row for row in rows}
        self.check(len(self.intervals) == len(rows), "duplicate_original_interval")
        for interval in rows:
            self.check(
                interval["disposition"] == "COMPLETE"
                and interval["error"] is None
                and interval["end"] is not None,
                "incomplete_original_interval",
            )
            if interval["end"] is not None:
                self.check(
                    interval["start_step"] <= interval["end_step"]
                    and interval["start"][0] < interval["end"][0],
                    "reversed_original_interval",
                )
        operations = raw["legacy_operations"]
        self.check(
            set(operations)
            == {str(number) for number, event in self.events.items() if event["kind"] != "RESET"},
            "legacy_operation_denominator_mismatch",
        )
        for key, operation in operations.items():
            event = self.events[int(key)]
            row = operation["row"]
            self.check(
                row == self.intervals.get(f"operation-{key}")
                and row["interval_id"] == f"operation-{key}",
                "operation_interval_join_mismatch",
            )
            self.check(
                operation["parameters"] == event["begin"]["parameters"]
                and operation["acquisition_id"] == event["acquisition_id"],
                "operation_metadata_join_mismatch",
            )
            self.check(
                row["start_step"] == event["begin"]["physics_step"]
                and row["end_step"] == event["end"]["physics_step"],
                "operation_interval_steps_mismatch",
            )
        resets = [event for event in self.events.values() if event["kind"] == "RESET"]
        self.check(
            len(resets) == 1 and raw["legacy_reset_count"] == 1, "reset_denominator_mismatch"
        )
        self.check(
            bool(resets)
            and resets[0] is next(iter(self.events.values()))
            and resets[0]["end"]["result"] == raw["legacy_reset_result"],
            "reset_original_mismatch",
        )

    def event_for(self, interval_id: str, kind: str) -> dict[str, Any]:
        interval = self.intervals[interval_id]
        matches = [
            event
            for event in self.events.values()
            if f"operation-{event['operation_id']}" == interval_id and event["kind"] == kind
        ]
        if len(matches) != 1 or interval["end"] is None:
            raise ValueError("unique completed original operation join missing")
        return matches[0]

    def physical(self) -> None:
        raw, side = self.raw, self.side
        reset = raw["legacy_reset_result"]
        dt = raw["legacy_reset_metadata"]["config"]["physics_dt_s"]
        self.check(
            type(dt) is float
            and dt.hex() == self.horizon.registered_dt_hex
            and reset["physics_dt_s"] == dt,
            "actual_reset_dt_encoding_mismatch",
        )
        previous = reset["physics_state"]
        _snapshot(previous)
        self.check(previous["physics_step"] == 0, "reset_step_not_zero")
        self.states[0] = previous
        commands = raw["legacy_commands"]
        self.check(
            [row["command_seq"] for row in commands] == list(range(1, len(commands) + 1)),
            "command_sequence_denominator_mismatch",
        )
        for row in commands:
            event = self.event_for(row["interval_id"], "COMMAND")
            payload = row["command_payload"]
            self.check(
                payload in event["end"]["result"]["command_records"]
                and payload["command_seq"] == row["command_seq"],
                "command_original_payload_mismatch",
            )
            self.check(
                payload["episode_id"] == side["episode_id"]
                and payload["physics_step"]
                == event["begin"]["physics_step"]
                == event["end"]["physics_step"],
                "command_source_step_mismatch",
            )
            self.check(
                raw["legacy_operations"][str(event["operation_id"])]["parent"]
                == row["parent_interval_id"],
                "command_parent_mismatch",
            )
        targets = list(reset["initial_controller_targets"]["joints_rad"])
        fingers = list(reset["initial_controller_targets"]["fingers_m"])
        pending: list[tuple[int, list[float]]] = []
        delay = _integer(reset["actuator_delay_steps"])
        used_events: set[int] = set()
        previous_physics_end = 0
        for expected_step, row in enumerate(raw["legacy_physics"], 1):
            n = _integer(row["physics_step"], 1)
            state, control = row["post_state_payload"], row["control_payload"]
            _snapshot(state)
            _snapshot(control, control=True)
            self.check(
                n == expected_step and n not in self.states,
                "physics_missing_duplicate_or_reordered",
            )
            self.check(
                row["previous_state_hash"] == _digest(previous), "physics_state_chain_mismatch"
            )
            self.check(
                state["episode_id"] == control["episode_id"] == side["episode_id"]
                and state["physics_step"] == control["physics_step"] == n,
                "physics_control_identity_mismatch",
            )
            ce, pe = (
                self.event_for(row["control_interval_id"], "CONTROL"),
                self.event_for(row["physics_interval_id"], "PHYSICS"),
            )
            self.check(previous_physics_end < ce["begin_seq"], "cross_step_operation_reorder")
            previous_physics_end = pe["end_seq"]
            self.check(
                ce["operation_id"] not in used_events and pe["operation_id"] not in used_events,
                "reused_control_physics_operation",
            )
            used_events.update((ce["operation_id"], pe["operation_id"]))
            self.check(
                ce["end_seq"] < pe["begin_seq"]
                and ce["begin"]["physics_step"]
                == ce["end"]["physics_step"]
                == pe["begin"]["physics_step"]
                == n - 1
                and pe["end"]["physics_step"] == n,
                "control_physics_order_or_step_mismatch",
            )
            self.check(
                ce["end"]["result"].get("control_state") == control
                and pe["end"]["result"].get("physics_state") == state,
                "control_physics_original_payload_mismatch",
            )
            for event in (ce, pe):
                self.check(
                    raw["legacy_operations"][str(event["operation_id"])]["parent"]
                    == row["purpose_interval_id"],
                    "physics_purpose_original_mismatch",
                )
            for command in commands:
                payload = command["command_payload"]
                if payload["physics_step"] != n - 1:
                    continue
                command_event = self.event_for(command["interval_id"], "COMMAND")
                self.check(command_event["end_seq"] < ce["begin_seq"], "command_after_control")
                if payload["accepted"] is not True:
                    self.check(False, "rejected_command_in_originals")
                    continue
                self.check(payload["after_emergency_stop"] is False, "command_after_emergency_stop")
                kind = payload["type"]
                if kind == "joint_target":
                    applied = [
                        max(-2.8, min(2.8, value)) for value in payload["target_positions_rad"]
                    ]
                    self.check(
                        payload["applied_target_positions_rad"] == applied,
                        "joint_target_clipping_mismatch",
                    )
                    if delay:
                        pending.append((n + delay, applied))
                    else:
                        targets = applied
                    self.check(
                        command["effective_from_step"] == n + delay, "joint_target_delay_mismatch"
                    )
                elif kind == "hold_current_joints":
                    targets = list(previous["joint_positions_rad"])
                    pending.clear()
                    self.check(
                        payload["target_positions_rad"]
                        == payload["applied_target_positions_rad"]
                        == targets
                        and command["effective_from_step"] == n,
                        "hold_measured_target_mismatch",
                    )
                elif kind == "gripper":
                    fingers = [0.039 if payload["target_open"] else 0.0] * 2
                else:
                    self.check(False, "unknown_control_command")
            while pending and pending[0][0] <= n:
                _, targets = pending.pop(0)
            self.check(
                control["applied_joint_targets_rad"] == targets
                and control["finger_control_targets_m"] == fingers,
                "controller_command_replay_mismatch",
            )
            self.check(
                control["pre_joint_positions_rad"] == previous["joint_positions_rad"],
                "control_pre_state_mismatch",
            )
            for q, target, bias, gain, limits, actual in zip(
                control["pre_joint_positions_rad"],
                targets,
                control["pre_gravity_bias_nm"],
                control["actuator_gains"],
                control["actuator_ctrl_ranges"],
                control["control_rad"],
                strict=True,
            ):
                if not self.check(gain > 0, "invalid_actuator_gain"):
                    continue
                wanted = max(
                    limits[0], min(limits[1], q + max(-0.10, min(0.10, target - q)) + bias / gain)
                )
                self.check(
                    math.isclose(actual, wanted, rel_tol=0, abs_tol=1e-12),
                    "actuator_control_equation_mismatch",
                )
            self.states[n] = state
            previous = state
        self.check(
            used_events
            == {
                event["operation_id"]
                for event in self.events.values()
                if event["kind"] in {"CONTROL", "PHYSICS"}
            },
            "physical_operation_denominator_mismatch",
        )
        self.check(
            raw["observed_total_physics_steps"] == len(raw["legacy_physics"]),
            "observed_physics_denominator_mismatch",
        )

    def frame(self, acquisition: str, step: int) -> dict[str, Any]:
        matches = [row for row in self.raw["legacy_frames"] if row["acquisition_id"] == acquisition]
        if len(matches) != 1:
            raise ValueError("unique original acquisition missing")
        frame = matches[0]
        event = self.event_for(frame["interval_id"], "CAPTURE")
        observation = RGBDObservation.model_validate(frame["observation_payload"])
        self.check(
            observation.model_dump(mode="json") == frame["observation_payload"],
            "observation_canonical_mismatch",
        )
        state = self.states[step]
        params, result = event["begin"]["parameters"], event["end"]["result"]
        sensor = result["sensor_frame"]
        sensor_values = dict(_shape(sensor, {item.name for item in fields(SensorFrame)}))
        for key in ("rgb", "valid_mask"):
            if sensor_values[key] is not None:
                sensor_values[key] = base64.b64decode(
                    _shape(sensor_values[key], {"original_bytes_base64"})["original_bytes_base64"],
                    validate=True,
                )
        sensor_values["captured_at"] = datetime.fromisoformat(sensor_values["captured_at"])
        for key in ("depth", "intrinsics", "camera_to_world"):
            sensor_values[key] = tuple(sensor_values[key])
        reconstructed = observation_from_sensor_frame(
            SensorFrame(**sensor_values), source="mujoco_camera"
        )
        self.check(
            reconstructed.model_dump(mode="json") == frame["observation_payload"],
            "capture_sensor_bytes_mismatch",
        )
        self.check(
            event["acquisition_id"] == acquisition
            and event["begin"]["physics_step"] == event["end"]["physics_step"] == step,
            "capture_step_or_identity_mismatch",
        )
        self.check(
            params["physics_state"] == state
            and frame["joined_physics_observation_hash"] == _digest(state),
            "capture_physics_join_mismatch",
        )
        self.check(
            frame["camera_state_payload"] == params["camera_state"]
            and frame["pass_state_hashes"]
            == result["pass_state_hashes"]
            == [_camera_hash(params["camera_state"])] * 3,
            "capture_camera_pass_join_mismatch",
        )
        self.check(
            sensor["frame_id"] == observation.frame_id
            and sensor["episode_id"] == observation.episode_id == self.side["episode_id"]
            and sensor["sim_time_s"] == observation.sim_time_s == state["sim_time_s"],
            "capture_sensor_join_mismatch",
        )
        return event

    def action_window(self) -> None:
        raw, side, prereg = self.raw, self.side, self.prereg
        ledger = raw["operational_ledger"]
        actions = raw["legacy_actions"]
        self.check(
            ledger["allocated_action_ids"] == [side["span_id"]] and len(actions) == 1,
            "action_allocation_or_contamination",
        )
        selected = [row for row in actions if row["span_id"] == side["span_id"]]
        if len(selected) != 1:
            raise ValueError("unique original action span missing")
        action = selected[0]
        self.check(
            prereg["span_id"] == side["span_id"]
            and action["step_id"] == prereg["step_id"]
            and action["attempt"] == prereg["attempt"],
            "preregistered_action_identity_mismatch",
        )
        self.check(
            _digest(side["recipe"]) == _digest(prereg["recipe"]), "preregistered_recipe_mismatch"
        )
        original = cast(
            VisualOriginalPlan, _owner_decode(VisualOriginalPlan, action["original_plan"])
        )
        compiled = TaskStep.model_validate(action["executed_step_payload"])
        requirement = original.requirements[action["step_id"]]
        original_step = requirement.original_step
        self.check(
            original.identity.episode_id == side["episode_id"]
            and compiled.step_id == action["step_id"]
            and compiled.skill == original_step.skill,
            "original_compiled_action_identity_mismatch",
        )
        self.check(
            _digest(action["original_plan"]) == prereg["original_plan_sha256"]
            and _digest(action["executed_step_payload"]) == prereg["executed_step_sha256"]
            and _digest(action["original_plan"]["requirements"][action["step_id"]])
            == prereg["owner_requirements_sha256"],
            "preregistered_payload_digest_mismatch",
        )
        self.check(
            prereg["controller_source_sha256"] == raw["source_hashes"].get(_CONTROLLER)
            and all(
                raw["source_hashes"].get(key) == value
                for key, value in original.source_hashes.items()
            ),
            "controller_or_owner_source_hash_mismatch",
        )
        duration = Fraction(str(requirement.expected_duration_s)) * 1_000_000_000
        self.check(duration.denominator == 1, "owner_duration_not_exact_integer_ns")
        derived = dict(
            skill=original_step.skill.value,
            original_timeout_ns=original_step.timeout_ms * 1_000_000,
            original_expected_ns=original_step.expected_duration_ms * 1_000_000,
            compiled_timeout_ns=compiled.timeout_ms * 1_000_000,
            compiled_expected_ns=compiled.expected_duration_ms * 1_000_000,
            effective_owner_required_ns=duration.numerator,
        )
        self.check(
            all(side["recipe"][key] == value for key, value in derived.items()),
            "recipe_original_duration_mismatch",
        )
        self.check(
            self.horizon.skill in {"MOVE_ABOVE", "APPROACH"}, "unsupported_full_horizon_skill"
        )
        self.check(
            not self.horizon.builtin_tail_included and prereg["tail_inclusion_basis"] is None,
            "tail_inclusion_not_proven",
        )
        interval = self.intervals[action["interval_id"]]
        self.dispatch = _integer(interval["start_step"])
        self.returned = _integer(interval["end_step"])
        self.terminal = self.dispatch + self.horizon.total_steps
        holds, waits = side["hold_interval_ids"], side["wait_interval_ids"]
        inventory = [
            row
            for row in raw["legacy_physics"]
            if self.dispatch < row["physics_step"] <= self.terminal
        ]
        for row in inventory:
            step, purpose = row["physics_step"], row["purpose_interval_id"]
            if step <= self.returned:
                self.execution.append(step)
            elif purpose in holds:
                self.hold.append(step)
            elif purpose in waits:
                self.wait.append(step)
        self.check(
            interval["kind"] == "EXECUTOR_ATTEMPT"
            and self.dispatch <= self.returned <= self.terminal,
            "action_return_outside_horizon",
        )
        result = action["returned_result"]
        self.check(
            action["disposition"] == "RETURNED"
            and action["error"] is None
            and result is not None
            and result["success"] is True
            and result["error_code"] is None,
            "action_not_successfully_returned",
        )
        if result is not None:
            self.check(
                result["action_type"] == self.horizon.skill
                and result["details"].get("physics_steps") == self.returned - self.dispatch,
                "action_result_step_mismatch",
            )
        before = self.frame(side["capture_acquisition_id"], self.dispatch)
        terminal = self.frame(side["terminal_acquisition_id"], self.terminal)
        self.check(
            side["open_boundary"]["operation_id"] == before["operation_id"]
            and side["close_boundary"]["operation_id"] == terminal["operation_id"],
            "open_close_capture_boundary_mismatch",
        )
        self.check(
            ledger["allocated_acquisition_ids"]
            == [row["acquisition_id"] for row in raw["legacy_frames"]]
            and len(set(ledger["allocated_acquisition_ids"]))
            == len(ledger["allocated_acquisition_ids"]),
            "capture_allocation_denominator_mismatch",
        )
        self.check(
            not set(holds) & set(waits)
            and len(set(holds)) == len(holds)
            and len(set(waits)) == len(waits),
            "hold_wait_overlap_or_duplicate",
        )
        self.check(
            set(holds + waits) <= set(raw["legacy_purpose_allocations"]),
            "hold_wait_allocation_missing",
        )
        for names, kind in ((holds, "HOLD"), (waits, "WAIT")):
            for name in names:
                purpose = self.intervals[name]
                self.check(
                    purpose["kind"] == kind
                    and self.returned
                    <= purpose["start_step"]
                    < purpose["end_step"]
                    <= self.terminal,
                    "hold_wait_interval_outside_window",
                )
                if kind == "HOLD":
                    accepted = [
                        row
                        for row in raw["legacy_commands"]
                        if row["parent_interval_id"] == name
                        and row["command_payload"]["type"] == "hold_current_joints"
                        and row["command_payload"]["accepted"] is True
                        and row["command_payload"]["physics_step"] == purpose["start_step"]
                    ]
                    self.check(
                        len(accepted) == 1
                        and sum(row["parent_interval_id"] == name for row in raw["legacy_commands"])
                        == 1,
                        "hold_current_joints_original_missing",
                    )
        # Iterate bounded actual inventory, never range(claimed_horizon).
        self.check(
            len(inventory) == self.horizon.total_steps, "full_horizon_physics_inventory_mismatch"
        )
        previous = self.dispatch
        for row in inventory:
            step, purpose = row["physics_step"], row["purpose_interval_id"]
            self.check(step == previous + 1, "window_missing_duplicate_or_reordered_step")
            previous = step
            if step <= self.returned:
                self.check(purpose == action["interval_id"], "execution_step_foreign_purpose")
            elif purpose not in holds and purpose not in waits:
                self.check(False, "uncovered_post_return_step")
            bound = self.intervals[purpose]
            self.check(
                bound["start_step"] < step <= bound["end_step"], "step_outside_purpose_interval"
            )
            pe = self.event_for(row["physics_interval_id"], "PHYSICS")
            self.check(
                before["end_seq"] < pe["begin_seq"] < pe["end_seq"] < terminal["begin_seq"],
                "window_capture_operation_order",
            )
        self.check(
            len(self.wait) == self.horizon.registered_wait_steps,
            "registered_wait_step_count_mismatch",
        )
        for name in holds + waits:
            bound = self.intervals[name]
            self.check(
                sum(row["purpose_interval_id"] == name for row in inventory)
                == bound["end_step"] - bound["start_step"],
                "noncontinuous_hold_wait_interval",
            )
        window_events = [
            event
            for event in self.events.values()
            if before["end_seq"] < event["begin_seq"] < terminal["end_seq"]
        ]
        for event in window_events:
            self.check(
                event["kind"] in {"CONTROL", "PHYSICS", "COMMAND", "CAPTURE"},
                "unknown_advance_or_reset_in_window",
            )
        action_commands = []
        for row in raw["legacy_commands"]:
            event = self.event_for(row["interval_id"], "COMMAND")
            if before["end_seq"] < event["begin_seq"] < terminal["end_seq"]:
                if row["parent_interval_id"] == action["interval_id"]:
                    action_commands.append(row["command_seq"])
                    self.check(
                        row["owner_action_span_id"] == side["span_id"]
                        and self.dispatch <= row["command_payload"]["physics_step"] < self.returned,
                        "action_command_outside_attempt",
                    )
                else:
                    self.check(
                        row["parent_interval_id"] in holds
                        and row["command_payload"]["type"] == "hold_current_joints"
                        and row["owner_action_span_id"] is None,
                        "foreign_post_return_command",
                    )
        self.check(
            len(action_commands) == action["command_seq_end"] - action["command_seq_start"]
            and all(
                value == action["command_seq_start"] + i for i, value in enumerate(action_commands)
            ),
            "action_command_denominator_mismatch",
        )


def audit_completion_horizon_originals_v1(
    *, sidecar_bytes: bytes, originals: Mapping[str, bytes]
) -> FullHorizonOriginalAuditV1:
    """Recompute original structural coverage while preserving UNKNOWN authority."""
    side = _shape(_decode(sidecar_bytes), _SIDE)
    if side["schema_version"] != "native.completion.full-horizon-sidecar.v1":
        raise ValueError("full-horizon sidecar schema required")
    for key in (
        "source_session_id",
        "episode_id",
        "span_id",
        "capture_acquisition_id",
        "terminal_acquisition_id",
    ):
        _text(side[key])
    _sha(side["domain_sha256"])
    for key in ("open_boundary", "close_boundary"):
        _integer(_shape(side[key], {"operation_id"})["operation_id"], 1)
    for key in ("hold_interval_ids", "wait_interval_ids"):
        if type(side[key]) is not list:
            raise ValueError("explicit interval ID list required")
        for value in side[key]:
            _text(value)
    horizon = completion_horizon_rational_v1(**_shape(side["recipe"], _RECIPE))
    files = _files(side, originals)
    raw = _shape(_decode(files["partial_attempts"]), _RAW)
    prereg = _shape(_decode(files["preregistration"]), _PREREG)
    if (
        raw["schema_version"] != "native.completion.full-horizon-originals.v1"
        or prereg["schema_version"] != "native.completion.horizon-preregistration.v1"
    ):
        raise ValueError(
            "new full-horizon original schemas required; prefix receipts cannot substitute"
        )
    _shape(prereg["recipe"], _RECIPE)
    for key in ("source_session_id", "episode_id", "span_id", "step_id"):
        _text(prereg[key])
    for key in (
        "domain_sha256",
        "original_plan_sha256",
        "executed_step_sha256",
        "owner_requirements_sha256",
        "controller_source_sha256",
    ):
        _sha(prereg[key])
    _integer(prereg["attempt"], 1)
    for key in (
        "backend_operation_ledger",
        "pending_operation_ids",
        "incomplete_operation_ids",
        "legacy_intervals",
        "legacy_clock_pairs",
        "legacy_reset_journal",
        "legacy_physics",
        "legacy_commands",
        "legacy_frames",
        "legacy_actions",
        "legacy_purpose_allocations",
    ):
        if type(raw[key]) is not list:
            raise ValueError("complete original list required")
    for key in (
        "legacy_operations",
        "legacy_reset_metadata",
        "legacy_reset_result",
        "legacy_frame_aux",
        "source_hashes",
    ):
        if type(raw[key]) is not dict:
            raise ValueError("complete original object required")
    for row in raw["backend_operation_ledger"]:
        _shape(row, _BOUNDARY_SLIM)
    ledger = validate_operational_originals_v1(raw["operational_ledger"])
    audit = _Audit(side, raw, prereg, horizon)
    # Malformed/missing recognizable action subrecords are evidence gaps, not a
    # reason to drop an allocated denominator or to invent a successful result.
    for operation in (
        audit.retain_failures,
        audit.strict_records,
        audit.operations,
        audit.physical,
        audit.complete_inventory,
        audit.legacy_time,
        audit.action_window,
    ):
        try:
            operation()
        except (
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            AttributeError,
            OverflowError,
        ) as error:
            audit.check(False, f"{operation.__name__}_original_gap:{type(error).__name__}:{error}")
    return FullHorizonOriginalAuditV1(
        hashlib.sha256(files["partial_attempts"]).hexdigest(),
        hashlib.sha256(files["preregistration"]).hexdigest(),
        hashlib.sha256(sidecar_bytes).hexdigest(),
        side["source_session_id"],
        side["episode_id"],
        side["span_id"],
        horizon,
        audit.dispatch,
        audit.returned,
        audit.terminal,
        tuple(audit.execution),
        tuple(audit.hold),
        tuple(audit.wait),
        len(ledger["allocated_action_ids"]),
        len(ledger["allocated_acquisition_ids"]),
        len(raw["legacy_physics"]),
        tuple(audit.failures),
        tuple(audit.reasons),
        "INCOMPLETE" if audit.reasons else "STRUCTURALLY_COMPLETE",
    )
