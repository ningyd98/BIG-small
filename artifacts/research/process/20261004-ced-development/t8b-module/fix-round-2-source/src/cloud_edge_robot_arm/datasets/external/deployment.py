"""第三方数据的幂等部署编排；实际数据与软件夹具验收分开保存。"""

from __future__ import annotations

import hashlib
import html
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from cloud_edge_robot_arm.datasets.external.index import build_index, group_key, load_index
from cloud_edge_robot_arm.datasets.external.loaders import DatasetLoader, read_sample
from cloud_edge_robot_arm.datasets.external.preview import save_preview
from cloud_edge_robot_arm.datasets.external.provider import DatasetObservationProvider

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATASETS = (
    "robomind",
    "graspclutter6d",
    "graspclutter6d_curated",
    "industryshapes_real",
    "microagi01_small",
    "vins_rgbd_small",
)
GIB = 1024**3


def data_root(value: Path | None) -> Path:
    return (
        (
            value
            or Path(
                os.environ.get("BIGSMALL_DATA_ROOT", str(Path.home() / "datasets" / "BIGsmall"))
            )
        )
        .expanduser()
        .resolve()
    )


def load_config(path: Path | None = None) -> dict[str, Any]:
    value = yaml.safe_load((path or PROJECT_ROOT / "configs/rgbd_datasets.yaml").read_text())
    if not isinstance(value, dict):
        raise ValueError("dataset config must contain a mapping")
    return value


def prepare_plan(
    dataset: str, profile: str, root: Path, config: Path | None = None
) -> dict[str, Any]:
    cfg = load_config(config)
    if dataset not in DATASETS or profile not in cfg["profiles"]:
        raise ValueError("unknown dataset or profile")
    manifest = Path(cfg["datasets"][dataset]["source_manifest"])
    if not manifest.is_absolute():
        manifest = PROJECT_ROOT / manifest
    source = json.loads(manifest.read_text())
    limit = cfg["budget"][
        "robomind_download_gib" if dataset.startswith("robomind") else "total_download_gib"
    ]
    budget = int(limit * GIB)
    if budget <= 0 or budget > int(cfg["budget"]["total_download_gib"] * GIB):
        raise ValueError("dataset budget exceeds the configured total limit")
    return {
        **source,
        "profile": profile,
        "data_root": str(root.resolve()),
        "budget_bytes": int(cfg["budget"]["total_download_gib"] * GIB),
        "dataset_budget_bytes": budget,
        "total_budget_bytes": int(cfg["budget"]["total_download_gib"] * GIB),
        "minimum_free_bytes": int(cfg["budget"]["minimum_free_gib"] * GIB),
        "extraction_estimated_bytes": (8 if source.get("storage_format") == "prepared_rgbd" else 3)
        * sum(f["size"] for f in source["files"]),
        "estimation": "ESTIMATED",
        "download_workers": cfg["budget"]["download_workers"],
        "decode_workers": cfg["budget"]["decode_workers"],
        "retries": cfg["budget"]["retries"],
        "profile_config": cfg["profiles"][profile],
        "network": {
            **cfg.get("network", {}),
            **source.get("network", {}),
            **cfg["datasets"][dataset].get("network", {}),
        },
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix + ".partial")
    stage.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    stage.replace(path)


