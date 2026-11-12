"""Exclusive development calibration registration, collection and independent readout.

Preparation never initializes a physics backend. Only the private concrete
application may execute one released assignment; public protocol data is not an
online execution or calibration certificate.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cloud_edge_robot_arm.vision.marker_families import (
    LEGACY_FAMILY,
    PREPARE_ONLY_FAMILY,
    SIDE_PREPARE_ONLY_FAMILY,
    marker_family,
)
from cloud_edge_robot_arm.vision.native_completion import COMPLETION_SKILLS_V2
from cloud_edge_robot_arm.vision.native_completion_horizon import completion_horizon_rational_v1

ROOT = Path(__file__).resolve().parents[3]
CONFIG = "configs/research/native_operational_calibration.yaml"
MARKED_ASSET = "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml"
MARKED_SHA = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"
BASE_ASSET = "assets/robots/franka_panda/scene.xml"
BASE_SHA = "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
_PREPARE_CONFIG = "configs/research/native_operational_calibration_75mm_r579.yaml"
_PREPARE_CONFIG_DIGEST = "5e00a5bb52b465a9b49931357ae630cef8cc56766bd115b8db0bba42c3cf213b"
_PREPARE_CONFIG_SHA = "621624088a9d3e3df7fe9de522b960abd8ea9c1c45193067b6978665fd88b6f3"


@dataclass(frozen=True)
class _PreparePolicy:
    config: str
    config_sha256: str
    settings_digest: str
    schema: str
    lineage: int


_PREPARE_POLICIES = MappingProxyType(
    {
        PREPARE_ONLY_FAMILY: _PreparePolicy(
            _PREPARE_CONFIG,
            _PREPARE_CONFIG_SHA,
            _PREPARE_CONFIG_DIGEST,
            "native.calibration.operational.v3",
            579,
        ),
        SIDE_PREPARE_ONLY_FAMILY: _PreparePolicy(
            "configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml",
            "fa876ce35780fbf98f50aa493199b8e9020b347cd57575fe71ca3a06c117f4c7",
            "325a19e65c06cd3e0db405f5e0c9414530f7b4d02b21518dd62e4cbe91c10192",
            "native.calibration.operational.v4",
            593,
        ),
    }
)
_SINGLE_TEACHER_POLICY = _PreparePolicy(
    "configs/research/native_operational_calibration_side_y_plus_single_teacher_r595.yaml",
    "da7426ab451bf59e76c682d605e5b211c79395b73fbe127990c1e0a1e2cf53cd",
    "3b1ff7748003c90dc922e2b21ba555269933887ac7bfb46ce03ceaa6cd455bac",
    "native.calibration.operational.v5",
    595,
)
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


def _collection_policy(
    family_id: str | None, protocol_schema: str | None = None
) -> _PreparePolicy | None:
    if (family_id is not None and type(family_id) is not str) or (
        protocol_schema is not None and type(protocol_schema) is not str
    ):
        raise ValueError("registered schema/family pair required")
    if family_id in (None, LEGACY_FAMILY) and protocol_schema in (
        None,
        "native.calibration.operational.v2",
    ):
        return None
    if family_id in _PREPARE_POLICIES:
        policy = _PREPARE_POLICIES[family_id]
        if protocol_schema in (None, policy.schema):
            return policy
    if family_id == SIDE_PREPARE_ONLY_FAMILY and protocol_schema == _SINGLE_TEACHER_POLICY.schema:
        return _SINGLE_TEACHER_POLICY
    raise ValueError("registered schema/family pair required")


def source_inventory(
    *, marker_family_id: str | None = None, protocol_schema: str | None = None
) -> dict[str, str]:
    family = marker_family(LEGACY_FAMILY if marker_family_id is None else marker_family_id)
    policy = _collection_policy(marker_family_id, protocol_schema)
    paths = sorted((ROOT / "src/cloud_edge_robot_arm").rglob("*.py"))
    paths += [
        ROOT / (policy.config if policy is not None else CONFIG),
        ROOT / BASE_ASSET,
        ROOT / family.asset_path,
        ROOT / "scripts/collect_native_calibration.py",
        ROOT / "pyproject.toml",
    ]
    if policy is not None:
        paths.append(ROOT / MARKED_ASSET)
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(regular(p).read_bytes()).hexdigest() for p in paths
    }


def check_sources(
    expected: dict[str, str],
    *,
    marker_family_id: str | None = None,
    protocol_schema: str | None = None,
) -> None:
    if (
        source_inventory(marker_family_id=marker_family_id, protocol_schema=protocol_schema)
        != expected
    ):
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


def _registered_settings(
    family_id: str | None, protocol_schema: str | None = None
) -> dict[str, Any]:
    policy = _collection_policy(family_id, protocol_schema)
    path = ROOT / (policy.config if policy is not None else CONFIG)
    expected = load_json(path)
    expected_digest = (
        policy.settings_digest
        if policy is not None
        else ("5752ed89e2b05e5265695298f9478813b01cd8ad4e6cde577f52287cfa2e2346")
    )
    if digest(expected) != expected_digest or (
        policy is not None
        and hashlib.sha256(regular(path).read_bytes()).hexdigest() != policy.config_sha256
    ):
        raise ValueError("fixed policy bytes changed")
    return expected


def _protocol(config: Path, *, historical_sources: dict[str, str] | None = None) -> dict[str, Any]:
    from cloud_edge_robot_arm.research.native_collection_grounding import (
        geometry_registration,
        release_reference_registration,
    )

    settings = load_json(config)  # The fixed file uses the JSON subset of YAML.
    if not isinstance(settings, dict):
        raise ValueError("fixed registered collection policy required")
    family_id = settings.get("marker_family")
    policy = _collection_policy(family_id, settings.get("schema_version"))
    config_sha = hashlib.sha256(regular(config).read_bytes()).hexdigest()
    if policy is not None and config_sha != policy.config_sha256:
        raise ValueError("fixed registered new-family config bytes required")
    family = marker_family(family_id or LEGACY_FAMILY)
    expected = _registered_settings(family_id, settings.get("schema_version"))
    if canonical(settings) != canonical(expected) or (
        settings["model_path"] != family.asset_path
        or settings["marked_asset_sha256"] != family.asset_sha256
        or settings["grasp_profile_base_asset_sha256"] != BASE_SHA
    ):
        raise ValueError("fixed registered collection policy required")
    geometry = geometry_registration(marker_family_id=family_id)
    sources = source_inventory(
        marker_family_id=family_id, protocol_schema=settings["schema_version"]
    )
    if historical_sources is not None:
        if (
            not isinstance(historical_sources, dict)
            or historical_sources.keys() != sources.keys()
            or any(
                type(v) is not str or re.fullmatch(r"[0-9a-f]{64}", v) is None
                for v in historical_sources.values()
            )
            or any(
                historical_sources[p] != value
                for p, value in sources.items()
                if not p.startswith("src/")
            )
        ):
            raise ValueError("registered family source inventory incomplete or mismatched")
        sources = historical_sources
    horizons = action_horizons()
    physics = settings["settle_steps"] + sum(row["horizon"]["total_steps"] for row in horizons)
    if physics != 12960 or physics > 32768:
        raise ValueError("registered physics budget changed")
    # Every step() consumes >=1 S step, hence its cached RGB/depth refresh count
    # is bounded by total S steps. initialize/reset each add at most one refresh.
    # Explicit per-step and 16 boundary frames each use RGB/depth/instance passes.
    implicit = physics + 2
    explicit = physics + 16
    protocol = dict(
        schema_version=settings["schema_version"],
        settings=settings,
        config_sha256=config_sha,
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
                assignment_id=f"native-r{policy.lineage if policy is not None else 439}-{i:04d}",
                seed=settings["first_seed"] + i - 1,
                ancestors=[
                    f"native-r{policy.lineage if policy is not None else 439}-preregistered-{i:04d}"
                ],
                pool="CALIBRATION_ONLY",
                status="RELEASED"
                if i == 1 and (family_id is None or policy is _SINGLE_TEACHER_POLICY)
                else "PREASSIGNED_NOT_RUN",
            )
            for i in range(1, 10)
        ],
    )
    if family_id is not None:
        protocol.update(
            marker_family=family_id,
            execution_release="PREPARE_ONLY_NOT_RELEASED",
            budget_basis="RECIPE_ESTIMATES_ONLY",
            authorized_actual_budget=dict(
                model_loads=0,
                generations=0,
                paid=0,
                teacher_acquisitions=0,
                mujoco_compile=0,
                mj_forward=0,
                render=0,
                physics_steps=0,
                controller=0,
                hardware=0,
            ),
        )
    if policy is _SINGLE_TEACHER_POLICY:
        protocol.update(
            execution_release="SINGLE_TEACHER_ASSIGNMENT_RELEASED",
            budget_basis="SINGLE_TEACHER_ATTEMPT_CEILINGS",
            authorized_actual_budget=dict(
                model_loads=0,
                generations=0,
                paid=0,
                teacher_acquisitions=1,
                mujoco_compile=1,
                mj_forward=4501,
                render=64852,
                physics_steps=12960,
                controller=8,
                hardware=0,
                MjData=19,
                mj_jacSite=4500,
            ),
            authorized_actual_roles={
                "MjData": {"ENGINE": 1, "IK_SCRATCH": 18},
                "mj_forward": {"RESET": 1, "IK_SCRATCH": 4500},
                "mj_jacSite": {"IK_SCRATCH": 4500},
            },
        )
    return protocol


def prepare_native_calibration(config: Path, *, output: Path) -> dict[str, Any]:
    protocol = _protocol(config)
    destination = fresh_directory(output)
    save_exclusive(destination / "protocol.json", protocol)
    return dict(
        protocol=str(destination),
        protocol_sha256=digest(protocol),
        physical_budget=protocol["physical_budget"],
        assigned_groups=9,
        released_assignments=[
            row["assignment_id"] for row in protocol["assignments"] if row["status"] == "RELEASED"
        ],
        native_qualification="UNKNOWN",
    )


def _has_prepare_family_identity(protocol: Mapping[str, Any]) -> bool:
    """Recognize reserved identity fields without rewriting historical legacy data."""
    reserved = {
        "marker_family",
        "execution_release",
        "budget_basis",
        "authorized_actual_budget",
        "authorized_actual_roles",
    }
    if reserved.intersection(protocol):
        return True

    def mapping(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    geometry = mapping(protocol.get("geometry"))
    pose = mapping(geometry.get("pose_marker"))
    settings = mapping(protocol.get("settings"))
    settings_pose = mapping(settings.get("pose_marker"))
    release = mapping(protocol.get("release_reference"))
    assignments = protocol.get("assignments")
    if isinstance(assignments, list):
        for row in assignments:
            row = mapping(row)
            ancestors = row.get("ancestors")
            if (
                row.get("assignment_id") in tuple(f"native-r595-{i:04d}" for i in range(1, 10))
                or row.get("seed") in range(595001, 595010)
                or (
                    isinstance(ancestors, list)
                    and any(
                        value in tuple(f"native-r595-preregistered-{i:04d}" for i in range(1, 10))
                        for value in ancestors
                    )
                )
            ):
                return True
    if geometry.get("marker_to_object") == list(
        marker_family(SIDE_PREPARE_ONLY_FAMILY).marker_to_object
    ):
        return True
    for family_id, policy in (
        *_PREPARE_POLICIES.items(),
        (SIDE_PREPARE_ONLY_FAMILY, _SINGLE_TEACHER_POLICY),
    ):
        family = marker_family(family_id)

        def sources(value: Any, *, family=family, policy=policy) -> bool:
            inventory = mapping(value)
            return bool({family.asset_path, policy.config}.intersection(inventory)) or any(
                item in (family.asset_sha256, policy.config_sha256) for item in inventory.values()
            )

        if (
            "marker_family" in geometry
            or geometry.get("asset_path") == family.asset_path
            or geometry.get("registration_id") == family.registration_id
            or pose.get("marked_asset_sha256") == family.asset_sha256
            or pose.get("marker_size_m") == family.marker_size_m
            or "marker_family" in settings
            or settings.get("model_path") == family.asset_path
            or settings.get("marked_asset_sha256") == family.asset_sha256
            or settings.get("marker_size_m") == family.marker_size_m
            or settings_pose.get("marker_size_m") == family.marker_size_m
            or protocol.get("config_sha256") == policy.config_sha256
            or sources(protocol.get("source_hashes"))
            or "marker_family" in release
            or release.get("marked_asset_sha256") == family.asset_sha256
            or sources(release.get("source_hashes"))
        ):
            return True
    return False


def read_protocol(path: Path, *, current_sources: bool = True) -> dict[str, Any]:
    protocol = load_json(path / "protocol.json")
    if (
        isinstance(protocol, dict)
        and protocol.get("schema_version") == "native.calibration.operational.v8"
    ):
        expected = _registered_collection_protocol_v2(
            None if current_sources else protocol.get("source_hashes")
        )
        if canonical(protocol) != canonical(expected):
            raise ValueError("registered occlusion recipe/source/zero-release identity changed")
        return protocol
    if (
        isinstance(protocol, dict)
        and protocol.get("schema_version") == REGISTERED_COLLECTION_SCHEMA
    ):
        sources = protocol.get("source_hashes")
        expected = _registered_collection_protocol(None if current_sources else sources)
        if canonical(protocol) != canonical(expected):
            raise ValueError("registered collection recipe/source/zero-release identity changed")
        return protocol
    if (
        isinstance(protocol, dict)
        and protocol.get("schema_version") == REGISTERED_PREPARATION_SCHEMA
    ):
        sources = protocol.get("source_hashes")
        expected = _registered_grounding_protocol(None if current_sources else sources)
        if canonical(protocol) != canonical(expected):
            raise ValueError("registered preparation recipe/source/zero-release identity changed")
        return protocol
    if not isinstance(protocol, dict) or protocol.get("schema_version") not in {
        "native.calibration.operational.v2",
        "native.calibration.operational.v3",
        "native.calibration.operational.v4",
        "native.calibration.operational.v5",
    }:
        raise ValueError("registered operational calibration protocol required")
    if protocol["schema_version"] != "native.calibration.operational.v2":
        family_id = protocol.get("marker_family")
        policy = _collection_policy(family_id, protocol["schema_version"])
        if policy is None:
            raise ValueError("registered schema/family pair required")
        sources = protocol.get("source_hashes")
        if not isinstance(sources, dict) or protocol.get("source_generation") != digest(sources):
            raise ValueError("original source generation digest mismatch")
        expected = _protocol(
            ROOT / policy.config,
            historical_sources=None if current_sources else sources,
        )
        if canonical(protocol) != canonical(expected):
            raise ValueError("fixed prepare-only registration/recipe or source generation changed")
        return protocol
    if _has_prepare_family_identity(protocol):
        raise ValueError("prepare-only family cannot downgrade to legacy protocol")
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


REGISTERED_PREPARATION_SCHEMA = "native.calibration.operational.v6"
REGISTERED_COLLECTION_SCHEMA = "native.calibration.operational.v7"


def _registered_collection_protocol(historical_sources=None):
    base = _protocol(
        ROOT / _PREPARE_POLICIES[SIDE_PREPARE_ONLY_FAMILY].config,
        historical_sources=historical_sources,
    )
    base.update(
        schema_version=REGISTERED_COLLECTION_SCHEMA,
        scope="REGISTERED_MODEL_COLLECTION_INTERFACES",
        settings={
            **base["settings"],
            "schema_version": REGISTERED_COLLECTION_SCHEMA,
            "assigned_groups": 0,
            "first_seed": None,
            "released_assignment": None,
            "admission_version": "teacher.registered.collection.admission.v1",
        },
        collection_policy_id="registered-model-collection-v1",
        geometry_basis="REGISTERED_RIGID_MODEL",
        support_basis="REGISTERED_NOMINAL",
        input_schema="registered.grounding.inputs.v1",
        binding_schema="registered.collection.binding.v1",
        action_span_schema="native.registered.action-span.v1",
        record_schema="native.registered.full-horizon.originals.v1",
        condition_version="registered-model-condition-v1",
        assignments=[],
        released_assignments=[],
        execution_release="PREPARE_ONLY_NOT_RELEASED",
        execution_allowed=False,
        prepare_only=True,
        admission={
            **base["admission"],
            "version": "teacher.registered.collection.admission.v1",
            "registered_pose_is_supplemental": True,
            "original_conditions_retained": True,
        },
    )
    return base


def _registered_collection_protocol_v2(historical_sources=None):
    """版本分离的遮挡实验接口；实际任务和额度保持零释放。"""
    from cloud_edge_robot_arm.research.native_collection_grounding import (
        registered_nominal_region_policy_v1,
    )

    base = _registered_collection_protocol(historical_sources)
    base.update(
        schema_version="native.calibration.operational.v8",
        collection_policy_id="registered-model-collection-v2",
        input_schema="registered.grounding.inputs.v2",
        binding_schema="registered.collection.binding.v2",
        action_span_schema="native.registered.action-span.v2",
        record_schema="native.registered.full-horizon.originals.v2",
        condition_version="registered-model-condition-v2",
        region_policy=registered_nominal_region_policy_v1(base["source_hashes"]),
    )
    base["settings"].update(
        schema_version=base["schema_version"],
        admission_version="teacher.registered.collection.admission.v2",
    )
    base["admission"].update(
        version="teacher.registered.collection.admission.v2",
        registered_pose_is_supplemental=False,
        explicit_assertions_require_pass=True,
        nominal_region_is_clearance=False,
    )
    return base


def prepare_registered_collection_protocol_v2(*, output: Path) -> dict[str, Any]:
    """保存未释放的 v8 遮挡接口配方，不创建运行任务。"""
    protocol = _registered_collection_protocol_v2()
    destination = fresh_directory(output)
    save_exclusive(destination / "protocol.json", protocol)
    return dict(
        status="REGISTERED_OCCLUSION_INTERFACES_PREPARED",
        protocol=str(destination),
        protocol_sha256=digest(protocol),
        execution_admitted=False,
        formal="NOT_ACCEPTED",
    )


def prepare_registered_collection_protocol(*, output: Path) -> dict[str, Any]:
    """生成原采集路径的独立注册模型协议；不释放实际任务或额度。"""
    protocol = _registered_collection_protocol()
    destination = fresh_directory(output)
    save_exclusive(destination / "protocol.json", protocol)
    return dict(
        status="REGISTERED_COLLECTION_INTERFACES_PREPARED",
        protocol=str(destination),
        protocol_sha256=digest(protocol),
        execution_admitted=False,
        formal="NOT_ACCEPTED",
    )


def _registered_grounding_protocol(historical_sources=None):
    from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration

    current = source_inventory(
        marker_family_id=SIDE_PREPARE_ONLY_FAMILY,
        protocol_schema="native.calibration.operational.v4",
    )
    sources = current if historical_sources is None else historical_sources
    if (
        type(sources) is not dict
        or set(sources) != set(current)
        or any(
            type(v) is not str or re.fullmatch(r"[a-f0-9]{64}", v) is None for v in sources.values()
        )
    ):
        raise ValueError("complete registered preparation source key set and SHA256 required")
    return dict(
        schema_version=REGISTERED_PREPARATION_SCHEMA,
        scope="REGISTERED_GROUNDING_PREPARATION",
        marker_family=SIDE_PREPARE_ONLY_FAMILY,
        geometry=geometry_registration(marker_family_id=SIDE_PREPARE_ONLY_FAMILY),
        geometry_basis="REGISTERED_RIGID_MODEL",
        support_basis="REGISTERED_NOMINAL",
        policy_id="registered-model-grounding-prepare-v1",
        condition_version="registered-model-condition-v1",
        admission_schema="registered.grounding.preparation-admission.v1",
        input_schema="registered.grounding.inputs.v1",
        binding_schema="registered.grounding.prepared-step.v1",
        actions=action_horizons(),
        source_hashes=sources,
        source_generation=digest(sources),
        authorized_actual_budget={
            name: 0
            for name in (
                "engine",
                "render",
                "physics_steps",
                "actions",
                "teacher",
                "model",
                "paid",
                "hardware",
            )
        },
        assignments=[],
        released_assignments=[],
        execution_release="PREPARE_ONLY_NOT_RELEASED",
        prepare_only=True,
        execution_allowed=False,
        native_qualification="UNKNOWN",
    )


def prepare_registered_grounding_protocol(*, output: Path) -> dict[str, Any]:
    """生成独立v6准备协议；不分配种子、领取任务或初始化物理后端。"""
    protocol = _registered_grounding_protocol()
    destination = fresh_directory(output)
    save_exclusive(destination / "protocol.json", protocol)
    return dict(
        status="REGISTERED_PROTOCOL_PREPARED",
        protocol=str(destination),
        protocol_sha256=digest(protocol),
        execution_admitted=False,
        formal="NOT_ACCEPTED",
    )


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
    if data["schema_version"] == REGISTERED_COLLECTION_SCHEMA:
        raise ValueError("registered collection has no released full-horizon groups")
    if data["schema_version"] == REGISTERED_PREPARATION_SCHEMA:
        raise ValueError(
            "v6 preparation requires its current-frame reader; no full-horizon release"
        )
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
