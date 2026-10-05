"""Immutable protocol data, deterministic scene pools, and verified freeze boundaries."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, canonical_json, content_digest
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene

TASKS = ("STATIC", "SENSOR", "DYNAMIC")
NETWORKS = ((0, 0.0), (100, 0.0), (300, 0.01), (600, 0.05))
STRATA = tuple(f"{task}_RTT{rtt}" for task in TASKS for rtt, _ in NETWORKS)


class OpportunitySeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    opportunity_id: str
    group_id: str
    observation_hash: str
    action_spec: dict[str, Any]
    oracle_label: Literal["VALID", "INVALID", "UNKNOWN"]


class ProtocolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["rgbd.research.v1", "ced.research.v2"] = "rgbd.research.v1"
    strata: tuple[str, ...] = STRATA
    formal_ns: tuple[int, ...] = (600, 1200, 1800, 2400)
    selected_n: int | None = None
    tcap_s: int | None = Field(default=None, ge=120, le=600, multiple_of=10)
    rcap_s: Literal[60] = 60
    hypothesis_family: tuple[str, ...] = (
        "G2_REQUESTS",
        "G2_SUCCESS",
        "G2_SAFETY",
        "G3_FALSE_ACCEPT",
        "G4_DURATION",
    )
    bootstrap_iterations: int = Field(default=10000, ge=10000)
    statistics_seed: int = 20261003
    alpha: float = Field(default=0.05, ge=0.05, le=0.05)
    target_power: float = Field(default=0.8, ge=0.8, le=0.8)
    b0_periods_s: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0)
    success_noninferiority_margin: float = Field(default=0.03, ge=0.03, le=0.03)
    safety_noninferiority_margin: float = Field(default=0.01, ge=0.01, le=0.01)
    minimum_baseline_nominal_success: float = Field(default=0.9, ge=0.9, le=0.9)
    minimum_baseline_overall_success: float = Field(default=0.8, ge=0.8, le=0.8)
    maximum_baseline_safety_violation: float = Field(default=0.01, ge=0.01, le=0.01)
    pool_hashes: dict[str, str] = Field(default_factory=dict)
    model_snapshot_hash: str | None = None
    method_hashes: dict[str, str] = Field(default_factory=dict)
    initial_protocol_hash: str | None = None
    opportunity_hash: str | None = None
    recovery_fault_manifest_hash: str | None = None
    role_bundle_hash: str | None = None
    selection_manifest_hash: str | None = None
    selected_b0_period_s: float | None = None
    budget_selection_rule_hash: str | None = None

    @model_serializer(mode="wrap")
    def preserve_v1_shape(self, handler: Any) -> dict[str, Any]:
        payload = dict(handler(self))
        if self.schema_version == "rgbd.research.v1":
            for name in (
                "role_bundle_hash",
                "selection_manifest_hash",
                "selected_b0_period_s",
                "budget_selection_rule_hash",
            ):
                payload.pop(name, None)
        return payload

    @model_validator(mode="after")
    def fixed_design(self) -> ProtocolSpec:
        if self.strata != STRATA or self.formal_ns != (600, 1200, 1800, 2400):
            raise ValueError("task strata and N candidates are fixed by the approved design")
        if self.selected_n is not None and self.selected_n not in self.formal_ns:
            raise ValueError("N must be an allowed candidate")
        if self.selected_b0_period_s is not None and self.selected_b0_period_s not in (
            0.5,
            1.0,
            2.0,
            5.0,
        ):
            raise ValueError("B0 period must be a fixed candidate")
        v2_fields = (
            self.role_bundle_hash,
            self.selection_manifest_hash,
            self.selected_b0_period_s,
            self.budget_selection_rule_hash,
        )
        if self.schema_version == "rgbd.research.v1" and any(v is not None for v in v2_fields):
            raise ValueError("role/stage bindings require explicit ced.research.v2")
        for digest in (
            self.role_bundle_hash,
            self.selection_manifest_hash,
            self.budget_selection_rule_hash,
        ):
            if digest is not None and (
                len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("v2 stage bindings require full SHA256")
        return self


class FrozenProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    spec: ProtocolSpec
    stage: Literal["INITIAL", "FINAL"]
    content_hash: str

    def require_formal(self) -> None:
        if self.stage != "FINAL":
            raise ValueError("formal runs require a FINAL frozen protocol")
        if not self.spec.selected_n or not self.spec.initial_protocol_hash:
            raise ValueError("formal runs require final N and initial protocol link")


def freeze_protocol(
    spec: ProtocolSpec,
    output: Path,
    stage: Literal["INITIAL", "FINAL"],
    *,
    evidence_directory: Path | None = None,
) -> FrozenProtocol:
    if spec.tcap_s is None:
        raise ValueError("Tcap requires real successful B0 pilot durations")
    if evidence_directory is None:
        raise ValueError("protocol freeze requires actual verified evidence directory")
    if stage == "FINAL":
        # Methods, power and statistical prerequisites are not yet implemented.
        raise ValueError("FINAL evidence verification is not implemented; cannot freeze")
    from cloud_edge_robot_arm.research.freeze_evidence import initial_spec_from_evidence

    derived = initial_spec_from_evidence(evidence_directory)
    for name in (
        "schema_version",
        "tcap_s",
        "pool_hashes",
        "model_snapshot_hash",
        "opportunity_hash",
        "recovery_fault_manifest_hash",
        "role_bundle_hash",
        "selection_manifest_hash",
        "selected_b0_period_s",
        "budget_selection_rule_hash",
    ):
        if getattr(spec, name) != getattr(derived, name):
            raise ValueError(f"protocol {name} differs from verified pilot evidence")
    if stage == "INITIAL" and spec.selected_n is not None:
        raise ValueError("initial freeze cannot choose formal N")
    if stage == "FINAL" and (
        not spec.selected_n or not spec.initial_protocol_hash or not spec.method_hashes
    ):
        raise ValueError("FINAL freeze requires initial link, method hashes and power-selected N")
    payload = {"spec": spec.model_dump(mode="json"), "stage": stage}
    frozen = FrozenProtocol(spec=spec, stage=stage, content_hash=content_digest(payload))
    output.mkdir(parents=True, exist_ok=False)
    temporary = output / "protocol.json.tmp"
    temporary.write_text(canonical_json(frozen.model_dump(mode="json")) + "\n")
    temporary.replace(output / "protocol.json")
    return frozen


def load_protocol(directory: Path) -> FrozenProtocol:
    frozen = FrozenProtocol.model_validate_json((directory / "protocol.json").read_bytes())
    payload = {"spec": frozen.spec.model_dump(mode="json"), "stage": frozen.stage}
    if content_digest(payload) != frozen.content_hash:
        raise ValueError("protocol content hash mismatch")
    if not all(
        (
            frozen.spec.pool_hashes,
            frozen.spec.model_snapshot_hash,
            frozen.spec.opportunity_hash,
            frozen.spec.recovery_fault_manifest_hash,
        )
    ):
        raise ValueError("protocol lacks required evidence bindings")
    if frozen.spec.schema_version == "ced.research.v2" and not all(
        (
            frozen.spec.role_bundle_hash,
            frozen.spec.selection_manifest_hash,
            frozen.spec.selected_b0_period_s,
            frozen.spec.budget_selection_rule_hash,
        )
    ):
        raise ValueError("v2 protocol lacks role/selection/budget evidence bindings")
    return frozen


def build_scene_pools(
    seed: int,
    excluded_groups: set[str],
    *,
    protocol_version: str = "rgbd.research.v1",
) -> dict[str, list[dict[str, Any]]]:
    """Freeze scenes before runs, matching physical group identity across all pools."""
    if protocol_version not in {"rgbd.research.v1", "ced.research.v2"}:
        raise ValueError("unsupported explicit scene pool protocol version")
    sizes: tuple[tuple[str, int], ...] = (
        ("foundation", 120),
        ("power", 120),
        ("formal", 2400),
        ("recovery", 200),
        ("ood", 300),
    )
    if protocol_version == "ced.research.v2":
        sizes = (("selection", 120), *sizes)
    config = DatasetConfig(
        dataset_id="research-pools",
        groups=sum(count for _, count in sizes),
        seed=seed,
        target_x=(0.34, 0.43),
        target_y=(-0.07, 0.08),
        half_size=(0.032, 0.037),
        camera_height=(1.4, 1.4),
        camera_x=(0.35, 0.35),
        camera_y=(0.0, 0.0),
        camera_fovy=(45.0, 45.0),
        distractor_count=(0, 0),
        depth_noise_m=(0.0,),
        invalid_depth_fractions=(0.0,),
    )
    pools: dict[str, list[dict[str, Any]]] = {}
    seen = set(excluded_groups)
    cursor = seed
    for name, count in sizes:
        rows = []
        local = config if name != "ood" else config.model_copy(update={"camera_fovy": (60.0, 65.0)})
        for index in range(count):
            for _attempt in range(
                max(5, len(seen) + 1) if protocol_version == "ced.research.v2" else 5
            ):
                scene = sample_scene(local, cursor)
                cursor += 1
                if scene.group_id not in seen:
                    break
            else:
                raise ValueError("cannot obtain disjoint unique scene groups")
            seen.add(scene.group_id)
            stratum = STRATA[index % 12]
            # Independent permutations within each layer, unrelated to scene seeds
            # and communication condition. Every complete block of three is balanced.
            ordinal = index // 12
            levels = {}
            for parameter, choices in {
                "movement_speed_m_s": (0.0, 0.02, 0.04),
                "noise_m": (0.0, 0.002, 0.005),
                "invalid_fraction": (0.0, 0.1, 0.3),
                "occlusion_fraction": (0.0, 0.2, 0.4),
            }.items():
                order = list(choices)
                random.Random(f"{seed}:{name}:{stratum}:{parameter}").shuffle(order)
                levels[parameter] = order[ordinal % 3]
            rows.append(
                {
                    "assignment_id": f"{name}-{index + 1:04d}",
                    "stratum_id": stratum,
                    "scene": scene.model_dump(mode="json"),
                    "scene_hash": scene.scene_hash,
                    "perturbation": levels,
                    "ood_definition": "unseen camera fovy 60-65 degrees" if name == "ood" else None,
                }
            )
        pools[name] = rows
    return pools


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_excluded_groups(datasets: list[Path]) -> set[str]:
    from cloud_edge_robot_arm.datasets.rgbd.writer import load_records

    groups: set[str] = set()
    for directory in datasets:
        records = load_records(directory)
        if not records:
            raise ValueError(f"missing published dataset records: {directory}")
        groups.update(row.group_id for row in records)
    return groups