def doctor(root: Path, *, check_sources: bool = True, config: Path | None = None) -> dict[str, Any]:
    import httpx

    probe = root
    while not probe.exists():
        probe = probe.parent
    disk = shutil.disk_usage(probe)
    modules: dict[str, str | None] = {}
    for module in ("numpy", "Pillow", "h5py", "huggingface_hub", "py7zr", "matplotlib"):
        try:
            modules[module] = importlib.metadata.version(module)
        except importlib.metadata.PackageNotFoundError:
            modules[module] = None
    gpu = (
        subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if shutil.which("nvidia-smi")
        else "not present; CPU reading supported"
    )
    sources: dict[str, Any] = {}
    if check_sources:
        from cloud_edge_robot_arm.datasets.external.network import (
            create_direct_transport,
            require_allowed_host,
        )

        cfg = load_config(config)
        for name, dataset in {"huggingface": "graspclutter6d", "modelscope": "robomind"}.items():
            policy = {**cfg.get("network", {}), **cfg["datasets"][dataset].get("network", {})}
            if policy.get("blocked_reason") or policy.get("mode") != "direct":
                sources[name] = {"status": "BLOCKED_NETWORK", "direct_only": True}
                continue
            url = (
                str(policy.get("hf_endpoint") or "") + "/api/datasets/GraspClutter6D/GraspClutter6D"
                if name == "huggingface"
                else "https://modelscope.cn/api/v1/datasets/X-Humanoid/RoboMIND"
            )
            try:
                require_allowed_host(url, policy)
                with httpx.Client(
                    transport=create_direct_transport(policy),
                    trust_env=False,
                    timeout=15,
                    follow_redirects=True,
                    event_hooks={
                        "request": [
                            lambda request, p=policy: require_allowed_host(str(request.url), p)
                        ]
                    },
                ) as client:
                    response = client.get(url)
                sources[name] = {"status_code": response.status_code, "network_mode": "direct"}
            except (httpx.HTTPError, RuntimeError, ValueError, OSError) as exc:
                sources[name] = {"error_type": type(exc).__name__, "status": "BLOCKED_NETWORK"}
    return {
        "os": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "cpu_count": os.cpu_count(),
        "meminfo": Path("/proc/meminfo").read_text().splitlines()[:3],
        "gpu": gpu,
        "data_root": str(root),
        "write_permission": os.access(probe, os.W_OK),
        "free_bytes": disk.free,
        "free_inodes": os.statvfs(probe).f_favail,
        "minimum_free_bytes": 50 * GIB,
        "dependencies": modules,
        "credential_presence": {
            key: bool(os.environ.get(key)) for key in ("HF_TOKEN", "MODELSCOPE_API_TOKEN")
        },
        "proxy_presence": {
            key: bool(os.environ.get(key)) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
        },
        "download_network_requirement": "physical_interface_direct_only",
        "source_checks": sources,
        "cpu_supported": True,
    }


def report_path(root: Path, dataset: str) -> Path:
    return root / "reports" / dataset / "deployment.json"


def status(dataset: str, root: Path) -> dict[str, Any]:
    path = report_path(root, dataset)
    default = {
        "dataset_id": dataset,
        "software_ready": False,
        "download_status": "NOT_STARTED",
        "rgbd_status": "NOT_CHECKED",
        "geometry_status": "NOT_CHECKED",
        "temporal_status": "NOT_CHECKED",
        "annotation_status": "NOT_CHECKED",
        "integration_status": "NOT_CHECKED",
        "verified_scope": "NOT_VERIFIED",
        "data_root": str(root),
    }
    result = {**default, **(json.loads(path.read_text()) if path.exists() else {})}
    download_dir = root / "downloads" / dataset
    result["partial_files"] = (
        [{"path": str(p), "bytes": p.stat().st_size} for p in download_dir.rglob("*.part")]
        if download_dir.exists()
        else []
    )
    return result


def update_status(root: Path, dataset: str, **values: Any) -> dict[str, Any]:
    result = {**status(dataset, root), **values}
    result.pop("partial_files", None)
    write_json(report_path(root, dataset), result)
    return result


def index_path(root: Path, dataset: str) -> Path:
    return root / "manifests" / f"{dataset}-index.jsonl"


def _plan_identity(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": plan.get("dataset_id"),
        "storage_format": plan.get("storage_format"),
        "reader_metadata": plan.get("reader_metadata", {}),
        "revision": plan.get("revision"),
        "source": plan.get("source"),
        "files": [
            {"path": file["path"], "sha256": file.get("sha256")} for file in plan.get("files", [])
        ],
        "selection": plan.get("smoke_selection", {}),
    }


