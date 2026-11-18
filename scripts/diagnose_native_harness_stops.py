"""Recompute scoped vision predicates from the frozen November 18 MuJoCo archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import numpy as np

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from cloud_edge_robot_arm.research.sol_molmo_offline_regression import FrozenCase, load_observation
from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
from cloud_edge_robot_arm.vision.molmo_pointing import native_prompt, parse_native_point
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import ground_observation
from cloud_edge_robot_arm.vision.point_association import associate_target_point
from cloud_edge_robot_arm.vision.servo import (
    _requested_optical_transform,
    measure_registered_marker_grasp,
)
from cloud_edge_robot_arm.vision.servo_region import measure_servo_region
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_REL = Path("experiments/results/phase9/real-harness-20261118")
VERIFICATION = "artifacts/research/process/20261118-real-model-harness/native-verification.json"
INPUT_MANIFEST_SHA256 = "6c0305c48fd50ed945662935b0f0e6744f3a219bad3754a66d2a28a5cfdba96e"
FRAME_BINDING_FIELDS = (
    "observation_id", "frame_id", "checksum_sha256", "episode_id", "scene_id", "source",
    "calibration_version", "camera_to_world", "intrinsics", "sim_time_s",
    "rgb_sha256", "depth_sha256", "width", "height",
)
ACCEPTED_SAMPLE_FIELDS = (
    "observation_id", "checksum_sha256", "calibration_version", "camera_to_world", "sim_time_s",
)
CAMERA_CONTEXT_FIELDS = ("episode_id", "scene_id", "source", "width", "height", "intrinsics")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_frame_binding(
    observation: RGBDObservation,
    evidence: dict[str, Any],
    fields: tuple[str, ...] = FRAME_BINDING_FIELDS,
) -> None:
    expected = observation.evidence()
    for field in fields:
        if field not in evidence or expected[field] != evidence[field]:
            raise ValueError("archive frame binding differs at " + field)


def read_bound_frame(case: FrozenCase, folder: str, *, episode_id: str) -> RGBDObservation:
    observation = load_observation(case, folder)
    check_frame_binding(observation, case.json(folder + "/observation.json"))
    if not episode_id or observation.episode_id != episode_id:
        raise ValueError("archive frame episode does not match the indexed episode")
    camera_bytes = struct.pack("<20d", *observation.intrinsics, *observation.camera_to_world)
    if observation.source != "mujoco_camera" or observation.calibration_version != sha256(
        camera_bytes
    )[:16]:
        raise ValueError("archive frame calibration does not match its MuJoCo camera")
    return observation


def check_same_sample(frames: list[RGBDObservation]) -> None:
    if not 1 <= len(frames) <= 3:
        raise ValueError("archive camera sample has an invalid number of captures")
    first = frames[0]
    for index, current in enumerate(frames[1:], start=1):
        if any(getattr(current, field) != getattr(first, field) for field in CAMERA_CONTEXT_FIELDS):
            raise ValueError("archive camera sample changes episode, scene or intrinsics")
        if current.sim_time_s != first.sim_time_s:
            raise ValueError("archive camera sample advances physics time")
        if any(
            current.observation_id == old.observation_id
            or current.calibration_version == old.calibration_version
            or np.allclose(current.camera_to_world, old.camera_to_world, atol=1e-9, rtol=0)
            for old in frames[:index]
        ):
            raise ValueError("archive camera sample repeats a frame or camera pose")
        if current.captured_at < frames[index - 1].captured_at:
            raise ValueError("archive camera sample reverses capture time")


def write_report(path: Path, report: dict[str, Any], *, protected: tuple[Path, ...]) -> None:
    path = path.resolve()
    if any(path.is_relative_to(source.resolve()) for source in protected):
        raise ValueError("report destination is inside a protected source")
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(rendered)


def measure_initial_geometry(
    observation: RGBDObservation, grounding: dict[str, Any],
) -> tuple[OpenCVTargetTracker | None, dict[str, Any]]:
    entities: dict[str, Any] = {}
    try:
        geometry = OpenCVTargetTracker._inspect_frozen_geometry(observation, grounding, entities)
    except ValueError as error:
        geometry = None
        reason = str(error)
    else:
        reason = None
    for name in ("target", "destination"):
        entities.setdefault(name, {"status": "NOT_REACHED", "reason": None})
    return geometry, {
        "status": "ACCEPTED" if geometry is not None else "REJECTED",
        "reason": reason,
        "entities": entities,
        "depth_count_semantics": "categories overlap; rejected_pixels is the union",
    }


def _pinned_archive(
    root: Path, input_manifest: Path,
) -> tuple[FrozenCase, dict[int, dict[str, Any]]]:
    contents = input_manifest.read_bytes()
    if sha256(contents) != INPUT_MANIFEST_SHA256:
        raise ValueError("round input manifest SHA256 differs from the approved plan")
    manifest = json.loads(contents)
    archives = {
        Path(row["path"]).relative_to(ARCHIVE_REL).as_posix(): row
        for row in manifest["files"] if row["root"] == "archive"
    }
    inventory = FrozenCase(root, archives, {})
    for name in archives:
        inventory.read(name)
    verification_file = next(
        row for row in manifest["files"]
        if row["root"] == "candidate" and row["path"] == VERIFICATION
    )
    verification = FrozenCase(ROOT, {VERIFICATION: verification_file}, {}).json(VERIFICATION)
    return inventory, {row["seed"]: row for row in verification["rows"] if row["split"]}


def _case(inventory: FrozenCase, seed: int) -> FrozenCase:
    relative = f"native/varied-{seed}"
    root = inventory.root / relative
    manifest = inventory.json(relative + "/evidence-manifest.json")
    files = {row["path"]: row for row in manifest["files"]}
    if len(files) != len(manifest["files"]):
        raise ValueError("archive episode index repeats a path")
    return FrozenCase(root, files, {})


def _frame_payload(observation: RGBDObservation) -> dict[str, Any]:
    evidence = observation.evidence()
    return {field: evidence[field] for field in FRAME_BINDING_FIELDS} | {
        "captured_at": evidence["captured_at"],
        "valid_mask_sha256": sha256(observation.valid_mask_bytes()),
    }


def _stage(case: FrozenCase, index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    planning = case.json(f"planning/planning-stage-{index:02d}.json")
    if len(planning["attempts"]) != 1:
        raise ValueError("archive planning stage does not bind one attempt")
    return planning, planning["attempts"][0]["draft"]["observation_evidence"]


def _marker_frame(
    observation: RGBDObservation, assignment: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    family_id = assignment["marker_family_id"]
    family = marker_family(family_id)
    if assignment["asset_sha256"] != family.asset_sha256 or assignment["marker"] != {
        "marker_id": family.marker_id,
        "marker_size_m": family.marker_size_m,
        "dictionary": family.dictionary,
        "marked_asset_sha256": family.asset_sha256,
    }:
        raise ValueError("archive marker registration differs from the assigned family")
    details: dict[str, Any] = {}
    try:
        grasp, _ = measure_registered_marker_grasp(observation, family_id, diagnostics=details)
    except ValueError as error:
        return details, str(error)
    if grasp is None:
        return details, "servo registered marker geometry unavailable"
    return details, None


def _view(
    observation: RGBDObservation,
    assignment: dict[str, Any],
    region: OpenCVTargetTracker | None,
) -> dict[str, Any]:
    marker, reason = _marker_frame(observation, assignment)
    details: dict[str, Any] = {"status": "NOT_REACHED"}
    if reason is None and region is not None:
        current, region_reason = measure_servo_region(observation, region, diagnostics=details)
        if current is None:
            details.update(status="REJECTED", reason=region_reason)
            reason = "servo region geometry unavailable: " + str(region_reason)
        else:
            details.update(status="ACCEPTED", support=current)
    return {
        "frame": _frame_payload(observation),
        "marker": marker,
        "region": details,
        "candidate_static_status": "REJECTED" if reason else "ACCEPTED",
        "candidate_first_rejection": reason,
    }


def _action(episode: dict[str, Any], step_id: str, skill: str) -> dict[str, Any]:
    actions = [action for action in episode["actions"] if action["step_id"] == step_id]
    if len(actions) != 1 or actions[0]["skill"] != skill:
        raise ValueError("archive action does not match the diagnostic boundary")
    return actions[0]


def _accepted_sample(action: dict[str, Any], observation: RGBDObservation) -> dict[str, Any]:
    matches = [
        item for item in action["visual_servo"]["visual_samples"]
        if item["observation_id"] == observation.observation_id
    ]
    if len(matches) != 1:
        raise ValueError("archive frame is not uniquely indexed as an accepted servo sample")
    check_frame_binding(observation, matches[0], ACCEPTED_SAMPLE_FIELDS)
    return matches[0]


def _adjacent_frames(previous: RGBDObservation, rejected: RGBDObservation) -> None:
    if any(getattr(previous, field) != getattr(rejected, field) for field in CAMERA_CONTEXT_FIELDS):
        raise ValueError("archive previous and rejected frames are from different camera contexts")
    if (
        previous.observation_id == rejected.observation_id
        or rejected.captured_at < previous.captured_at
        or not 0 < rejected.sim_time_s - previous.sim_time_s <= 0.1
    ):
        raise ValueError("archive previous and rejected frames are not adjacent servo samples")


def _transport(
    case: FrozenCase, result: dict[str, Any], episode: dict[str, Any], assignment: dict[str, Any],
) -> dict[str, Any]:
    episode_id = result["episode_id"]
    reference = read_bound_frame(case, "component/frames/post-cloud", episode_id=episode_id)
    _, grounding = _stage(case, 2)
    check_frame_binding(reference, grounding)
    geometry, initialization = measure_initial_geometry(reference, grounding)
    if geometry is None:
        raise ValueError("archive reference could not reinitialize production geometry")
    action = _action(episode, "step-05", "MOVE_TO_REGION")
    path = "component/servo-frames/step-05/"
    positive = result["seed"] == 44102
    previous = read_bound_frame(
        case, path + ("sample-0001" if positive else "sample-0100"), episode_id=episode_id,
    )
    accepted = _accepted_sample(action, previous)
    row = {
        "reference": _frame_payload(reference),
        "reference_initialization": initialization,
        "accepted_control": _view(previous, assignment, geometry) | {
            "original_region_support": accepted.get("region_support"),
        },
        "original_terminal_reason": action["visual_servo"]["terminal_reason"],
    }
    if positive:
        return row
    rejected = [
        read_bound_frame(case, path + name, episode_id=episode_id)
        for name in ("sample-0101", "sample-0101-view-01", "sample-0101-view-02")
    ]
    check_same_sample(rejected)
    _adjacent_frames(previous, rejected[0])
    adjustments = [
        item for item in episode["camera_adjustments"]
        if item.get("step_id") == action["step_id"]
        and item.get("physics_step") == action["controller_return_step"]
    ]
    if len(adjustments) != len(rejected) - 1:
        raise ValueError("archive does not bind the recorded alternate camera requests")
    for adjustment, frame in zip(adjustments, rejected[1:], strict=True):
        expected = _requested_optical_transform(
            (tuple(adjustment["position_m"]), tuple(adjustment["look_at_m"])),
        )
        if not np.allclose(frame.camera_to_world, expected, atol=1e-9, rtol=0):
            raise ValueError("archived alternate frame did not capture the requested camera pose")
    original_reasons = [item["reason"] for item in adjustments] + [
        row["original_terminal_reason"].removeprefix("ValueError:"),
    ]
    row["rejected_sample"] = {
        "physics_step": action["controller_return_step"],
        "views": [
            _view(frame, assignment, geometry) | {"original_first_rejection": reason}
            for frame, reason in zip(rejected, original_reasons, strict=True)
        ],
        "unknown": "observability from any unrecorded view",
    }
    return row


def _retreat(
    case: FrozenCase, result: dict[str, Any], episode: dict[str, Any], assignment: dict[str, Any],
) -> dict[str, Any]:
    action = _action(episode, "step-08", "RETREAT")
    if action["continuation"] is not True:
        raise ValueError("archive retreat sample does not belong to the lateral continuation")
    path = "component/servo-frames/step-08/"
    positive = result["seed"] == 44102
    episode_id = result["episode_id"]
    previous = read_bound_frame(
        case, path + ("sample-0001" if positive else "sample-0021"), episode_id=episode_id,
    )
    _accepted_sample(action, previous)
    row = {
        "accepted_control": _view(previous, assignment, None),
        "original_terminal_reason": action["visual_servo"]["terminal_reason"],
    }
    if positive:
        return row
    failure = read_bound_frame(case, path + "sample-0022", episode_id=episode_id)
    _adjacent_frames(previous, failure)
    alternate_count = sum(name.startswith(path + "sample-0022-view-") for name in case.files)
    if alternate_count:
        raise ValueError("archive has an unplanned same-sample retreat alternate")
    row["rejected_sample"] = _view(failure, assignment, None) | {
        "physics_step": action["controller_return_step"],
        "same_sample_alternate_frames": 0,
        "unknown": "same-instant alternative marker observability",
    }
    return row


def _model_point(
    case: FrozenCase, index: int, observation: RGBDObservation, binding: dict[str, Any],
) -> tuple[tuple[int, int], dict[str, Any]]:
    directory = f"raw/molmo/request-{index:04d}/"
    started = case.json(directory + "started.json")
    result = case.json(directory + "result.json")
    raw = case.read(directory + "raw-response.txt")
    prompt = case.read(directory + "prompt.txt")
    phrase = started["phrase"]
    raw_sha = sha256(raw)
    query_sha = sha256(phrase.encode())
    rgb_sha = observation.evidence()["rgb_sha256"]
    point = parse_native_point(raw.decode())
    # The archived provider stores the processor-rendered single-image prompt.
    rendered = (
        b"<|image|><|im_start|>user\n"
        + native_prompt(phrase).encode()
        + b"<|im_end|>\n<|im_start|>assistant\n"
    )
    if (
        started["observation_checksum"] != observation.checksum_sha256
        or result["observation_checksum"] != observation.checksum_sha256
        or started["rgb_sha256"] != rgb_sha
        or result["rgb_sha256"] != rgb_sha
        or started["query_sha256"] != query_sha
        or result["query_sha256"] != query_sha
        or binding["query_sha256"] != query_sha
        or result["raw_sha256"] != raw_sha
        or binding["raw_sha256"] != raw_sha
        or prompt != rendered
        or point.status != "POINT"
        or binding["status"] != point.status
        or point.normalized_1000 is None
        or list(point.normalized_1000) != binding["normalized_1000"]
        or result["reached_cap"] is not False
    ):
        raise ValueError("archive model point/raw prompt is not bound to the paired observation")
    pixel = model_to_observation_pixel(
        point.normalized_1000, observation, coordinate_system="normalized_1000",
    )
    return pixel, {
        "normalized_1000": point.normalized_1000,
        "status": point.status,
        "pixel": pixel,
        "phrase": phrase,
        "query_sha256": query_sha,
        "prompt_sha256": sha256(prompt),
        "raw_sha256": raw_sha,
        "rgb_sha256": rgb_sha,
    }


def _initial(
    case: FrozenCase, result: dict[str, Any], assignment: dict[str, Any],
) -> dict[str, Any]:
    observation = read_bound_frame(case, "before", episode_id=result["episode_id"])
    planning, evidence = _stage(case, 1)
    check_frame_binding(observation, evidence)
    target, target_binding = _model_point(case, 1, observation, evidence["native_results"][0])
    destination, destination_binding = _model_point(
        case, 2, observation, evidence["native_results"][1],
    )
    if (
        list(target) != evidence["native_original_pixel_target"]
        or list(destination) != evidence["native_original_pixel_destination"]
    ):
        raise ValueError("archive model point does not match the original planned input pixel")
    request = InitialPlanningRequest(
        request_id=planning["request_id"],
        user_instruction=assignment["instruction"],
        observation=observation,
    )
    target_phrase = target_binding["phrase"].removeprefix("visible top center of ")
    try:
        association = associate_target_point(observation, target, target_phrase=target_phrase)
        measured = ground_observation(
            request, observation, target_pixel=association.pixel, destination_pixel=destination,
            target_label=target_phrase, grasp_profile=assignment["grasp_profile"], evidence={},
        )
    except ValueError as error:
        candidate = {"status": "REJECTED", "reason": str(error), "tracker_stage": "NOT_REACHED"}
    else:
        _, candidate = measure_initial_geometry(observation, measured.evidence)
        candidate["associated_pixel_target"] = association.pixel
        candidate["tracker_stage"] = "EVALUATED"
    return {
        "frame": _frame_payload(observation),
        "original_planning": {"outcome": planning["outcome"], "reason": planning["reason"]},
        "native_model_points": {"target": target_binding, "destination": destination_binding},
        "candidate_static_geometry": candidate,
        "unknown": "physical cause of any missing depth in the selected supports",
    }


def diagnose(archive_root: Path, input_manifest: Path) -> dict[str, Any]:
    inventory, historical_rows = _pinned_archive(archive_root, input_manifest)
    cases = []
    for seed in (44101, 44102, 44103, 44104):
        case = _case(inventory, seed)
        result = case.json("result.json")
        assignment = case.json("scene-assignment.json")
        episode = case.json("component/episode.json")
        historical = historical_rows[seed]
        if (
            result["seed"] != seed or assignment["seed"] != seed
            or episode["episode_id"] != result["episode_id"]
            or result["component_success"] != historical["component_success"]
            or result["physical_success"] != historical["physical"]["success"]
            or result["terminal_reason"] != historical["terminal_reason"]
        ):
            raise ValueError("archive result does not match the historical verification")
        row = {
            "seed": seed,
            "source_group": historical["source_group"],
            "episode_index_sha256": sha256(
                inventory.read(f"native/varied-{seed}/evidence-manifest.json"),
            ),
            "original_outcome": {
                key: result[key] for key in (
                    "worker_status", "terminal_reason", "component_success", "physical_success",
                    "executed_actions", "cloud_requests", "local_generations",
                )
            } | {"placed_stable_s": historical["physical"]["placed_stable_s"]},
        }
        if seed in (44101, 44102):
            row["transport_region"] = _transport(case, result, episode, assignment)
        if seed in (44102, 44103):
            row["lateral_retreat_marker"] = _retreat(case, result, episode, assignment)
        if seed in (44102, 44104):
            row["initial_grounding"] = _initial(case, result, assignment)
        cases.append(row)
    return {
        "scope": "ARCHIVED_MUJOCO_STATIC_VISION_DIAGNOSTICS",
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "verified_pinned_archive_files": len(inventory.files),
        "live_freshness_evaluated": False,
        "actions_dispatched": 0,
        "model_loads": 0,
        "local_generations": 0,
        "cloud_requests": 0,
        "hardware_dispatch": False,
        "formal_research": "NOT_ACCEPTED",
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_report(
        args.output,
        diagnose(args.archive_root, args.input_manifest),
        protected=(args.archive_root, args.input_manifest),
    )


if __name__ == "__main__":
    main()
