"""已下载原生 RGBD 数据的离线门禁和原子转换；无网络入口。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .fiftyone_curated import _atomic_derived_write
from .prepared import DATASETS, safe_path
from .transfer import hash_file


def source_root(plan: dict[str, Any]) -> Path:
    if plan.get("source_mode") != "existing_downloads" or plan["dataset_id"] not in DATASETS:
        raise ValueError("prepared source must use explicit existing_downloads mode")
    return safe_path(
        Path(plan["data_root"]),
        f"downloads/{plan['dataset_id']}/{plan['source']}/{plan['revision']}",
    )


def verify_existing(plan: dict[str, Any]) -> dict[str, Any]:
    source = source_root(plan)
    if not plan["files"]:
        raise ValueError("selected source manifest is empty")
    names = set()
    total = 0
    for entry in plan["files"]:
        if entry["path"] in names:
            raise ValueError("duplicate source manifest path")
        names.add(entry["path"])
        path = safe_path(source, entry["path"])
        if not path.is_file():
            raise FileNotFoundError(f"selected source missing: {entry['path']}")
        if path.stat().st_size != entry["size"] or hash_file(path) != entry.get("sha256"):
            raise ValueError(f"selected source size/digest mismatch: {entry['path']}")
        total += path.stat().st_size
    return {
        "status": "VERIFIED_EXISTING",
        "files": len(names),
        "verified_bytes": total,
        "network_bytes": 0,
        "source_mode": "existing_downloads",
        "sha256_evidence": plan.get("reader_metadata", {}).get("sha256_evidence", "manifest"),
    }


def local_budget(plan: dict[str, Any]) -> dict[str, Any]:
    from .deployment import _verify_raw_marker

    root = Path(plan["data_root"])
    probe = root
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    expected = int(plan.get("extraction_estimated_bytes", 0))
    verified = verify_existing(plan)
    raw = safe_path(root, f"raw/{plan['dataset_id']}")
    reusable = (raw / "COMPLETE.json").exists()
    if reusable:
        # 只有完整核验身份及派生清单后，才可免去本轮不会发生的转换峰值。
        _verify_raw_marker(plan)
        expected = 0
    return {
        "status": "READY" if free >= plan["minimum_free_bytes"] + expected else "BLOCKED_STORAGE",
        "download_bytes": 0,
        "verified_existing_bytes": verified["verified_bytes"],
        "estimated_conversion_peak_bytes": expected,
        "raw_reusable": reusable,
        "estimation": "ESTIMATED",
        "free_bytes": free,
        "minimum_free_bytes": plan["minimum_free_bytes"],
        "network_mode": "offline_existing_files",
    }


def extract_prepared(plan: dict[str, Any]) -> dict[str, Any]:
    from .deployment import _plan_identity, _verify_raw_marker
    from .native_sources import convert_industry, convert_microagi, convert_vins

    root = Path(plan["data_root"])
    destination = safe_path(root, f"raw/{plan['dataset_id']}")
    if (destination / "COMPLETE.json").exists():
        marker = _verify_raw_marker(plan)
        return {"status": "REUSED", "raw_path": str(destination), **marker}
    if destination.exists():
        raise ValueError("INCOMPLETE: prepared raw lacks completion marker")
    gate = local_budget(plan)
    if gate["status"] != "READY":
        raise RuntimeError("BLOCKED_STORAGE: insufficient space for estimated conversion peak")
    stage = safe_path(root, f"raw/.{plan['dataset_id']}-prepared.partial")
    stage.mkdir(parents=True, exist_ok=True)
    identity = _plan_identity(plan)
    state = safe_path(stage, ".deployment-identity.json")
    if state.exists() and json.loads(state.read_text()) != identity:
        raise ValueError("prepared staging source/selection identity mismatch")
    reserve = plan["minimum_free_bytes"]
    _atomic_derived_write(stage, state.name, json.dumps(identity).encode(), reserve)
    converter = {
        "industryshapes_real": convert_industry,
        "microagi01_small": convert_microagi,
        "vins_rgbd_small": convert_vins,
    }[plan["dataset_id"]]
    rows, report = converter(plan, source_root(plan), stage)
    selection = plan["smoke_selection"]
    if len(rows) != selection["expected_rgbd_samples"]:
        raise ValueError(f"prepared pair count differs from fixed scope: {len(rows)}")
    # 转换后再次校验原始来源，防止转换期间源文件被替换。
    verify_existing(plan)
    index = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
    _atomic_derived_write(stage, "samples.jsonl", index, reserve)
    _atomic_derived_write(
        stage, "conversion.json", json.dumps(report, ensure_ascii=False).encode(), reserve
    )
    members = {"samples.jsonl", "conversion.json"}
    for row in rows:
        relative = row["record_relative_path"]
        members.add(relative)
        envelope = json.loads(safe_path(stage, relative).read_text())
        members.update(item["path"] for item in envelope["images"].values())
    inventory = []
    for name in sorted(members):
        path = safe_path(stage, name)
        inventory.append({"path": name, "size": path.stat().st_size, "sha256": hash_file(path)})
    marker = {
        "identity": identity,
        "extracted_files": inventory,
        "source_format": "prepared_rgbd",
        "materialized_samples": len(rows),
        "conversion_report": report,
        "original_full_target_verified": False,
    }
    _atomic_derived_write(
        stage, "COMPLETE.json", json.dumps(marker, ensure_ascii=False).encode(), reserve
    )
    stage.replace(destination)
    return {"status": "COMPLETE", "raw_path": str(destination), **marker}


def selected_scope_ready(plan: dict[str, Any], current: dict[str, Any]) -> bool:
    selection = plan["smoke_selection"]
    expected = selection["expected_rgbd_samples"]
    return bool(
        expected > 0
        and current["samples"] == expected
        and current["groups"] == selection["expected_groups"]
        and current["quarantined"] == 0
        and current["split_audit"]["valid"]
        and current["preview_report"]["frames"]
        >= min(expected, plan["profile_config"]["preview_groups"])
    )
