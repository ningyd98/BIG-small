"""Exclusive development calibration registration, collection and independent readout.

Preparation never initializes a physics backend. Only the private concrete
application may execute one released assignment; public protocol data is not an
online execution or calibration certificate.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.vision.native_completion import COMPLETION_SKILLS_V2
from cloud_edge_robot_arm.vision.native_completion_horizon import completion_horizon_rational_v1

ROOT = Path(__file__).resolve().parents[3]
CONFIG = "configs/research/native_operational_calibration.yaml"
MARKED_ASSET = "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml"
MARKED_SHA = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"
BASE_ASSET = "assets/robots/franka_panda/scene.xml"
BASE_SHA = "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
ADMISSION_VERSION = "teacher.collection.admission.v1"
ADMISSION_ROWS = (
    "PRE_INITIAL_REACHABLE_DEPTH",
    "POST_LIFT_DEPTH",
    "POST_LIFT_CONTINUITY",
    "POST_LIFT_HELD_INTERFACE",
    "PRE_RELEASE_NOMINAL_DEPTH",
    "TERMINAL_DEPTH",
    "TERMINAL_CONTINUITY",
    "TERMINAL_PLACED_DEPTH",
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def detached(value: Any) -> Any:
    """Preserve public source payloads without deep-copying live/frozen handles."""
    if hasattr(value, "to_payload"):
        return detached(value.to_payload())
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: detached(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): detached(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [detached(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def regular(path: Path) -> Path:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("regular source file without lexical symlinks required")
    return path


def load_json(path: Path) -> Any:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(value: str) -> Any:
        raise ValueError("nonfinite JSON number: " + value)

    return json.loads(regular(path).read_bytes(), object_pairs_hook=pairs, parse_constant=nonfinite)


def save_exclusive(path: Path, value: Any) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("lexical symlink output rejected")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def fresh_directory(path: Path) -> Path:
    path = path.absolute()
    if path.exists() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("fresh exclusive directory without lexical symlinks required")
    path.mkdir(parents=True, exist_ok=False)
    return path


def source_inventory() -> dict[str, str]:
    paths = sorted((ROOT / "src/cloud_edge_robot_arm").rglob("*.py"))
    paths += [
        ROOT / CONFIG,
        ROOT / BASE_ASSET,
        ROOT / MARKED_ASSET,
        ROOT / "scripts/collect_native_calibration.py",
        ROOT / "pyproject.toml",
    ]
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(regular(p).read_bytes()).hexdigest() for p in paths
    }


def check_sources(expected: dict[str, str]) -> None:
    if source_inventory() != expected:
        raise ValueError("registered source generation changed")


def action_horizons() -> list[dict[str, Any]]:
    rows = []
    for skill, duration in zip(
        COMPLETION_SKILLS_V2, (8000, 8000, 1000, 8000, 10000, 8000, 1000, 8000), strict=True
    ):
        original = duration * 1_000_000
        recipe: dict[str, Any] = dict(
            dt_numerator=1,
            dt_denominator=240,
            registered_dt_s=1 / 240,
            original_timeout_ns=original,
            original_expected_ns=original,
            compiled_timeout_ns=original,
            compiled_expected_ns=original,
            effective_owner_required_ns=original,
            builtin_tail_included=False,
            registered_wait_steps=0,
        )
        initial = completion_horizon_rational_v1(skill, **recipe)
        # Freeze the effective owner requirement before issuing the original plan.
        recipe["effective_owner_required_ns"] = initial.total_steps * 10**9 // 240
        recipe["builtin_tail_included"] = skill in {"LIFT", "RELEASE"}
        final = completion_horizon_rational_v1(skill, **recipe)
        if final.total_steps != initial.total_steps:
            raise ValueError("tail counted twice in registered owner duration")
        rows.append(
            dict(
                skill=skill,
                original_timeout_ms=duration,
                recipe=recipe,
                horizon=asdict(final),
                tail_basis=asdict(initial),
            )
        )
    return rows


def _protocol(config: Path) -> dict[str, Any]:
    from cloud_edge_robot_arm.research.native_collection_grounding import (
        geometry_registration,
        release_reference_registration,
    )

    settings = load_json(config)  # The fixed file uses the JSON subset of YAML.
    expected = load_json(ROOT / CONFIG)
    if digest(expected) != "5752ed89e2b05e5265695298f9478813b01cd8ad4e6cde577f52287cfa2e2346":
        raise ValueError("fixed policy bytes changed")
    if canonical(settings) != canonical(expected) or (
        settings["model_path"] != MARKED_ASSET
        or settings["marked_asset_sha256"] != MARKED_SHA
        or settings["grasp_profile_base_asset_sha256"] != BASE_SHA
    ):
        raise ValueError("fixed registered collection policy required")
    geometry = geometry_registration()
    sources = source_inventory()
    horizons = action_horizons()
    physics = settings["settle_steps"] + sum(row["horizon"]["total_steps"] for row in horizons)
    if physics != 12960 or physics > 32768:
        raise ValueError("registered physics budget changed")
    # Every step() consumes >=1 S step, hence its cached RGB/depth refresh count
    # is bounded by total S steps. initialize/reset each add at most one refresh.
    # Explicit per-step and 16 boundary frames each use RGB/depth/instance passes.
    implicit = physics + 2
    explicit = physics + 16
    return dict(
        schema_version="native.calibration.operational.v2",
        settings=settings,
        config_sha256=hashlib.sha256(regular(config).read_bytes()).hexdigest(),
        source_hashes=sources,
        source_generation=digest(sources),
        geometry=geometry,
        release_reference=release_reference_registration(sources, geometry),
        role=dict(
            schema_version="native.teacher.collection.role.v1",
            scope="TEACHER_COLLECTION",
            instruction="Move the red block to the green region.",
            object_id="object",
            target_region_id="target_region",
            provider=None,
            model=None,
            model_requests=0,
        ),
        actions=horizons,
        physical_budget=physics,
        explicit_acquisition_budget=explicit,
        implicit_capture_budget=implicit,
        render_pass_budget=3 * explicit + 2 * implicit,
        sampling=dict(max_gap_sim_s=0.005, per_physics_step=True, noise_schedule="FULL_H_V1"),
        native_qualification="UNKNOWN",
        future_wall_bound=None,
        admission=dict(
            version=ADMISSION_VERSION,
            rows=list(ADMISSION_ROWS),
            online_effect_status="UNKNOWN",
            execution_admitted=False,
            required_unknown_group_score=None,
        ),
        future_wall_bound_status="NOT_REQUIRED_FOR_THIS_RECIPE",
        coverage=0.9,
        assignments=[
            dict(
                assignment_id=f"native-r439-{i:04d}",
                seed=439000 + i,
                ancestors=[f"native-r439-preregistered-{i:04d}"],
                pool="CALIBRATION_ONLY",
                status="RELEASED" if i == 1 else "PREASSIGNED_NOT_RUN",
            )
            for i in range(1, 10)
        ],
    )


def prepare_native_calibration(config: Path, *, output: Path) -> dict[str, Any]:
    protocol = _protocol(config)
    destination = fresh_directory(output)
    save_exclusive(destination / "protocol.json", protocol)
    return dict(
        protocol=str(destination),
        protocol_sha256=digest(protocol),
        physical_budget=protocol["physical_budget"],
        assigned_groups=9,
        released_assignments=["native-r439-0001"],
        native_qualification="UNKNOWN",
    )


def read_protocol(path: Path, *, current_sources: bool = True) -> dict[str, Any]:
    protocol = load_json(path / "protocol.json")
    if (
        not isinstance(protocol, dict)
        or protocol.get("schema_version") != "native.calibration.operational.v2"
    ):
        raise ValueError("registered operational calibration protocol required")
    if canonical(protocol["settings"]) != canonical(load_json(ROOT / CONFIG)) or canonical(
        protocol["actions"]
    ) != canonical(action_horizons()):
        raise ValueError("original collection recipe changed")
    if protocol["source_generation"] != digest(protocol["source_hashes"]):
        raise ValueError("original source generation digest mismatch")
    if current_sources:
        if canonical(protocol) != canonical(_protocol(ROOT / CONFIG)):
            raise ValueError("fixed startup registration or source generation changed")
    return protocol


def collect_native_calibration_once(
    protocol: Path, *, assignment_id: str, output: Path
) -> dict[str, Any]:
    from cloud_edge_robot_arm.research.native_collection_application import (
        NativeCollectionApplication,
    )

    return NativeCollectionApplication.from_startup(
        protocol, assignment_id=assignment_id, output=output
    ).execute_once()


def verify_native_calibration_collection(protocol: Path, *, output: Path) -> dict[str, Any]:
    from cloud_edge_robot_arm.research.native_full_horizon_originals import (
        reconstruct_native_full_horizon_registry,
    )

    data = read_protocol(protocol, current_sources=False)
    roots = {}
    for row in data["assignments"]:
        claim = protocol / "claims" / (row["assignment_id"] + ".json")
        if claim.exists():
            roots[row["assignment_id"]] = Path(load_json(claim)["output"])
    groups: list[dict[str, Any]] = []
    diagnostics = reconstruct_native_full_horizon_registry(
        protocol, roots=roots, group_sink=groups.append
    )
    destination = fresh_directory(output)
    save_exclusive(destination / "diagnostics.json", asdict(diagnostics))
    save_exclusive(destination / "groups.json", groups)
    return dict(
        output=str(destination),
        assigned_groups=diagnostics.assigned_group_count,
        joint_bound_m=diagnostics.joint_bound_m,
        native_qualification="UNKNOWN",
    )
