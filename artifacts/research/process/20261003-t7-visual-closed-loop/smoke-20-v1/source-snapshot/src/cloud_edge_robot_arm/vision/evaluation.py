"""Visual execution policy and offline-only independent grounding evaluation."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.datasets.rgbd.models import SplitManifest
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import EpisodeOutcome
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter

ExecutionScope = Literal["CAPTURE_ONLY", "VISUAL_PLANNING", "VISION_CLOSED_LOOP"]


@dataclass(frozen=True)
class ExecutionPolicy:
    instruction: str
    scope: ExecutionScope = "VISION_CLOSED_LOOP"
    timeout_s: float = 120.0
    model_snapshot_hash: str = ""
    verification_budget: VerificationBudget = field(
        default_factory=lambda: VerificationBudget(
            max_reobservations=2,
            max_retries=0,
            max_no_progress=3,
            deadline_s=120.0,
        )
    )
    cancelled: Callable[[], bool] | None = field(default=None, repr=False, compare=False)
    output_dir: Path | None = None

    def __post_init__(self) -> None:
        if not self.instruction.strip() or not math.isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("instruction and finite positive episode timeout are required")
        if self.scope not in {"CAPTURE_ONLY", "VISUAL_PLANNING", "VISION_CLOSED_LOOP"}:
            raise ValueError("unknown execution scope")
        if self.scope != "CAPTURE_ONLY" and (
            len(self.model_snapshot_hash) != 64
            or any(c not in "0123456789abcdef" for c in self.model_snapshot_hash)
        ):
            raise ValueError("visual runs require an explicit frozen snapshot digest")


@dataclass(frozen=True, slots=True)
class VisualEpisodeOutcome(EpisodeOutcome):
    """Extension leaves the authoritative T5 dataclass and serialized evidence intact."""

    evaluation_scope: str = "VISION_CLOSED_LOOP"
    online_reported_complete: bool | None = False
    physical_success: bool = False
    verification_records: tuple[dict[str, Any], ...] = ()
    terminal_reason: str | None = None
    model_calls: int = 0
    executed_actions: int = 0
    observation_count: int = 0
    episode_id: str = ""


def combine_outcome(
    physical: EpisodeOutcome,
    *,
    online_complete: bool,
    records: tuple[dict[str, Any], ...],
    terminal_reason: str | None = None,
    model_calls: int = 0,
    executed_actions: int = 0,
    observation_count: int = 0,
    episode_id: str = "",
) -> VisualEpisodeOutcome:
    """Terminal conjunction only; this function cannot request another online action."""
    values = asdict(physical)
    success = online_complete and physical.success and terminal_reason is None
    values.update(
        success=success,
        status=(
            "SUCCESS" if success else "SAFETY_VIOLATION" if physical.safety_violation else "FAILED"
        ),
        failure_reason=None
        if success
        else terminal_reason or physical.failure_reason or "ONLINE_COMPLETION_NOT_VERIFIED",
    )
    return VisualEpisodeOutcome(
        **values,
        online_reported_complete=online_complete,
        physical_success=physical.success,
        verification_records=records,
        terminal_reason=terminal_reason,
        model_calls=model_calls,
        executed_actions=executed_actions,
        observation_count=observation_count,
        episode_id=episode_id,
    )


@dataclass(frozen=True)
class EvaluationReport:
    assigned: int
    succeeded: int
    blocked: int
    localization_errors_m: tuple[float, ...]
    recognition_coverage: float
    invalid_depth_rejection_rate: float
    latency_summary: dict[str, float | None]
    records: tuple[dict[str, Any], ...] = ()
    evaluation_scope: str = "OFFLINE_MODEL_GROUNDING"
    split: str = ""


def independent_top_center(labels: Mapping[str, Any]) -> tuple[float, float, float]:
    """Reference is the labeled rigid box top center, never the predicted pixel."""
    matches = [row for row in labels.get("instances", []) if row.get("role") == "target"]
    if len(matches) != 1:
        raise ValueError("independent target geometry is missing or ambiguous")
    target = matches[0]
    center, size = target["position"], target["half_size"]
    if len(center) != 3 or len(size) != 3:
        raise ValueError("independent target geometry must have three dimensions")
    values = (*center, *size)
    if any(not math.isfinite(float(v)) for v in values) or any(float(v) <= 0 for v in size):
        raise ValueError("independent target geometry must be finite")
    return float(center[0]), float(center[1]), float(center[2]) + float(size[2])


def localization_error(predicted: Mapping[str, Any], reference: tuple[float, ...]) -> float:
    return math.dist(tuple(float(predicted[axis]) for axis in ("x", "y", "z")), reference)


def evaluate_model(
    dataset: Path,
    split: Literal["selection", "test"],
    planner: RGBDPlannerAdapter,
    output: Path,
) -> EvaluationReport:
    """Score verified offline inputs without changing timestamps or dispatching actions."""
    from cloud_edge_robot_arm.datasets.rgbd.writer import load_records
    from cloud_edge_robot_arm.vision.offline_reader import (
        load_numeric,
        load_offline_observation,
        resolve_payload,
        verified_payloads,
    )

    if split not in {"selection", "test"}:
        raise ValueError("offline evaluation permits only selection or test")
    audit = SplitManifest.model_validate_json(
        resolve_payload(dataset, "reports/split_audit.json").read_bytes(),
    )
    selected = [
        record
        for record in load_records(dataset)
        if audit.sample_assignments.get(record.sample_id) == split
    ]
    if not selected:
        raise ValueError(f"no independently assigned {split} samples")
    if output.exists():
        raise ValueError("evaluation output already exists")
    output.mkdir(parents=True)
    assignment = [
        {
            "sample_id": record.sample_id,
            "group_id": record.group_id,
            "content_hash": record.content_hash,
        }
        for record in selected
    ]
    write_json(output / "assignments.json", {"split": split, "cases": assignment})
    records, errors, latencies = [], [], []
    recognized = blocked = succeeded = rejected_depth = 0
    for record in selected:
        row: dict[str, Any] = {
            "sample_id": record.sample_id,
            "success": False,
            "scope": "OFFLINE_MODEL_GROUNDING",
            "split": split,
        }
        start = time.monotonic()
        try:
            observation = load_offline_observation(record)
            request = InitialPlanningRequest(
                request_id="offline-grounding",
                user_instruction=record.labels["instruction"],
                observation=observation,
                scene=SceneSummary(scene_version=1, updated_at=observation.captured_at),
            )
            draft = planner.plan(request)
            evidence = draft.observation_evidence or {}
            row.update(parse_error=draft.parse_error, model_evidence=evidence)
            pixel = evidence.get("original_pixel_target")
            payloads = verified_payloads(record)
            instance = load_numeric(
                payloads["instance"], "<i4", (observation.height, observation.width), "instance"
            )
            hit = bool(
                isinstance(pixel, (list, tuple))
                and len(pixel) == 2
                and 0 <= pixel[0] < observation.width
                and 0 <= pixel[1] < observation.height
                and instance[pixel[1], pixel[0]] == record.labels["target_instance_id"]
            )
            row["recognized"] = hit
            destination_pixel = evidence.get("original_pixel_destination")
            destination_hit = bool(
                isinstance(destination_pixel, (list, tuple))
                and len(destination_pixel) == 2
                and 0 <= destination_pixel[0] < observation.width
                and 0 <= destination_pixel[1] < observation.height
                and instance[destination_pixel[1], destination_pixel[0]]
                == record.labels["destination_instance_id"]
            )
            row["destination_recognized"] = destination_hit
            recognized += int(hit)
            point = evidence.get("target_visible_surface")
            if hit and isinstance(point, dict):
                reference = independent_top_center(record.labels)
                error = localization_error(point, reference)
                errors.append(error)
                row.update(
                    localization_error_m=error,
                    independent_reference_m=reference,
                    reference_source="OFFLINE_RIGID_BOX_TOP_CENTER",
                )
            else:
                row["localization_error_m"] = None
            refusal = bool(
                draft.parsed_json
                and draft.parsed_json.get("_sentinel") == "REQUEST_MORE_OBSERVATION"
            )
            depth_rejection = refusal and any(
                word in str(draft.parsed_json).lower() for word in ("depth", "invalid metric")
            )
            rejected_depth += int(depth_rejection)
            row["invalid_depth_rejected"] = depth_rejection
            row["success"] = bool(
                hit
                and destination_hit
                and draft.observed_scene is not None
                and not draft.parse_error
                and not refusal
            )
            succeeded += int(row["success"])
        except RGBDModelUnavailable as exc:
            blocked += 1
            row.update(blocked=True, error=str(exc))
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        elapsed = time.monotonic() - start
        latencies.append(elapsed)
        row["latency_s"] = elapsed
        records.append(row)
        write_json(output / f"{record.sample_id}.json", row)
    latency: dict[str, float | None] = {
        name: float(np.percentile(latencies, quantile))
        for name, quantile in (("p50_s", 50), ("p95_s", 95))
    }
    report = EvaluationReport(
        assigned=len(selected),
        succeeded=succeeded,
        blocked=blocked,
        localization_errors_m=tuple(errors),
        recognition_coverage=recognized / len(selected),
        invalid_depth_rejection_rate=rejected_depth / len(selected),
        latency_summary=latency,
        records=tuple(records),
        split=split,
    )
    write_json(output / "report.json", asdict(report))
    return report


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str
        )
        + "\n",
        encoding="utf-8",
    )
