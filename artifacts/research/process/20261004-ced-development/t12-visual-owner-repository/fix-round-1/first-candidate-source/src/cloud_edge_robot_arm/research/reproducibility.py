"""Verify a local evidence bundle and reuse the analysis entry without shell replay.

File integrity and assignment coverage do not establish physical or research
acceptance. Numeric analysis and physical reruns are recorded separately.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value)


def _relative(name: str) -> Path:
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ValueError("bundle path must be a relative path without traversal")
    return path


def _resolve(root: Path, name: str) -> Path:
    relative = _relative(name)
    path = root / relative
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("bundle source cannot be a symlink")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("bundle path escapes its root")
    return path


@dataclass(frozen=True)
class ReproductionManifest:
    source_tree_hash: str
    dependency_versions: Mapping[str, str]
    asset_hashes: Mapping[str, str]
    model_snapshot_hash: str
    protocol_hash: str
    dataset_hashes: Mapping[str, str]
    seeds: Sequence[int]
    command_arguments: Sequence[Sequence[str]]
    artifact_hashes: Mapping[str, str]
    source_hashes: Mapping[str, str] = field(default_factory=dict, kw_only=True)
    assignment_index_path: str = field(default="", kw_only=True)
    runs_path: str = field(default="", kw_only=True)
    protocol_path: str = field(default="", kw_only=True)
    analysis_path: str = field(default="", kw_only=True)
    scope: str = field(default="RESEARCH", kw_only=True)

    def __post_init__(self) -> None:
        if not _sha(self.source_tree_hash):
            raise ValueError("source tree hash must be SHA256")
        if self.scope not in {"SOFTWARE_ONLY", "RESEARCH"}:
            raise ValueError("unsupported reproduction scope")
        for name in ("model_snapshot_hash", "protocol_hash"):
            value = getattr(self, name)
            if value and not _sha(value):
                raise ValueError(f"invalid {name}")
        for name in ("asset_hashes", "dataset_hashes", "artifact_hashes", "source_hashes"):
            values = dict(getattr(self, name))
            for path, digest in values.items():
                _relative(path)
                if not _sha(digest):
                    raise ValueError("file hash must be SHA256")
            object.__setattr__(self, name, MappingProxyType(values))
        if not self.source_hashes or not self.artifact_hashes:
            raise ValueError("source and artifact inventories are required")
        dependencies = dict(self.dependency_versions)
        if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v
               for k, v in dependencies.items()):
            raise ValueError("dependency versions must be nonempty strings")
        object.__setattr__(self, "dependency_versions", MappingProxyType(dependencies))
        if any(type(seed) is not int or seed < 0 for seed in self.seeds):
            raise ValueError("seeds must be nonnegative integers")
        object.__setattr__(self, "seeds", tuple(self.seeds))
        if any(isinstance(command, str) or not command or any(
            not isinstance(arg, str) for arg in command) for command in self.command_arguments):
            raise ValueError("command arguments must be structured argument lists")
        object.__setattr__(self, "command_arguments", tuple(
            tuple(command) for command in self.command_arguments))
        for name in ("assignment_index_path", "runs_path", "protocol_path", "analysis_path"):
            if value := getattr(self, name):
                _relative(value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_tree_hash": self.source_tree_hash,
            "dependency_versions": dict(self.dependency_versions),
            "asset_hashes": dict(self.asset_hashes),
            "model_snapshot_hash": self.model_snapshot_hash,
            "protocol_hash": self.protocol_hash,
            "dataset_hashes": dict(self.dataset_hashes),
            "seeds": list(self.seeds),
            "command_arguments": [list(command) for command in self.command_arguments],
            "artifact_hashes": dict(self.artifact_hashes),
            "source_hashes": dict(self.source_hashes),
            "assignment_index_path": self.assignment_index_path,
            "runs_path": self.runs_path, "protocol_path": self.protocol_path,
            "analysis_path": self.analysis_path, "scope": self.scope,
        }


def write_reproduction_manifest(manifest: ReproductionManifest, root: Path) -> None:
    """Publish a new manifest without replacing any previous bundle metadata."""
    root.mkdir(parents=True, exist_ok=True)
    payload = manifest.to_payload()
    target = root / "reproduction-manifest.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump({"schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
                   "content_hash": _digest(payload)}, stream, indent=2, allow_nan=False)
        stream.write("\n")


def _load(root: Path) -> ReproductionManifest:
    payload = json.loads(_resolve(root, "reproduction-manifest.json").read_text())
    if not isinstance(payload, dict) or (
        payload.get("schema_version") != "ced.reproduction-manifest.v1"
    ):
        raise ValueError("unsupported reproduction manifest schema")
    if _digest(payload["manifest"]) != payload.get("content_hash"):
        raise ValueError("reproduction manifest content hash mismatch")
    return ReproductionManifest(**payload["manifest"])


def _archived_assignment_ids(root: Path, hashes: Mapping[str, str]) -> set[str]:
    """Find original episode identities in the declared archive, including failures.

    Unrelated JSON may contain raw malformed model responses and is byte evidence,
    so only structured episode records with an assignment identity join coverage.
    """
    identities: set[str] = set()
    for name in hashes:
        path = _resolve(root, name)
        if path.suffix not in {".json", ".jsonl"} or not path.is_file():
            continue
        try:
            rows = [json.loads(line) for line in path.read_text().splitlines()] if (
                path.suffix == ".jsonl"
            ) else [json.loads(path.read_text())]
        except (ValueError, UnicodeError):
            continue
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("assignment"), dict):
                continue
            identity = row["assignment"].get("assignment_id")
            if isinstance(identity, str) and identity:
                identities.add(identity)
    return identities


def verify_reproduction_bundle(root: Path) -> Mapping[str, object]:
    """Read all declared bytes; integrity is separate from experiment acceptance."""
    errors: list[str] = []
    assigned = recorded = 0
    scope = "UNKNOWN"
    try:
        manifest = _load(root)
        scope = manifest.scope
        if _digest(dict(manifest.source_hashes)) != manifest.source_tree_hash:
            errors.append("source tree aggregate hash mismatch")
        inventory: dict[str, str] = {}
        for hashes in (manifest.artifact_hashes, manifest.source_hashes,
                       manifest.asset_hashes, manifest.dataset_hashes):
            for name, digest in hashes.items():
                if name in inventory and inventory[name] != digest:
                    raise ValueError("conflicting file hashes")
                inventory[name] = digest
        for name, digest in inventory.items():
            path = _resolve(root, name)
            if not path.is_file():
                errors.append(f"missing source file: {name}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                errors.append(f"file hash mismatch: {name}")
        if manifest.protocol_path:
            protocol_file = _resolve(root, manifest.protocol_path) / "protocol.json"
            if protocol_file.relative_to(root).as_posix() not in manifest.artifact_hashes:
                raise ValueError("bound protocol absent from artifact inventory")
            from cloud_edge_robot_arm.research.protocol import load_protocol

            frozen = load_protocol(_resolve(root, manifest.protocol_path))
            if manifest.protocol_hash != frozen.content_hash:
                raise ValueError("reproduction protocol hash differs from its bound protocol")
            if manifest.model_snapshot_hash != frozen.spec.model_snapshot_hash:
                raise ValueError("reproduction model hash differs from its bound protocol")
        if manifest.assignment_index_path:
            if manifest.assignment_index_path not in manifest.artifact_hashes:
                raise ValueError("assignment index must be in the artifact inventory")
            index = json.loads(_resolve(root, manifest.assignment_index_path).read_text())
            if not isinstance(index, dict) or (
                index.get("schema_version") != "ced.reproduction-index.v1"
            ):
                raise ValueError("unsupported assignment index schema")
            assignments, records = index["assignments"], index["records"]
            if (not isinstance(assignments, list) or not isinstance(records, dict)
                    or any(not isinstance(value, str) or not value for value in assignments)
                    or any(not isinstance(path, str) or not path for path in records.values())
                    or len(assignments) != len(set(assignments))
                    or set(assignments) != set(records)):
                raise ValueError("assignment coverage must retain every failed/blocked original")
            assigned, recorded = len(assignments), len(records)
            if manifest.runs_path:
                original_name = (
                    _relative(manifest.runs_path) / "assignments.json"
                ).as_posix()
                if original_name not in manifest.artifact_hashes:
                    raise ValueError("bound original assignment list absent from inventory")
                original = json.loads(_resolve(root, original_name).read_text())
                from cloud_edge_robot_arm.datasets.rgbd.models import content_digest

                if not isinstance(original, dict) or (
                    original.get("schema_version") != "ced.assignments.v1"
                    or content_digest({key: value for key, value in original.items()
                                       if key != "content_hash"}) != original.get("content_hash")
                ):
                    raise ValueError("invalid bound original assignment list")
                original_ids = [row["assignment_id"] for row in original["assignments"]]
                if (len(original_ids) != len(set(original_ids))
                        or set(original_ids) != set(assignments)):
                    raise ValueError("index omits bound original assigned episodes")
                if manifest.protocol_hash and (
                    original.get("protocol_hash") != manifest.protocol_hash
                ):
                    raise ValueError("bound assignment list protocol hash mismatch")
                if manifest.protocol_path:
                    from cloud_edge_robot_arm.research.acceptance import CORE_METHODS
                    from cloud_edge_robot_arm.research.assignments import (
                        EpisodeAssignment,
                        build_assignments,
                    )

                    pool_name = (_relative(manifest.runs_path) / "pools.json").as_posix()
                    if pool_name not in manifest.artifact_hashes:
                        raise ValueError("bound original scene pool absent from inventory")
                    pools = json.loads(_resolve(root, pool_name).read_text())
                    rebuilt = build_assignments(frozen, CORE_METHODS, scene_pool=pools["formal"])
                    declared = [EpisodeAssignment(**row) for row in original["assignments"]]
                    if rebuilt != declared:
                        raise ValueError("assignment list omits exact frozen protocol assignments")
            if _archived_assignment_ids(root, manifest.artifact_hashes) != set(assignments):
                raise ValueError("assignment index omits archived original episode records")
            for path in set(records.values()):
                if path not in manifest.artifact_hashes:
                    raise ValueError("assignment record absent from artifact inventory")
                ids = {identity for identity, source in records.items() if source == path}
                if path.endswith(".jsonl"):
                    lines = _resolve(root, path).read_text().splitlines()
                    rows = [json.loads(line) for line in lines]
                    actual = [row["assignment"]["assignment_id"] for row in rows]
                    if len(actual) != len(set(actual)) or set(actual) != ids:
                        raise ValueError(
                            "JSONL source must retain every indexed original assignment")
                elif len(ids) != 1:
                    raise ValueError("different assignments cannot share a single JSON record")
                else:
                    row = json.loads(_resolve(root, path).read_text())
                    if row["assignment"]["assignment_id"] not in ids:
                        raise ValueError("JSON source does not match its indexed assignment")
        else:
            errors.append("assignment coverage index is missing")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "ced.reproduction-verification.v1",
        "integrity_valid": not errors, "scope": scope, "errors": errors,
        "assignment_count": assigned, "record_count": recorded,
        "research_accepted": False, "physical_reproduction": "NOT_RUN",
        "dependency_reproduction": "NOT_RUN",
    }


def rebuild_analysis(root: Path, output: Path, *, software_only: bool = False) -> None:
    """Call T16's same Python analysis entry; stored commands are metadata only."""
    verification = verify_reproduction_bundle(root)
    if verification["integrity_valid"] is not True:
        raise ValueError(f"bundle integrity failed: {verification['errors']}")
    manifest = _load(root)
    if output.exists():
        raise ValueError("reproduction output already exists")
    if not manifest.runs_path or not manifest.protocol_path:
        raise ValueError("analysis requires the bound runs and protocol paths")
    if manifest.scope == "SOFTWARE_ONLY" and not software_only:
        raise ValueError("software bundle requires explicit software_only analysis")
    runs, protocol = _resolve(root, manifest.runs_path), _resolve(root, manifest.protocol_path)
    required_inputs = (
        runs / "assignments.json", runs / "records.jsonl", runs / "pools.json",
        protocol / "protocol.json",
    )
    for path in required_inputs:
        if path.relative_to(root).as_posix() not in manifest.artifact_hashes:
            raise ValueError("analysis input absent from artifact inventory")
    from cloud_edge_robot_arm.research.protocol import load_protocol

    frozen = load_protocol(protocol)
    if manifest.protocol_hash != frozen.content_hash:
        raise ValueError("reproduction protocol hash differs from its bound protocol")
    if manifest.model_snapshot_hash != frozen.spec.model_snapshot_hash:
        raise ValueError("reproduction model hash differs from its bound protocol")
    from cloud_edge_robot_arm.research.acceptance import analyze_research_runs

    analysis = analyze_research_runs(runs, protocol, output, software_only=software_only)
    if manifest.analysis_path:
        original = _resolve(root, manifest.analysis_path)
        for name in ("metrics.json", "goal_verdicts.json"):
            expected, actual = original / name, output / name
            relative = expected.relative_to(root).as_posix()
            if relative not in manifest.artifact_hashes:
                raise ValueError("saved analysis result absent from artifact inventory")
            if json.loads(expected.read_text()) != json.loads(actual.read_text()):
                raise ValueError("recomputed metrics differ from the saved analysis")
    (output / "reproduction.json").write_text(json.dumps({
        **verification, "numeric_rebuild": analysis.get("status", "NOT_RUN"),
        "matches_saved_analysis": bool(manifest.analysis_path),
    }, indent=2) + "\n")
