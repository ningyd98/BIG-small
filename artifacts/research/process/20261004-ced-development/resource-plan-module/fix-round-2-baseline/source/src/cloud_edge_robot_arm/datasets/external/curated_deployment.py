"""精选文件源的原子发布；精选验收不升级完整数据目标。"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from .transfer import _safe_target, hash_file


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("curated source path escapes root")
    if value != path.as_posix() or value in {"", ".", "COMPLETE.json"}:
        raise ValueError("invalid curated source path")
    return value


def _copy_source(source: Path, target: Path, reserve: int) -> None:
    """逐块复制已验来源，未完成文件不冒充已发布raw。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".copy.partial")
    if temporary.is_symlink():
        raise ValueError("unsafe curated staging symlink")
    with source.open("rb") as stream, temporary.open("wb") as output:
        while chunk := stream.read(1024 * 1024):
            if shutil.disk_usage(target.parent).free < reserve + len(chunk):
                raise RuntimeError("BLOCKED_STORAGE: curated copy violates disk reserve")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(target)


def extract_curated_dataset(plan: dict[str, Any]) -> dict[str, Any]:
    from .deployment import _plan_identity, _verify_raw_marker, write_json
    from .fiftyone_curated import materialize_curated_records

    root = Path(plan["data_root"])
    destination = root / "raw" / plan["dataset_id"]
    _safe_target(destination, root)
    if (destination / "COMPLETE.json").exists():
        marker = _verify_raw_marker(plan)
        return {"status": "REUSED", "raw_path": str(destination), **marker}
    if destination.exists():
        raise ValueError("INCOMPLETE: curated raw lacks a completion marker")
    source = root / "downloads" / plan["dataset_id"] / plan["source"] / plan["revision"]
    for file in plan["files"]:
        path = source / _safe_relative(file["path"])
        _safe_target(path, root)
        if (
            not file.get("sha256")
            or not path.is_file()
            or path.stat().st_size != file["size"]
            or hash_file(path) != file["sha256"]
        ):
            raise ValueError("curated publication requires complete verified download")
    stage = root / "raw" / f".{plan['dataset_id']}-{plan['revision']}.partial"
    _safe_target(stage, root)
    stage.mkdir(parents=True, exist_ok=True)
    identity = _plan_identity(plan)
    state = stage / ".deployment-identity.json"
    if state.exists() and json.loads(state.read_text()) != identity:
        raise ValueError("curated staging selection/revision mismatch")
    write_json(state, identity)
    for file in plan["files"]:
        target = stage / _safe_relative(file["path"])
        _safe_target(target, root)
        if target.exists():
            if not target.is_file() or hash_file(target) != file["sha256"]:
                raise ValueError("curated staging source integrity mismatch")
            continue
        _copy_source(source / file["path"], target, plan["minimum_free_bytes"])
        if hash_file(target) != file["sha256"]:
            raise ValueError("curated copy source changed before publication")
    generated = materialize_curated_records(
        stage,
        plan["revision"],
        plan["smoke_selection"]["scene_ids"],
        metadata=plan.get("reader_metadata", {}),
        minimum_free_bytes=plan["minimum_free_bytes"],
    )
    members = [file["path"] for file in plan["files"]] + generated["files"]
    inventory = []
    for name in sorted(set(members)):
        path = stage / _safe_relative(name)
        _safe_target(path, root)
        if not path.is_file():
            raise ValueError("curated derived inventory member is missing")
        inventory.append({"path": name, "size": path.stat().st_size, "sha256": hash_file(path)})
    if shutil.disk_usage(stage).free < plan["minimum_free_bytes"]:
        raise RuntimeError("BLOCKED_STORAGE: curated materialization violates disk reserve")
    marker = {
        "identity": identity,
        "extracted_files": inventory,
        "source_format": "fiftyone_curated",
        "materialized_samples": generated["samples"],
        "original_full_target_verified": False,
    }
    write_json(stage / "COMPLETE.json", marker)
    stage.replace(destination)
    return {"status": "COMPLETE", "raw_path": str(destination), **marker}


def curated_scope_ready(plan: dict[str, Any], current: dict[str, Any]) -> bool:
    """数量与标注齐备才通过已选精选，不能称FULL或原规模已通过。"""
    selection = plan["smoke_selection"]
    expected = selection.get("expected_rgbd_samples", 0)
    return bool(
        expected > 0
        and current["samples"] == expected
        and current["groups"] == len(selection["scene_ids"])
        and current["quarantined"] == 0
        and current["split_audit"]["valid"]
        and current["preview_report"]["groups"] >= plan["profile_config"]["preview_groups"]
        and current["annotation_status"] == "CURATED_2D_ANNOTATIONS_AVAILABLE"
    )
