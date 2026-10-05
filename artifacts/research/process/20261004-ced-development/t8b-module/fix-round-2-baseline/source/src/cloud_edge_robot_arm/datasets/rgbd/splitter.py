"""Deterministic source-connected holdouts with auditable duplicate evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from cloud_edge_robot_arm.datasets.rgbd.models import SampleRecord, SplitManifest, canonical_json
from cloud_edge_robot_arm.datasets.rgbd.quality import duplicate_reason, source_identity

SplitRole = Literal["train", "calibration", "selection", "test"]
ROLES: tuple[SplitRole, ...] = ("train", "calibration", "selection", "test")
ALGORITHM = "source-content-local-rgbd-v1"


def assign_splits(records: Sequence[SampleRecord], seed: int) -> SplitManifest:
    """Keep connected source/episode/content/perceptual groups in one holdout.

    Largest-remainder allocation applies to independent connected groups, not
    frame counts. Hash ordering makes results independent of input iteration.
    """
    if type(seed) is not int or seed < 0:
        raise ValueError("split seed must be a nonnegative integer")
    ordered = sorted(records, key=lambda record: record.sample_id)
    if len({record.sample_id for record in ordered}) != len(ordered):
        raise ValueError("duplicate sample identity")
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    duplicates = []
    for i, current in enumerate(ordered):
        for j in range(i):
            reason = duplicate_reason(current, ordered[j])
            if reason:
                parent[find(i)] = find(j)
                duplicates.append(
                    {
                        "sample_id": current.sample_id,
                        "duplicate_of": ordered[j].sample_id,
                        "reason": reason,
                    }
                )
    components: dict[int, list[SampleRecord]] = {}
    for index, record in enumerate(ordered):
        components.setdefault(find(index), []).append(record)

    def rank(component: list[SampleRecord]) -> str:
        identity = canonical_json(sorted({source_identity(record) for record in component}))
        return hashlib.sha256(f"{seed}:{identity}".encode()).hexdigest()

    groups = sorted(components.values(), key=rank)
    proportions = (80, 5, 5, 10)
    quotas = [len(groups) * percentage // 100 for percentage in proportions]
    # Integer remainders avoid floating-point quota errors (e.g. 100 -> 80/5/5/10).
    remainder_order = sorted(range(4), key=lambda i: (-(len(groups) * proportions[i] % 100), i))
    for index in remainder_order[: len(groups) - sum(quotas)]:
        quotas[index] += 1
    group_assignments: dict[str, SplitRole] = {}
    sample_assignments: dict[str, SplitRole] = {}
    start = 0
    for role, quota in zip(ROLES, quotas, strict=True):
        for component in groups[start : start + quota]:
            for record in component:
                group_assignments[record.group_id] = role
                sample_assignments[record.sample_id] = role
        start += quota
    return SplitManifest(
        seed=seed,
        group_assignments=group_assignments,
        sample_assignments=sample_assignments,
        counts=dict(zip(ROLES, quotas, strict=True)),
        duplicates=duplicates,
        algorithm_version=ALGORITHM,
    )


def write_splits(root: Path, manifest: SplitManifest, records: Sequence[SampleRecord]) -> None:
    """Atomically replace each role file, then publish its audit manifest last.

    A concurrent/incomplete replacement fails validation rather than exposing an
    apparently verified mixture. Generation supports one writer per dataset.
    """
    from cloud_edge_robot_arm.datasets.rgbd.writer import _atomic_write

    manifest = SplitManifest.model_validate(manifest.model_dump(mode="json"))
    expected = assign_splits(records, manifest.seed)
    if manifest != expected:
        raise ValueError("split manifest does not match source-connected assignments")
    root = Path(root).resolve()
    for directory in (root / "splits", root / "reports"):
        if directory.is_symlink():
            raise ValueError("symlink split/report directory is forbidden")
        directory.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        payload = "".join(
            canonical_json(record.model_dump(mode="json")) + "\n"
            for record in sorted(records, key=lambda item: item.sample_id)
            if manifest.sample_assignments[record.sample_id] == role
        )
        _atomic_write(root / "splits" / f"{role}.jsonl", payload.encode())
    _atomic_write(
        root / "reports" / "split_audit.json",
        (canonical_json(manifest.model_dump(mode="json")) + "\n").encode(),
    )
