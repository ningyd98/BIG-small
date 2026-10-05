"""Read-only risk diagnostics from registered originals, never source admission.

SOFTWARE_ONLY clock/reference carriers permit numeric reconstruction. Their
bytes, declared history and raw consistency are not measurement authenticity.
Actual raw-v3 acquisition, independent calibration and committed risk labels
are separate missing publishers; this module cannot qualify a method.
"""

from __future__ import annotations

import base64
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.datasets.rgbd.quality import _near_duplicate, perceptual_signature
from cloud_edge_robot_arm.research.admission import (
    InitialSourceAdmissionAuditor,
    InitialSourceRegistration,
)
from cloud_edge_robot_arm.research.risk_sources import (
    RawCaseRegistration,
    RiskSourceAuditor,
    RiskSourceRegistration,
    Status,
    _array,
    _copied,
    _hashes,
    _integer,
    _inventory,
    _json,
    _number,
    _physics,
    _plain,
    _relative,
    _reset,
    _rows,
    _safe,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.risk.features import extract_risk_features

_REVIEWED_RAW = "0bf79e3ef94ee33fec9e3642b7c77f956efa6e1a1f015de17d567d0f585c983a"
_RAW_PATH = "src/cloud_edge_robot_arm/research/risk_sources.py"
_MISSING = (
    "raw_v3_clock_publisher_unavailable",
    "independent_calibration_publisher_unavailable",
    "derived_risk_commits_unavailable",
    "risk_selection_replay_unavailable",
)
_CAMERA_KEYS = {"calibration_version", "intrinsics", "camera_to_world", "width", "height", "source"}
_SPLITS = {"train", "calibration", "selection", "test"}
_HISTORIES = {
    "UNVIEWED",
    "UNKNOWN",
    "DEVELOPMENT_FEEDBACK",
    "VIEWED",
    "TUNED",
    "TRAIN",
    "CALIBRATION",
    "SELECTION",
    "TEST",
}


def required_supervision_source_paths() -> tuple[str, ...]:
    """Additional current validating bytes required alongside the RAW inventory."""
    return (
        "src/cloud_edge_robot_arm/research/risk_supervision.py",
        "src/cloud_edge_robot_arm/research/admission.py",
        "src/cloud_edge_robot_arm/research/freeze_evidence.py",
        "src/cloud_edge_robot_arm/research/resource_plan.py",
        "src/cloud_edge_robot_arm/research/protocol.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/quality.py",
        "src/cloud_edge_robot_arm/vision/risk/features.py",
        "src/cloud_edge_robot_arm/vision/risk/models.py",
    )


def _identity(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", value):
        raise ValueError("opaque registered identity required")


@dataclass(frozen=True)
class RiskObservationAllocation:
    sample_id: str
    case_id: str
    observation_id: str
    split: Literal["train", "calibration", "selection", "test"]
    previous_sample_id: str | None = None

    def __post_init__(self) -> None:
        for value in (self.sample_id, self.case_id, self.observation_id):
            _identity(value)
        if self.previous_sample_id is not None:
            _identity(self.previous_sample_id)
        if self.split not in _SPLITS:
            raise ValueError("unknown allocation split")


@dataclass(frozen=True)
class RiskComponentHistory:
    group_id: str
    used_purposes: Sequence[str]

    def __post_init__(self) -> None:
        _identity(self.group_id)
        history = tuple(self.used_purposes)
        if any(type(value) is not str or value not in _HISTORIES for value in history):
            raise ValueError("unsupported original usage history")
        if len(set(history)) != len(history) or ("UNVIEWED" in history and len(history) > 1):
            raise ValueError("contradictory original usage history")
        object.__setattr__(self, "used_purposes", history)


@dataclass(frozen=True)
class RiskDiagnosticMeasurements:
    artifact_root: Path
    original_file_hashes: Mapping[str, str]
    clock_path: str | None = None
    calibration_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_root", Path(self.artifact_root).absolute())
        object.__setattr__(self, "original_file_hashes", _hashes(self.original_file_hashes))
        for name in (self.clock_path, self.calibration_path):
            if name is not None:
                _relative(name)
                if name not in self.original_file_hashes:
                    raise ValueError("measurement path absent from original inventory")


@dataclass(frozen=True)
class RiskSupervisionRegistration:
    raw_registration: RiskSourceRegistration
    allocations: Sequence[RiskObservationAllocation]
    histories: Sequence[RiskComponentHistory]
    initial_registration: InitialSourceRegistration | None = None
    diagnostic_measurements: RiskDiagnosticMeasurements | None = None

    def __post_init__(self) -> None:
        raw = self.raw_registration
        if type(raw) is not RiskSourceRegistration:
            raise TypeError("concrete RAW registration required, never a receipt/auditor")
        if any(type(case) is not RawCaseRegistration for case in raw.cases):
            raise TypeError("concrete original case registrations required")
        if any(
            case.marker_registration is not None
            and type(case.marker_registration) is not PoseMarkerRegistration
            for case in raw.cases
        ):
            raise TypeError("concrete marker registrations required")
        if raw.current_source_hashes.get(_RAW_PATH) != _REVIEWED_RAW:
            raise ValueError("corrected independently reviewed RAW fix2 dependency required")
        if not set(required_supervision_source_paths()) <= set(raw.current_source_hashes):
            raise ValueError("registration omits risk supervision production helper sources")
        object.__setattr__(
            self,
            "raw_registration",
            RiskSourceRegistration(
                Path(raw.artifact_root).absolute(),
                Path(raw.source_root).absolute(),
                dict(raw.current_source_hashes),
                tuple(
                    replace(
                        case,
                        marker_registration=replace(case.marker_registration)
                        if case.marker_registration is not None
                        else None,
                    )
                    for case in raw.cases
                ),
                replace(raw.criteria),
                raw.current_role_binding,
            ),
        )
        for name, concrete in (
            ("allocations", RiskObservationAllocation),
            ("histories", RiskComponentHistory),
        ):
            original = tuple(getattr(self, name))
            if any(type(item) is not concrete for item in original):
                raise TypeError(f"concrete {name} registrations required")
            object.__setattr__(self, name, tuple(replace(item) for item in original))
        initial = self.initial_registration
        if initial is not None:
            if type(initial) is not InitialSourceRegistration:
                raise TypeError("concrete INITIAL registration required")
            object.__setattr__(
                self,
                "initial_registration",
                InitialSourceRegistration(
                    initial.evidence_root,
                    initial.protocol_path,
                    initial.current_role_binding,
                    dict(initial.current_source_hashes),
                ),
            )
        measured = self.diagnostic_measurements
        if measured is not None:
            if type(measured) is not RiskDiagnosticMeasurements:
                raise TypeError("concrete diagnostic measurements required")
            object.__setattr__(self, "diagnostic_measurements", replace(measured))


@dataclass(frozen=True)
class RiskSupervisionAudit:
    status: Status
    diagnostic_status: Status
    actual_source_status: Status
    reasons: tuple[str, ...]
    counts: Mapping[str, int]
    rows: tuple[Mapping[str, Any], ...]
    original_file_hashes: Mapping[str, str]
    current_source_hashes: Mapping[str, str]
    source_scope: Literal["SOFTWARE_ONLY", "RECORDED_RAW_DIAGNOSTICS", "MIXED_DIAGNOSTICS"]
    raw_execution_status: Status = "UNKNOWN"
    initial_source_status: Status = "UNKNOWN"
    schema_version: Literal["ced.risk-supervision-audit.v1"] = "ced.risk-supervision-audit.v1"

    def __post_init__(self) -> None:
        for name in ("counts", "rows", "original_file_hashes", "current_source_hashes"):
            object.__setattr__(self, name, _copied(getattr(self, name)))
        object.__setattr__(self, "reasons", tuple(self.reasons))


def _shape(value: Any, keys: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{what} object schema differs")
    return value


def _utc(value: Any) -> datetime:
    if type(value) is not str:
        raise ValueError("clock acquisition UTC string required")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("clock acquisition timezone required")
    return result


def _raw_frames(directory: Path) -> list[RGBDObservation]:
    observations: dict[str, RGBDObservation] = {}
    for folder in ("frames", "supervision-frames", "raw-frames"):
        base = directory / folder
        if not base.exists():
            continue
        for path in sorted(base.iterdir()):
            metadata = _json(path / "observation.json")
            if not isinstance(metadata, dict):
                raise ValueError("original frame metadata object required")
            values = {key: metadata[key] for key in RGBDObservation.model_fields if key in metadata}
            values.update(
                rgb_png_base64=base64.b64encode((path / "rgb.png").read_bytes()).decode(),
                depth_float32_base64=base64.b64encode((path / "depth.f32").read_bytes()).decode(),
            )
            frame = RGBDObservation.model_validate(values)
            if frame.observation_id in observations and observations[frame.observation_id] != frame:
                raise ValueError("original observation identity has contradictory bytes")
            observations[frame.observation_id] = frame
    return sorted(observations.values(), key=lambda frame: (frame.sim_time_s, frame.observation_id))


def _clock(payload: Any, cases: Mapping[str, tuple[Any, list[RGBDObservation]]]) -> None:
    data = _shape(payload, {"schema_version", "source_scope", "cases"}, "clock")
    if (
        data["schema_version"] != "risk.clock-diagnostic.v1"
        or data["source_scope"] != "SOFTWARE_ONLY"
    ):
        raise ValueError("only explicit SOFTWARE_ONLY diagnostic clock supported")
    if not isinstance(data["cases"], dict) or set(data["cases"]) != set(cases):
        raise ValueError("clock original attempt coverage differs")
    for case_id, (raw, frames) in cases.items():
        rows = data["cases"][case_id]
        if not isinstance(rows, list) or len(rows) != len(raw):
            raise ValueError("clock complete reset-to-terminal coverage differs")
        previous: tuple[float, datetime] | None = None
        acquired: dict[float, datetime] = {}
        for index, row in enumerate(rows):
            _shape(row, {"physics_step", "sim_time_s", "monotonic_s", "utc"}, "clock row")
            sim, mono, utc = (
                _number(row["sim_time_s"]),
                _number(row["monotonic_s"]),
                _utc(row["utc"]),
            )
            if _integer(row["physics_step"]) != index or abs(sim - raw[index].sim_time_s) > 1e-9:
                raise ValueError("clock step/simulation identity differs")
            if mono < 0 or (previous and (mono <= previous[0] or utc <= previous[1])):
                raise ValueError("clock acquisition timestamps are not strictly increasing")
            # For this software carrier, both measured clock channels must agree.
            if previous and abs((utc - previous[1]).total_seconds() - (mono - previous[0])) > 1e-6:
                raise ValueError("clock UTC/monotonic intervals differ")
            previous = (mono, utc)
            acquired[sim] = utc
        for frame in frames:
            matching = [utc for sim, utc in acquired.items() if abs(sim - frame.sim_time_s) <= 1e-9]
            if len(matching) != 1 or matching[0] != frame.captured_at:
                raise ValueError("original frame acquisition has no exact clock association")


def _calibration(payload: Any, frames: Sequence[RGBDObservation]) -> tuple[float, ...]:
    data = _shape(
        payload,
        {
            "schema_version",
            "source_scope",
            "geometry_scope",
            "observation_ids",
            "camera_domain",
            "pairs_m",
        },
        "calibration",
    )
    if (
        data["schema_version"] != "risk.calibration-diagnostic.v1"
        or data["source_scope"] != "SOFTWARE_ONLY"
        or data["geometry_scope"] != "MARKER_CENTER_TRANSLATION"
    ):
        raise ValueError("only SOFTWARE_ONLY marker-center calibration diagnostics supported")
    identities, pairs = data["observation_ids"], data["pairs_m"]
    if (
        not isinstance(identities, list)
        or not identities
        or any(type(item) is not str for item in identities)
        or len(set(identities)) != len(identities)
        or set(identities) & {frame.observation_id for frame in frames}
        or not isinstance(pairs, list)
        or len(pairs) != len(identities)
    ):
        raise ValueError("independent diagnostic calibration reference coverage differs")
    domain = _shape(data["camera_domain"], _CAMERA_KEYS, "calibration camera domain")
    _array(domain["intrinsics"], (4,))
    _array(domain["camera_to_world"], (16,))
    if _integer(domain["width"]) == 0 or _integer(domain["height"]) == 0:
        raise ValueError("calibration camera dimensions must be positive strict integers")
    for identity in identities:
        _identity(identity)
    for frame in frames:
        if domain != {key: frame.model_dump(mode="json")[key] for key in _CAMERA_KEYS}:
            raise ValueError("calibration camera domain differs from original target frames")
    residuals = []
    for pair in pairs:
        _shape(pair, {"estimate", "reference"}, "calibration reference pair")
        estimate, reference = _array(pair["estimate"], (3,)), _array(pair["reference"], (3,))
        residual = math.dist(estimate, reference)
        if not math.isfinite(residual):
            raise ValueError("calibration residual exceeds finite floating range")
        residuals.append(residual)
    return tuple(residuals)


def _marker_point(
    registration: RiskSourceRegistration, case: RawCaseRegistration
) -> tuple[float, ...]:
    marker = case.marker_registration
    if marker is None:
        raise FileNotFoundError("registered_marker_point_unavailable")
    assets = [
        name
        for name, digest in registration.current_source_hashes.items()
        if digest == marker.marked_asset_sha256 and name.endswith(".xml")
    ]
    if len(assets) != 1:
        raise FileNotFoundError("registered_marker_asset_unavailable")
    root = ElementTree.parse(_safe(registration.source_root, assets[0])).getroot()
    body = root.find(".//body[@name='object']")
    if body is None:
        raise ValueError("registered marker object body missing")
    cells = [
        geom
        for geom in body.findall("geom")
        if re.fullmatch(r"pose_marker_(?:v1|color_v2)_r[0-5]c[0-5]", geom.get("name", ""))
    ]
    if len(cells) != 36 or marker.marker_id != 7:
        raise ValueError("unsupported registered marker-plane geometry")
    positions = [_array([float(v) for v in geom.attrib["pos"].split()], (3,)) for geom in cells]
    sizes = [_array([float(v) for v in geom.attrib["size"].split()], (3,)) for geom in cells]
    if any(geom.get("type") != "box" for geom in cells) or any(
        abs(size[0] * 12 - marker.marker_size_m) > 1e-9
        or abs(size[1] * 12 - marker.marker_size_m) > 1e-9
        or abs(position[2] - positions[0][2]) > 1e-9
        or abs(size[2] - sizes[0][2]) > 1e-9
        for position, size in zip(positions, sizes, strict=True)
    ):
        raise ValueError("registered marker plane dimensions differ")
    return (
        sum(position[0] for position in positions) / 36,
        sum(position[1] for position in positions) / 36,
        positions[0][2] + sizes[0][2],
    )


def _truth_point(raw: Any, local: Sequence[float]) -> tuple[float, ...]:
    rotation, origin = raw.object_geom_rotation_row_major, raw.object_geom_position_m
    return tuple(
        origin[i] + sum(rotation[i * 3 + j] * local[j] for j in range(3)) for i in range(3)
    )


def _allocation_closure(
    registration: RiskSupervisionRegistration, frames: Mapping[str, list[RGBDObservation]]
) -> None:
    allocations = registration.allocations
    expected = {
        (case_id, frame.observation_id) for case_id, items in frames.items() for frame in items
    }
    actual = {(item.case_id, item.observation_id) for item in allocations}
    if (
        len({item.sample_id for item in allocations}) != len(allocations)
        or len(actual) != len(allocations)
        or actual != expected
    ):
        raise ValueError("allocation does not cover every original observation exactly once")
    by_observation = {(item.case_id, item.observation_id): item for item in allocations}
    for case_id, items in frames.items():
        for index, frame in enumerate(items):
            current = by_observation[(case_id, frame.observation_id)]
            previous = by_observation[(case_id, items[index - 1].observation_id)] if index else None
            if current.previous_sample_id != (previous.sample_id if previous else None):
                raise ValueError("previous sample must be the adjacent earlier original frame")
            if previous and (
                previous.split != current.split or items[index - 1].sim_time_s >= frame.sim_time_s
            ):
                raise ValueError("previous original frame split/time differs")


def _histories(
    registration: RiskSupervisionRegistration,
    cases: Mapping[str, tuple[Any, list[RGBDObservation]]],
) -> bool:
    groups = {
        case.case_id: _reset(cases[case.case_id][0], case)
        for case in registration.raw_registration.cases
    }
    history = {item.group_id: tuple(item.used_purposes) for item in registration.histories}
    if len(history) != len(registration.histories) or set(history) != {
        scene.group_id for scene in groups.values()
    }:
        raise ValueError("history must retain every original source component")
    missing = False
    entries = []
    for item in registration.allocations:
        scene = groups[item.case_id]
        purposes = history[scene.group_id]
        known_uses = set(purposes) - {"UNVIEWED", "UNKNOWN"}
        if item.split != "train" and known_uses:
            raise ValueError("original usage history cannot become an independent holdout")
        if not purposes or "UNKNOWN" in purposes:
            missing = True
        frame = next(
            frame for frame in cases[item.case_id][1] if frame.observation_id == item.observation_id
        )
        physical = {
            key: value
            for key, value in scene.scene_parameters.items()
            if key not in {"camera", "light_intensity", "depth_noise_m", "invalid_depth_fraction"}
        }
        entries.append(
            (
                item,
                scene,
                frame,
                content_digest(
                    {"parameters": _plain(physical), "asset_family_hash": scene.asset_family_hash}
                ),
                perceptual_signature(frame),
            )
        )
    for i, (left, scene, frame, source, signature) in enumerate(entries):
        for right, other_scene, other, other_source, other_signature in entries[:i]:
            connected = (
                scene.group_id == other_scene.group_id
                or frame.episode_id == other.episode_id
                or source == other_source
                or scene.scene_hash == other_scene.scene_hash
                or frame.checksum_sha256 == other.checksum_sha256
                or _near_duplicate(signature, other_signature)
            )
            if connected and left.split != right.split:
                raise ValueError(
                    "connected original source/derivative observations span purpose splits"
                )
    return missing


class RiskSupervisionAuditor:
    """Application-owned registry; no callbacks, passed auditors or stored verdicts."""

    def __init__(self, registrations: Mapping[str, RiskSupervisionRegistration]) -> None:
        self._sources = {}
        for evidence_id, registration in registrations.items():
            _identity(evidence_id)
            if type(registration) is not RiskSupervisionRegistration:
                raise TypeError("concrete risk supervision registration required")
            self._sources[evidence_id] = replace(registration)

    def audit(self, evidence_id: str) -> RiskSupervisionAudit:
        counts = {
            "assigned_attempts": 0,
            "allocated_observations": 0,
            "missing_observations": 0,
            "task_labels": 0,
            "feature_rows": 0,
            "geometric_labels": 0,
            "motion_labels": 0,
        }
        registration = self._sources.get(evidence_id)
        if registration is None:
            return RiskSupervisionAudit(
                "UNKNOWN",
                "UNKNOWN",
                "UNKNOWN",
                ("evidence_id_not_registered",),
                counts,
                (),
                {},
                {},
                "SOFTWARE_ONLY",
            )
        raw_registration = registration.raw_registration
        counts["assigned_attempts"] = len(raw_registration.cases)
        counts["allocated_observations"] = sum(
            case.expected_counts["frames"] for case in raw_registration.cases
        )
        counts["missing_observations"] = counts["allocated_observations"]
        raw_audit = RiskSourceAuditor({"raw": raw_registration}).audit("raw", scope="RAW_EXECUTION")
        originals = dict(raw_audit.original_file_hashes)
        measured = registration.diagnostic_measurements
        if measured:
            originals.update(
                {
                    f"measurements/{name}": digest
                    for name, digest in measured.original_file_hashes.items()
                }
            )
        reasons = list(raw_audit.reasons) + list(_MISSING)
        diagnostic: Status = raw_audit.status
        actual: Status = "INVALID" if raw_audit.status == "INVALID" else "UNKNOWN"
        rows: list[Mapping[str, Any]] = []
        kinds = {case.source_kind for case in raw_registration.cases}
        scope: Literal["SOFTWARE_ONLY", "RECORDED_RAW_DIAGNOSTICS", "MIXED_DIAGNOSTICS"] = (
            "SOFTWARE_ONLY"
            if kinds == {"SOFTWARE_ONLY"}
            else "RECORDED_RAW_DIAGNOSTICS"
            if kinds == {"RECORDED_SIMULATION"}
            else "MIXED_DIAGNOSTICS"
        )
        initial = registration.initial_registration
        initial_status: Status = "UNKNOWN"
        if initial is None:
            reasons.append("initial_source_registration_unavailable")
        else:
            initial_result = InitialSourceAdmissionAuditor({"initial": initial}).audit("initial")
            initial_status = initial_result.status
            originals.update(
                {
                    f"initial/{name}": digest
                    for name, digest in initial_result.raw_file_hashes.items()
                }
            )
            reasons.extend(f"initial:{reason}" for reason in initial_result.reasons)
            if initial_result.status == "INVALID":
                actual = "INVALID"
            binding = raw_registration.current_role_binding
            if binding is None:
                reasons.append("raw_current_role_binding_unavailable")
            else:
                baseline = initial.current_role_binding
                if binding.bundle.cloud_snapshot != baseline.bundle.cloud_snapshot or dict(
                    binding.device_source_hashes
                ) != dict(baseline.device_source_hashes):
                    actual = "INVALID"
                    reasons.append("raw_initial_common_role_source_binding_mismatch")
        if raw_audit.status == "VALID":
            try:
                cases: dict[str, tuple[Any, list[RGBDObservation]]] = {}
                before = {}
                for case in raw_registration.cases:
                    directory = _safe(raw_registration.artifact_root, case.relative_directory)
                    before[case.case_id] = _inventory(
                        directory, case.original_file_hashes, complete=True
                    )
                    physics = _physics(
                        _json(directory / "physical-observations.json")
                        if case.layout == "CED_PILOT_RAW_V2"
                        else _rows(directory / "raw-physics.jsonl"),
                        case,
                    )
                    cases[case.case_id] = (physics, _raw_frames(directory))
                _allocation_closure(registration, {key: value[1] for key, value in cases.items()})
                history_missing = _histories(registration, cases)
                if history_missing:
                    diagnostic = "UNKNOWN"
                    reasons.append("original_usage_history_unavailable")
                residuals: tuple[float, ...] | None = None
                measurement_before = None
                if measured is None:
                    diagnostic = "UNKNOWN"
                    reasons.extend(
                        ("diagnostic_clock_unavailable", "diagnostic_calibration_unavailable")
                    )
                else:
                    measurement_before = _inventory(
                        measured.artifact_root, measured.original_file_hashes, complete=True
                    )
                    if measured.clock_path is None:
                        diagnostic = "UNKNOWN"
                        reasons.append("diagnostic_clock_unavailable")
                    else:
                        _clock(_json(_safe(measured.artifact_root, measured.clock_path)), cases)
                    if measured.calibration_path is None:
                        diagnostic = "UNKNOWN"
                        reasons.append("diagnostic_calibration_unavailable")
                    else:
                        residuals = _calibration(
                            _json(_safe(measured.artifact_root, measured.calibration_path)),
                            [frame for _, frames in cases.values() for frame in frames],
                        )
                allocations = {
                    (item.case_id, item.observation_id): item for item in registration.allocations
                }
                outcomes = {
                    item["case_id"]: item["physical_outcome"] for item in raw_audit.case_results
                }
                histories = {
                    item.group_id: tuple(item.used_purposes) for item in registration.histories
                }
                for case in raw_registration.cases:
                    physics, frames = cases[case.case_id]
                    scene = _reset(physics, case)
                    try:
                        local = _marker_point(raw_registration, case)
                    except FileNotFoundError as error:
                        local = None
                        diagnostic = "UNKNOWN"
                        reasons.append(f"{case.case_id}:{error}")
                    for index, frame in enumerate(frames):
                        allocation = allocations[(case.case_id, frame.observation_id)]
                        previous = frames[index - 1] if index else None
                        features = (
                            extract_risk_features(frame, previous, residuals)
                            if residuals is not None and measured and measured.clock_path
                            else None
                        )
                        point_error = None
                        if local is not None and case.marker_registration is not None:
                            estimate = detect_pose_marker(frame, case.marker_registration)
                            if (
                                estimate.status == "OBSERVED"
                                and estimate.marker_center_world_m is not None
                            ):
                                sample = next(
                                    item
                                    for item in physics
                                    if abs(item.sim_time_s - frame.sim_time_s) <= 1e-9
                                )
                                point_error = math.dist(
                                    estimate.marker_center_world_m, _truth_point(sample, local)
                                )
                                counts["geometric_labels"] += 1
                            else:
                                reasons.append(
                                    f"{allocation.sample_id}:marker_point_label_unavailable"
                                )
                        counts["task_labels"] += 1
                        counts["feature_rows"] += features is not None
                        rows.append(
                            {
                                "sample_id": allocation.sample_id,
                                "case_id": case.case_id,
                                "observation_id": frame.observation_id,
                                "split": allocation.split,
                                "source_kind": case.source_kind,
                                "group_id": scene.group_id,
                                "scene_hash": scene.scene_hash,
                                "used_purposes": histories[scene.group_id],
                                "geometry_scope": "MARKER_CENTER_TRANSLATION",
                                "online_features": {
                                    key: value.value for key, value in features.values.items()
                                }
                                if features
                                else None,
                                "offline_labels": {
                                    "failure": not outcomes[case.case_id]["success"],
                                    "geometric_error_m": point_error,
                                    "motion_residual_m_s": None,
                                },
                                "failure_horizon": {
                                    "kind": "ORIGINAL_EPISODE_TERMINAL",
                                    "evaluation_start_step": 120,
                                    "terminal_step": len(physics) - 1,
                                    "terminal_sim_time_s": physics[-1].sim_time_s,
                                },
                            }
                        )
                reasons.append("point_motion_label_reconstruction_unavailable")
                for case in raw_registration.cases:
                    directory = _safe(raw_registration.artifact_root, case.relative_directory)
                    if (
                        _inventory(directory, case.original_file_hashes, complete=True)
                        != before[case.case_id]
                    ):
                        raise ValueError(
                            "original source changed during supervision reconstruction"
                        )
                if measured and measurement_before != _inventory(
                    measured.artifact_root, measured.original_file_hashes, complete=True
                ):
                    raise ValueError("diagnostic measurement changed during reconstruction")
                if _inventory(
                    raw_registration.source_root,
                    raw_registration.current_source_hashes,
                    complete=False,
                ) != dict(raw_audit.current_source_hashes):
                    raise ValueError("validating production source changed during reconstruction")
                counts["missing_observations"] = counts["allocated_observations"] - len(rows)
            except (ValueError, TypeError, KeyError, IndexError, ElementTree.ParseError) as error:
                diagnostic = "INVALID"
                reasons.append(f"supervision_invalid:{error}")
                rows = []
                for name in ("task_labels", "feature_rows", "geometric_labels", "motion_labels"):
                    counts[name] = 0
            except OSError as error:
                diagnostic = "UNKNOWN"
                reasons.append(f"supervision_unavailable:{error}")
                rows = []
                for name in ("task_labels", "feature_rows", "geometric_labels", "motion_labels"):
                    counts[name] = 0
        if diagnostic == "INVALID":
            actual = "INVALID"
        return RiskSupervisionAudit(
            actual,
            diagnostic,
            actual,
            tuple(dict.fromkeys(reasons)),
            counts,
            tuple(rows),
            originals,
            raw_audit.current_source_hashes,
            scope,
            raw_execution_status=raw_audit.status,
            initial_source_status=initial_status,
        )