def _verify_raw_marker(plan: dict[str, Any]) -> dict[str, Any]:
    from cloud_edge_robot_arm.datasets.external.transfer import hash_file

    raw = Path(plan["data_root"]) / "raw" / plan["dataset_id"]
    marker = raw / "COMPLETE.json"
    if not marker.is_file() or marker.is_symlink():
        raise ValueError("raw dataset is missing its completed deployment marker")
    stored = json.loads(marker.read_text())
    if stored.get("identity") != _plan_identity(plan):
        raise ValueError("raw marker source/revision/selection identity mismatch")
    if not stored.get("extracted_files"):
        raise ValueError("completed raw marker has no verified source files")
    for entry in stored["extracted_files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("raw inventory path escapes root")
        target = raw / relative
        if any(path.is_symlink() for path in [target, *target.parents]):
            raise ValueError("raw source symlinks are forbidden")
        if not target.is_file() or hash_file(target) != entry["sha256"]:
            raise ValueError("raw inventory content no longer matches pinned deployment")
    return dict(stored)


def trajectory_completeness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("episode_id"):
            groups.setdefault(group_key(row), []).append(row)
    complete = []
    complete_tasks = set()
    for key, group in groups.items():
        cameras = {row["camera_id"] for row in group}
        valid = all(
            {row["frame_index"] for row in group if row["camera_id"] == camera}
            == set(range(group[0].get("episode_length", 0)))
            and group[0].get("episode_length", 0) > 0
            for camera in cameras
        )
        if valid:
            complete.append(key)
            if group[0].get("task_id"):
                complete_tasks.add(group[0]["task_id"])
    return {
        "complete_episodes": len(complete),
        "complete_tasks": len(complete_tasks),
        "complete_episode_ids": sorted(complete),
        "complete_task_ids": sorted(complete_tasks),
        "incomplete_episodes": len(groups) - len(complete),
    }


def discover(plan: dict[str, Any]) -> list[dict[str, Any]]:
    dataset = plan["dataset_id"]
    root = Path(plan["data_root"]) / "raw" / dataset
    _verify_raw_marker(plan)
    if plan.get("storage_format") == "prepared_rgbd":
        from .prepared import discover_prepared

        return discover_prepared(root, dataset, plan["revision"])
    if dataset == "graspclutter6d_curated":
        from .fiftyone_curated import discover_curated_grasp_samples

        return discover_curated_grasp_samples(
            root, plan["revision"], plan["smoke_selection"]["scene_ids"]
        )
    if dataset == "robomind":
        from cloud_edge_robot_arm.datasets.external.robomind import discover_robomind_samples

        metadata: dict[str, Any] = {}
        try:
            return discover_robomind_samples(root, plan["revision"], metadata)
        finally:
            write_json(
                Path(plan["data_root"]) / "reports" / dataset / "discovery-quarantine.json",
                {"quarantine": metadata.get("quarantine", [])},
            )
    from cloud_edge_robot_arm.datasets.external.graspclutter import discover_grasp_samples

    selection = plan["smoke_selection"]
    splits = {scene: "train" for scene in selection["official_train_scene_ids"]}
    splits.update({scene: "test" for scene in selection["official_test_scene_ids"]})
    return discover_grasp_samples(
        root, plan["revision"], splits, selection["scene_ids"], protocol=selection["protocol"]
    )


def validate_dataset(plan: dict[str, Any]) -> dict[str, Any]:
    rows = discover(plan)
    quarantine = []
    valid = []
    totals: dict[str, int] = {}
    for ref in rows:
        try:
            sample = read_sample(ref)
            if sample.metadata.get("sample_provenance") == "synthetic_fixture":
                raise ValueError("synthetic fixture cannot pass real deployment validation")
            if not sample.capabilities["rgbd_decodable"]:
                raise ValueError("all-zero/invalid depth cannot enter valid RGB-D set")
            for name, available in sample.capabilities.items():
                totals[name] = totals.get(name, 0) + int(available)
            ref["content_sha256"] = hashlib.sha256(
                sample.rgb.tobytes() + sample.depth_raw.tobytes()
            ).hexdigest()
            annotation_issues = list(sample.metadata.get("annotation_issues", []))
            annotation_issues.extend(sample.annotations.get("issues", []))
            if plan["dataset_id"] == "graspclutter6d_curated":
                instances = sample.annotations.get("instances", [])
                if not instances:
                    annotation_issues.append("curated instance annotations are unavailable")
                elif any(not item.get("visible_mask", {}).get("available") for item in instances):
                    annotation_issues.append("curated visible mask annotations are incomplete")
            ref["quality"] = {
                "capabilities": sample.capabilities,
                "valid_ratio": float(sample.depth_valid_mask.mean()),
                "rgb_shape": list(sample.rgb.shape),
                "depth_dtype": str(sample.depth_raw.dtype),
                "annotation_issues": annotation_issues,
            }
            valid.append(ref)
        except (ValueError, OSError, IndexError, KeyError) as exc:
            quarantine.append({"ref": ref, "error_type": type(exc).__name__, "reason": str(exc)})
    root = Path(plan["data_root"])
    discovery_file = root / "reports" / plan["dataset_id"] / "discovery-quarantine.json"
    discovery_quarantine = (
        json.loads(discovery_file.read_text()).get("quarantine", [])
        if discovery_file.exists()
        else []
    )
    write_json(
        root / "reports" / plan["dataset_id"] / "quality.json",
        {
            "sample_count": len(rows),
            "valid_count": len(valid),
            "quarantine": quarantine,
            "trajectory_quarantine": discovery_quarantine,
            "capability_counts": totals,
        },
    )
    if not valid:
        raise ValueError("no valid real RGB-D samples; see quality.json")
    result = build_index(
        valid,
        index_path(root, plan["dataset_id"]),
        validation_fraction=plan["profile_config"]["validation_fraction"],
    )
    completeness = trajectory_completeness(valid)
    return {
        "samples": len(valid),
        "quarantined": len(quarantine) + len(discovery_quarantine),
        "quarantined_frames": len(quarantine),
        "quarantined_trajectories": len(discovery_quarantine),
        **completeness,
        "capability_counts": totals,
        "index_report": result,
        "rows": valid,
        "quality": str(root / "reports" / plan["dataset_id"] / "quality.json"),
    }


def preview_dataset(plan: dict[str, Any]) -> dict[str, Any]:
    root = Path(plan["data_root"])
    rows = load_index(index_path(root, plan["dataset_id"]))
    selected = []
    seen = set()
    for row in rows:
        group = row.get("episode_id") or row.get("scene_id")
        if group not in seen:
            selected.append(row)
            seen.add(group)
        if len(selected) >= plan["profile_config"]["preview_groups"]:
            break
    if plan.get("storage_format") == "prepared_rgbd":
        # 单条序列抽取多个原始帧，帧数与独立场景/轨迹数分别报告。
        count = min(len(rows), plan["profile_config"]["preview_groups"])
        if len(selected) < count:
            selected = [rows[int(i)] for i in np.linspace(0, len(rows) - 1, count)]
    out = root / "previews" / plan["dataset_id"]
    reports = [save_preview(read_sample(row), out / row["sample_id"]) for row in selected]
    out.mkdir(parents=True, exist_ok=True)
    figures = "".join(
        f'<figure><img src="{html.escape(row["sample_id"])}/preview.png">'
        f"<figcaption>{html.escape(row['sample_id'])}</figcaption></figure>"
        for row in selected
    )
    (out / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>RGBD offline</title>'
        "<h1>Dataset replay</h1><p>Offline observations; no execution evidence.</p>" + figures
    )
    return {
        "groups": len({row.get("episode_id") or row.get("scene_id") for row in selected}),
        "frames": len(reports),
        "previews": reports,
        "html": str(out / "index.html"),
    }


def smoke_dataset(plan: dict[str, Any], *, num_workers: int = 0) -> dict[str, Any]:
    root = Path(plan["data_root"])
    rows = load_index(index_path(root, plan["dataset_id"]))
    count = plan["profile_config"]["batch_size"]
    for row in rows[:count]:
        sample = read_sample(row)
        if sample.metadata.get("sample_provenance") == "synthetic_fixture":
            raise ValueError("synthetic_fixture cannot be reported as a real dataset batch")
        if row.get("source_revision") != plan.get("revision"):
            raise ValueError("index source revision identity does not match plan")
        if row.get("dataset_id") != plan["dataset_id"]:
            raise ValueError("index dataset identity does not match plan")
        row_root = row.get("source_root", row.get("root"))
        if (
            not row_root
            or Path(row_root).resolve() != (root / "raw" / plan["dataset_id"]).resolve()
        ):
            raise ValueError("index source root does not belong to pinned raw deployment")
    _verify_raw_marker(plan)
    started = time.monotonic()
    baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    batch = next(iter(DatasetLoader(rows[:count], batch_size=count, num_workers=num_workers)))
    observation = DatasetObservationProvider(rows).next_observation()
    if "annotations" in observation or "action" in observation:
        raise ValueError("oracle/action leakage into ordinary model observation")
    shape = {
        name: {"shape": list(value.shape), "dtype": str(value.dtype)}
        if isinstance(value, np.ndarray)
        else {"items": len(value), "nullable": any(v is None for v in value)}
        for name, value in batch.items()
    }
    result = {
        "source": "real_dataset",
        "execution_verified": False,
        "samples": len(rows[:count]),
        "num_workers": num_workers,
        "batch": shape,
        "read_elapsed_s": time.monotonic() - started,
        "parent_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "parent_baseline_rss_bytes": baseline * 1024,
        "peak_scope": "parent process lifetime; child worker peaks recorded separately",
        "child_peak_rss_bytes": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
        "depth_valid_ratios": [
            float(read_sample(row).depth_valid_mask.mean()) for row in rows[:count]
        ],
        "calibration": [read_sample(row).capabilities for row in rows[:count]],
        "original_timestamp_preserved": True,
        "gt_channel_separate": True,
        "hardware_disabled": True,
    }
    write_json(root / "reports" / plan["dataset_id"] / f"smoke-workers-{num_workers}.json", result)
    return result


def extract_dataset(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("storage_format") == "prepared_rgbd":
        from .prepared_deployment import extract_prepared

        return extract_prepared(plan)
    if plan.get("storage_format") == "fiftyone_curated":
        from .curated_deployment import extract_curated_dataset

        return extract_curated_dataset(plan)
    from cloud_edge_robot_arm.datasets.external.archives import extract_archive, inspect_archive
    from cloud_edge_robot_arm.datasets.external.transfer import hash_file

    root = Path(plan["data_root"])
    download = root / "downloads" / plan["dataset_id"] / plan["source"] / plan["revision"]
    destination = root / "raw" / plan["dataset_id"]
    identity = _plan_identity(plan)
    complete = destination / "COMPLETE.json"
    if complete.exists():
        marker = json.loads(complete.read_text())
        if marker["identity"] != identity:
            raise ValueError("raw deployment revision/selection mismatch; preserve existing data")
        for entry in marker["extracted_files"]:
            path = destination / entry["path"]
            if path.is_symlink() or not path.is_file() or hash_file(path) != entry["sha256"]:
                raise ValueError("raw deployment integrity changed")
        return {"status": "REUSED", "raw_path": str(destination), **marker}
    if destination.exists():
        raise ValueError("INCOMPLETE: raw destination lacks a completion marker")
    for file in plan["files"]:
        path = download / file["path"]
        if (
            not path.is_file()
            or path.stat().st_size != file["size"]
            or (file.get("sha256") and hash_file(path) != file["sha256"])
        ):
            raise ValueError(f"complete verified download required: {file['path']}")
    stage = root / "raw" / f".{plan['dataset_id']}-{plan['revision']}.partial"
    stage.mkdir(parents=True, exist_ok=True)
    stage_identity = stage / ".deployment-identity.json"
    if stage_identity.exists() and json.loads(stage_identity.read_text()) != identity:
        raise ValueError("staging revision mismatch")
    write_json(stage_identity, identity)
    groups = []
    used = set()
    for group in plan.get("archive_dependency_groups", []):
        names = group["all_required"]
        used.update(names)
        groups.append((group["archive"], names))
    groups += [(f["path"], [f["path"]]) for f in plan["files"] if f["path"] not in used]
    inventories = []
    bundle_reports = []
    for number, (archive_name, names) in enumerate(groups):
        parts = [download / name for name in names]
        listing_file = root / "manifests" / plan["dataset_id"] / f"archive-{number}-listing.json"
        # 原压缩包已按官方SHA核验；重用相同SHA的完整listing，避免重复全归档CRC。
        key = [
            {"path": f["path"], "sha256": f.get("sha256")}
            for f in plan["files"]
            if f["path"] in names
        ]
        stored = json.loads(listing_file.read_text()) if listing_file.exists() else None
        if stored is not None and stored["source_identity"] == key:
            listing = stored["listing"]
        else:
            listing = inspect_archive(parts)
            write_json(listing_file, {"source_identity": key, "listing": listing})
        members = listing["members"]
        selection: list[str] | None = None
        if plan["dataset_id"] == "graspclutter6d":
            selected = plan["smoke_selection"]
            if archive_name == "scenes.7z":
                selection = [f"scenes/{scene}/" for scene in selected["scene_ids"]]
            elif archive_name in {"models_m.7z", "grasp_label.7z"}:
                objects = {f"obj_{obj:06d}" for obj in selected["object_ids"]}
                selection = [
                    member["path"]
                    for member in members
                    if member["type"] == "file"
                    and any(Path(member["path"]).name.startswith(obj) for obj in objects)
                ]
            elif archive_name == "collision_label.7z":
                scenes = set(selected["scene_ids"])
                selection = [
                    member["path"]
                    for member in members
                    if member["type"] == "file" and Path(member["path"]).stem in scenes
                ]
        wanted = [
            member
            for member in members
            if member["type"] == "file"
            and (
                selection is None
                or any(
                    member["path"] == name
                    or (name.endswith("/") and member["path"].startswith(name))
                    for name in selection
                )
            )
        ]
        expanded = sum(member["size"] for member in wanted)
        if not wanted:
            raise ValueError(f"archive has no selected members for {archive_name}")
        if shutil.disk_usage(stage).free < expanded + plan["minimum_free_bytes"]:
            raise RuntimeError("BLOCKED_STORAGE: selected expansion violates reserve")
        bundle = stage / ".bundles" / str(number)
        assembly_report = stage / f".bundle-{number}-assembled.json"
        if assembly_report.exists():
            report = json.loads(assembly_report.read_text())
        else:
            report = extract_archive(
                parts,
                bundle,
                selected_members=selection,
                max_expanded_bytes=expanded,
                minimum_free_bytes=plan["minimum_free_bytes"],
            )
            # 先持久化已完成解压的inventory，移动中断后不重新验证已被搬空的bundle。
            write_json(assembly_report, report)
        for entry in report["files"]:
            source = bundle / entry["path"]
            target = stage / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if hash_file(target) != entry["sha256"]:
                    raise ValueError("staging member collision/integrity mismatch")
            elif source.exists():
                source.replace(target)
            else:
                raise ValueError("incomplete assembly lost a verified member")
        for entry in report["files"]:
            path = stage / entry["path"]
            if not path.is_file() or path.stat().st_size != entry["size"]:
                raise ValueError("assembled stage file is missing")
            inventories.append(entry)
        bundle_reports.append(
            {
                "archive": archive_name,
                "expanded_bytes": expanded,
                "integrity_status": report["integrity_status"],
            }
        )
    marker = {
        "identity": identity,
        "extracted_files": inventories,
        "archives": bundle_reports,
        "source": plan.get("sample_provenance", "real_dataset"),
        "raw_path": str(destination),
    }
    write_json(stage / "COMPLETE.json", marker)
    stage.replace(destination)
    return {"status": "COMPLETE", **marker}


def run_operation(command: str, plan: dict[str, Any], *, num_workers: int = 0) -> dict[str, Any]:
    from cloud_edge_robot_arm.datasets.external.transfer import download_plan, plan_budget

    root, dataset = Path(plan["data_root"]), plan["dataset_id"]
    prepared = plan.get("storage_format") == "prepared_rgbd"
    if command == "plan":
        if prepared:
            from .prepared_deployment import local_budget

            budget = local_budget(plan)
        else:
            budget = plan_budget(plan)
        report = {"plan": plan, "budget": budget}
        write_json(root / "manifests" / f"{dataset}-download-plan.json", report)
        return report
    if command == "status":
        return status(dataset, root)
    if command == "download":
        update_status(
            root, dataset, download_status="DOWNLOADING", source_revision=plan["revision"]
        )
        if prepared:
            from .prepared_deployment import verify_existing

            result = verify_existing(plan)
        else:
            result = download_plan(
                plan, max_workers=plan["download_workers"], retries=plan["retries"]
            )
        write_json(root / "reports" / dataset / "download.json", result)
        update_status(
            root,
            dataset,
            download_status=result["status"],
            download_report=str(root / "reports" / dataset / "download.json"),
        )
        return result
    if command == "extract":
        result = extract_dataset(plan)
        update_status(
            root, dataset, extraction_status=result["status"], raw_path=result["raw_path"]
        )
        return result
    if command in {"validate", "index"}:
        result = validate_dataset(plan)
        counts = result["capability_counts"]
        geometry = counts.get("camera_geometry", 0) == result["samples"]
        annotation_issues = [
            row["quality"]["annotation_issues"]
            for row in result["rows"]
            if row["quality"]["annotation_issues"]
        ]
        groups = {group_key(row) for row in result["rows"]}
        tasks = {row.get("task_id") for row in result["rows"] if row.get("task_id")}
        update_status(
            root,
            dataset,
            samples=result["samples"],
            groups=len(groups),
            tasks=len(tasks),
            quarantined=result["quarantined"],
            quarantined_frames=result["quarantined_frames"],
            quarantined_trajectories=result["quarantined_trajectories"],
            complete_episodes=result["complete_episodes"],
            complete_tasks=result["complete_tasks"],
            incomplete_episodes=result["incomplete_episodes"],
            rgbd_status="RGBD_READABLE",
            geometry_status="VERIFIED_CAMERA_GEOMETRY"
            if geometry
            else "RGBD_READABLE_GEOMETRY_UNVERIFIED",
            temporal_status="VERIFIED"
            if counts.get("temporal_alignment", 0) == result["samples"]
            else "UNVERIFIED",
            annotation_status="UNAVAILABLE"
            if counts.get("task_annotations", 0) == 0
            else "PARTIAL"
            if annotation_issues
            else (
                "CURATED_2D_ANNOTATIONS_AVAILABLE"
                if dataset == "graspclutter6d_curated"
                else "AVAILABLE_EVALUATION_NOT_RUN"
            ),
            index=str(index_path(root, dataset)),
            quality_report=result["quality"],
            split_audit=result["index_report"]["audit"],
            capability_counts=counts,
        )
        return {key: value for key, value in result.items() if key != "rows"}
    if command == "preview":
        result = preview_dataset(plan)
        update_status(root, dataset, preview_report=result)
        return result
    if command == "smoke":
        result = smoke_dataset(plan, num_workers=num_workers)
        update_status(
            root,
            dataset,
            integration_status="OFFLINE_INTERFACE_VERIFIED",
            smoke_report=str(root / "reports" / dataset / f"smoke-workers-{num_workers}.json"),
        )
        return result
    if command == "deploy":
        gate = run_operation("plan", plan)["budget"]
        if gate["status"] != "READY":
            update_status(
                root,
                dataset,
                download_status=gate["status"],
                verified_scope="NOT_VERIFIED",
                reason=gate.get("network_reason") or plan.get("reason") or gate["status"],
            )
            return status(dataset, root)
        for step in ("download", "extract", "validate", "preview", "smoke"):
            run_operation(step, plan, num_workers=num_workers)
        if num_workers != 0:
            run_operation("smoke", plan, num_workers=0)
        current = status(dataset, root)
        audit = current["split_audit"]["valid"]
        enough = (
            current["groups"] >= 10
            if dataset == "graspclutter6d"
            else current["complete_episodes"] >= 10 and current["complete_tasks"] >= 2
        )
        previews = current["preview_report"]["groups"] >= 5
        annotations = dataset != "graspclutter6d" or current["annotation_status"] != "PARTIAL"
        verified = audit and enough and previews and annotations
        curated = dataset == "graspclutter6d_curated"
        if curated:
            from .curated_deployment import curated_scope_ready

            verified = curated_scope_ready(plan, current)
        if prepared:
            from .prepared_deployment import selected_scope_ready

            verified = selected_scope_ready(plan, current)
        scope = (
            (
                "SELECTED_RGBD_VERIFIED"
                if prepared
                else "CURATED_RGBD_VERIFIED"
                if curated
                else f"{plan['profile'].upper()}_VERIFIED"
            )
            if verified
            else "PARTIAL_REAL_DATA"
        )
        return update_status(
            root,
            dataset,
            verified_scope=scope,
            software_ready=True,
            deployment_status="COMPLETE" if verified else "PARTIAL",
            verified_scene_ids=plan.get("smoke_selection", {}).get("scene_ids", []),
            evaluation_status="NOT_RUN",
            execution_verified=False,
            original_full_target_verified=False,
        )
    raise ValueError("unknown data command")
