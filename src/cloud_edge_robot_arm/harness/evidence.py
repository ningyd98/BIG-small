"""Read the existing per-episode evidence manifest and verify its file bindings."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from cloud_edge_robot_arm.harness.checkout import ENTRY, SourceCheckout
from cloud_edge_robot_arm.harness.config import HarnessConfig, strict_json
from cloud_edge_robot_arm.vision.marker_families import marker_family

MANIFEST = "evidence-manifest.json"
RESULT = "result.json"
ASSIGNMENT = "scene-assignment.json"
SOURCES = "source-hashes.json"
_ERROR_PHASES = frozenset({"FAILED", "INTERRUPTED"})
_PHASES = {
    "dry-run": _ERROR_PHASES | {"PREPARED"},
    "check-marker": _ERROR_PHASES | {"MARKER_CHECKED"},
    "plan-only": _ERROR_PHASES | {"PLANNED", "PLANNING_REJECTED"},
    "execute": _ERROR_PHASES | {"BLOCKED", "SUCCESS", "COMPONENTS_COMPLETED"},
}
_STAGE_FILES = (
    ASSIGNMENT, SOURCES, "role-binding.json", "raw/molmo/load-started.json",
    "raw/cloud/request.json", "raw/cloud/response.json", "planning-response.json",
    "component/episode.json", "costs.json", RESULT, MANIFEST,
)
_EPISODE_FIELDS = (
    "mode",
    "status",
    "execution_scope",
    "success",
    "component_success",
    "physical_success",
    "online_reported_complete",
    "planning_passed",
    "marker_endpoints_observed",
    "model_calls",
    "model_loads",
    "local_generations",
    "cloud_requests",
    "cloud_request_reservations",
    "physics_steps",
    "executed_actions",
    "blocking_reasons",
    "source_snapshot_status",
    "hardware_dispatch",
    "formal_research",
    "qualified_groups_added",
    "worker_status",
    "terminal_reason",
    "error_type",
)


class EvidenceOwnershipError(ValueError):
    """The files could not be attributed to the launched episode."""


@dataclass(frozen=True)
class EpisodeExpectation:
    """Bind archive identity to the switches passed to the original entry."""

    source: SourceCheckout
    config: HarnessConfig
    native: bool

    def check(self, result: dict[str, Any], assignment: object, sources: object) -> None:
        family = marker_family(self.config.marker_family)
        expected = {
            "scenario_id": self.config.scenario_id,
            "marker_family_id": family.family_id,
            "model_path": family.asset_path,
            "asset_sha256": family.asset_sha256,
            "seed": self.config.seed,
            "component_diagnostic": self.native,
            "cloud_vision_fallback": False,
        }
        if (
            not isinstance(assignment, dict)
            or assignment.get("schema_version") != "sol-molmo.single-scene.v1"
            or any(
                type(assignment.get(key)) is not type(value) or assignment[key] != value
                for key, value in expected.items()
            )
            or type(result.get("seed")) is not int
            or result["seed"] != self.config.seed
            or result.get("mode") != ("execute" if self.native else "dry-run")
            or result.get("scene_file") != family.asset_path
        ):
            raise EvidenceOwnershipError("episode assignment does not belong to this launch")
        requested_split = self.config.scene_split if self.native else None
        camera = self.config.camera_position_m if self.native else None
        scene = assignment.get("component_scene")
        actual_split = scene.get("split") if isinstance(scene, dict) else None
        sampling = "FIXED_REGISTERED_SCENE" if requested_split is None else (
            "SEEDED_COMPONENT_POSE_V1"
        )
        if (
            assignment.get("visual_servo", False) is not self.native
            or assignment.get("camera_position_m") != (list(camera) if camera is not None else None)
            or assignment.get("scene_sampling") != sampling
            or actual_split != requested_split
            or (requested_split is None and scene is not None)
        ):
            raise EvidenceOwnershipError("episode runtime switches do not belong to this launch")
        if result["source_snapshot_status"] == "COMPLETE":
            pinned = (
                ENTRY,
                "src/cloud_edge_robot_arm/research/sol_molmo_single_episode.py",
                "src/cloud_edge_robot_arm/vision/marker_families.py",
                family.asset_path,
            )
            if (
                not isinstance(sources, dict)
                or sources.get("scope") != "SELECTED_ENTRY_SOURCES"
                or not isinstance(sources.get("files"), dict)
                or any(
                    key not in self.source.files
                    or sources["files"].get(key) != self.source.files[key] for key in pinned
                )
            ):
                raise EvidenceOwnershipError(
                    "episode source snapshot does not belong to this launch",
                )


@contextmanager
def _artifact(root_fd: int, relative: str) -> Iterator[BinaryIO]:
    parts = relative.split("/")
    if any(part in {"", ".", ".."} or "\\" in part or "\x00" in part for part in parts):
        raise ValueError("unsafe evidence path")
    with ExitStack() as stack:
        directory = root_fd
        for part in parts[:-1]:
            directory = os.open(part, os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            stack.callback(os.close, directory)
        fd = os.open(parts[-1], os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("evidence must contain only regular files")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                yield stream
        finally:
            os.close(fd)


def _json_bytes(stream: BinaryIO) -> bytes:
    limit = 8 * 1024 * 1024
    raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("evidence JSON exceeds 8 MiB")
    return raw


def _manifest_result(stream: BinaryIO, size: int, digest: str) -> object:
    limit = 16 * 1024 * 1024
    actual_size = os.fstat(stream.fileno()).st_size
    if size > limit or actual_size > limit:
        raise ValueError("evidence result.json exceeds 16 MiB")
    if actual_size != size:
        raise ValueError("local evidence differs from manifest size or hash")
    raw = stream.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("local evidence differs from manifest size or hash")
    return strict_json(raw)


def stage_files(output: Path) -> list[str]:
    """Name stage files that survived an incomplete run, without asserting validity."""
    try:
        root_fd = os.open(output, os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return []
    present = []
    try:
        for name in _STAGE_FILES:
            try:
                with _artifact(root_fd, name):
                    present.append(name)
            except (OSError, ValueError):
                continue
    finally:
        os.close(root_fd)
    return present


def _episode_result(result: object) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("schema_version") != (
        "sol-molmo.single-episode-result.v1"
    ):
        raise ValueError("missing or unsupported single-episode result")
    mode, status = result.get("mode"), result.get("status")
    if (
        not isinstance(mode, str) or mode not in _PHASES
        or not isinstance(status, str) or status not in _PHASES[mode]
    ):
        raise ValueError("missing or invalid single-episode phase")
    bools = ("success", "planning_passed", "marker_endpoints_observed", "hardware_dispatch")
    nullable = ("physical_success", "online_reported_complete", "component_success")
    counters = (
        "model_calls", "model_loads", "local_generations", "cloud_requests",
        "cloud_request_reservations", "physics_steps", "executed_actions", "qualified_groups_added",
    )
    reasons = result.get("blocking_reasons")
    if (
        any(type(result.get(key)) is not bool for key in bools)
        or any(key not in result or type(result[key]) not in {bool, type(None)} for key in nullable)
        or any(type(result.get(key)) is not int or result[key] < 0 for key in counters)
        or not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons)
        or result.get("source_snapshot_status") not in ("COMPLETE", "INCOMPLETE")
        or result.get("execution_scope") not in ("NOT_EXECUTED", "MUJOCO_COMPONENT_DIAGNOSTIC")
        or result.get("formal_research") != "NOT_ACCEPTED"
        or result["hardware_dispatch"]
        or result["qualified_groups_added"] != 0
    ):
        raise ValueError("missing or invalid single-episode result fields")
    if status == "PREPARED" and (
        result["source_snapshot_status"] != "COMPLETE"
        or result["execution_scope"] != "NOT_EXECUTED"
        or any(result[key] for key in counters)
        or any(result[key] is not None for key in nullable)
        or result["success"] or result["planning_passed"]
    ):
        raise ValueError("invalid prepared episode state")
    return result


def _prepared_configuration(
    result: dict[str, Any], assignment: object, source: object,
) -> dict[str, object]:
    if (
        not isinstance(assignment, dict)
        or assignment.get("schema_version") != "sol-molmo.single-scene.v1"
        or assignment.get("scene_sampling") != "FIXED_REGISTERED_SCENE"
        or assignment.get("independent_random_scene") is not False
        or not isinstance(assignment.get("scenario_id"), str)
        or not isinstance(assignment.get("marker_family_id"), str)
        or type(assignment.get("seed")) is not int
        or assignment["seed"] != result.get("seed")
        or assignment.get("model_path") != result.get("scene_file")
        or not isinstance(assignment.get("model_path"), str)
        or not isinstance(assignment.get("asset_sha256"), str)
        or assignment.get("component_diagnostic") is not False
        or assignment.get("visual_servo", False) is not False
        or assignment.get("camera_position_m") is not None
    ):
        raise ValueError("prepared episode does not bind the original fixed scene assignment")
    if (
        not isinstance(source, dict)
        or source.get("scope") != "SELECTED_ENTRY_SOURCES"
        or not isinstance(source.get("files"), dict)
        or not source["files"]
        or any(
            not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in source["files"].values()
        )
        or source["files"].get(assignment["model_path"]) != assignment["asset_sha256"]
    ):
        raise ValueError("prepared episode does not bind the original source snapshot")
    return {
        "scenario_id": assignment["scenario_id"],
        "seed": assignment["seed"],
        "marker_family": assignment["marker_family_id"],
        "scene_sampling": assignment["scene_sampling"],
        "scene_split": None,
        "visual_servo": False,
        "camera_position_m": None,
    }


def verify_evidence(
    output: Path, *, expected: EpisodeExpectation | None = None,
) -> dict[str, Any]:
    """Verify the recorded byte counts and SHA256 digests without rewriting evidence."""
    root_fd = os.open(output, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with _artifact(root_fd, MANIFEST) as stream:
            manifest_raw = _json_bytes(stream)
        manifest = strict_json(manifest_raw)
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != "local.files.v1"
            or not isinstance(manifest.get("files"), list)
        ):
            raise ValueError("unsupported local evidence manifest")
        names: set[str] = set()
        phase_json: dict[str, object] = {}
        for row in manifest["files"]:
            if not isinstance(row, dict):
                raise ValueError("invalid local evidence entry")
            path, size, digest = (row.get(key) for key in ("path", "bytes", "sha256"))
            if (
                not isinstance(path, str) or path in names or path == MANIFEST
                or type(size) is not int or size < 0
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            ):
                raise ValueError("invalid or duplicate local evidence entry")
            names.add(path)
            with _artifact(root_fd, path) as stream:
                if path == RESULT:
                    phase_json[path] = _manifest_result(stream, size, digest)
                    continue
                if path in {ASSIGNMENT, SOURCES}:
                    raw = _json_bytes(stream)
                    phase_json[path] = strict_json(raw)
                    actual_size, actual_digest = len(raw), hashlib.sha256(raw).hexdigest()
                else:
                    actual_size = os.fstat(stream.fileno()).st_size
                    actual_digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if size != actual_size or digest != actual_digest:
                raise ValueError("local evidence differs from manifest size or hash")
    finally:
        os.close(root_fd)
    result = _episode_result(phase_json.get(RESULT))
    if expected is not None:
        expected.check(result, phase_json.get(ASSIGNMENT), phase_json.get(SOURCES))
    effective = {}
    if result["status"] == "PREPARED":
        effective = {
            "effective_configuration": _prepared_configuration(
                result, phase_json.get(ASSIGNMENT), phase_json.get(SOURCES),
            ),
        }
    return {
        "status": "VERIFIED",
        "evidence_scope": "LOCAL_EPISODE_FILES",
        "manifest": MANIFEST,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "file_count": len(names),
        "episode": {key: result[key] for key in _EPISODE_FIELDS if key in result},
        **effective,
    }
