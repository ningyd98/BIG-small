"""Bounded dataset jobs and verified offline previews through the existing runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.cloud.api.simulation_workbench import _service
from cloud_edge_robot_arm.dashboard.models import UserRole
from cloud_edge_robot_arm.dashboard.security import enforce_dashboard_access, enforce_dashboard_role
from cloud_edge_robot_arm.datasets.rgbd.models import (
    DatasetConfig,
    SampleRecord,
    SplitManifest,
    safe_component,
    safe_relative_path,
)
from cloud_edge_robot_arm.simulation_runtime.models import SimulationJobRecord
from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft
from cloud_edge_robot_arm.vision.offline_reader import (
    load_offline_observation,
    resolve_payload,
)

router = APIRouter(prefix="/api/v1/rgbd-datasets", tags=["rgbd-datasets"])
PRESETS = {"SMOKE": "dataset_smoke.yaml", "VALIDATION": "dataset_validation.yaml",
           "FULL": "dataset_full.yaml"}


class DatasetJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_id: Literal["SMOKE", "VALIDATION", "FULL"] = "SMOKE"
    groups: int = Field(default=100, ge=1, le=10000)
    seed: int = Field(default=0, ge=0, le=2**31-1)
    width: int = Field(default=320, ge=1, le=1280)
    height: int = Field(default=240, ge=1, le=720)


class DatasetJobView(BaseModel):
    job_id: str
    dataset_id: str
    status: str
    requested_groups: int
    published_groups: int
    published_samples: int
    positive_samples: int
    negative_samples: int
    sample_ids: list[str]
    split_group_counts: dict[str, int]
    model_calls: Literal[0] = 0
    task_success: Literal[False] = False
    task_execution: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"
    cancel_requested: bool
    error_code: str


class DatasetSampleView(BaseModel):
    dataset_id: str
    sample_id: str
    group_id: str
    status: str
    split: str | None
    rgb_data_url: str
    depth_data_url: str
    depth_min_m: float | None
    depth_max_m: float | None
    valid_depth_fraction: float
    observation_metadata: dict[str, Any]
    rejection_reasons: list[str]
    execution_verified: Literal[False] = False
    evidence_scope: Literal["OFFLINE_CAPTURE"] = "OFFLINE_CAPTURE"


def _job(request: Request, identifier: str, *, dataset: bool = False) -> SimulationJobRecord:
    try:
        safe_component(identifier)
        repo = _service(request).runtime.repository
        job = repo.get_job_by_run_id(identifier) if dataset else repo.get_job(identifier)
        if job.draft.get("job_type") != "DATASET_GENERATION":
            raise KeyError(identifier)
        return job
    except (KeyError, ValueError) as exc:
        raise HTTPException(404, "dataset_job_not_found") from exc


def _root(request: Request, job: SimulationJobRecord) -> Path:
    service = _service(request)
    relative = safe_relative_path(job.artifact_root + "/dataset")
    root = service.artifact_root.absolute()
    cursor = root
    for part in Path(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("dataset path contains a symlink")
    if not cursor.resolve().is_relative_to(root.resolve()):
        raise ValueError("dataset path escapes configured artifacts")
    return cursor


def _published_records(root: Path) -> list[SampleRecord]:
    """Read committed metadata without decoding every image on every progress poll."""
    if not root.exists():
        return []
    if not (root / "config.json").exists():
        initializing = root / "episodes"
        if not initializing.exists() or (initializing.is_dir() and not initializing.is_symlink()
                                         and not any(initializing.iterdir())):
            return []
    config = DatasetConfig.model_validate_json(resolve_payload(root, "config.json").read_bytes())
    episodes = root / "episodes"
    if episodes.is_symlink():
        raise ValueError("symlink episodes forbidden")
    if not episodes.exists():
        return []
    records = []
    seen = set()
    for episode in sorted(episodes.iterdir()):
        if episode.is_symlink() or not episode.is_dir():
            raise ValueError("invalid published episode directory")
        safe_component(episode.name)
        prefix = f"episodes/{episode.name}/"
        commit = json.loads(resolve_payload(root, prefix + "COMMIT.json").read_bytes())
        payload = resolve_payload(root, prefix + "records.jsonl").read_bytes()
        if (commit.get("schema_version") != "rgbd.dataset.v1"
                or commit.get("config_hash") != config.config_hash
                or commit.get("records_sha256") != hashlib.sha256(payload).hexdigest()):
            raise ValueError("published metadata checksum/config mismatch")
        rows = [SampleRecord.model_validate_json(line).model_copy(update={"root": root})
                for line in payload.splitlines() if line.strip()]
        if len(rows) != commit.get("sample_count") or not rows:
            raise ValueError("published sample count mismatch")
        for row in rows:
            if row.episode_id != episode.name or row.sample_id in seen:
                raise ValueError("duplicate or foreign published sample")
            seen.add(row.sample_id)
            records.append(row)
    return records


def _splits(root: Path) -> SplitManifest | None:
    if not (root / "reports/split_audit.json").exists():
        return None
    return SplitManifest.model_validate_json(
        resolve_payload(root, "reports/split_audit.json").read_bytes()
    )


def _view(request: Request, job: SimulationJobRecord) -> DatasetJobView:
    try:
        root = _root(request, job)
        records = _published_records(root)
        splits = _splits(root)
        groups = {row.group_id for row in records}
        split_counts = Counter(splits.group_assignments[g] for g in groups
                               if splits and g in splits.group_assignments)
        return DatasetJobView(
            job_id=job.job_id, dataset_id=job.run_id, status=str(job.status),
            requested_groups=int(job.draft["dataset_config"]["groups"]),
            published_groups=len(groups), published_samples=len(records),
            positive_samples=sum(r.status == "POSITIVE" for r in records),
            negative_samples=sum(r.status == "NEGATIVE" for r in records),
            sample_ids=[r.sample_id for r in records],
            split_group_counts={str(k): v for k, v in split_counts.items()},
            cancel_requested=job.cancel_requested, error_code=job.error_code,
        )
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(409, "dataset_published_evidence_invalid") from exc


@router.post("/jobs", status_code=202, response_model=DatasetJobView)
async def create_job(request: Request, body: DatasetJobRequest) -> DatasetJobView:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        preset = yaml.safe_load((Path("configs/rgbd") / PRESETS[body.config_id]).read_text())
        config = DatasetConfig.model_validate({**preset, "dataset_id": f"ui-{uuid.uuid4().hex}",
            "groups": body.groups, "seed": body.seed, "width": body.width, "height": body.height})
        draft = ExperimentDraft.model_validate({
            "backend": "MUJOCO", "job_type": "DATASET_GENERATION", "input_mode": "RGBD",
            "execution_scope": "CAPTURE_ONLY", "scenarios": ["S01_NORMAL_STATIC"],
            "control_modes": ["PCSC"], "seeds": [body.seed],
            "dataset_config": config.model_dump(mode="json"),
        })
        run = await asyncio.to_thread(_service(request).create_run, draft)
        job = _job(request, run.run_id, dataset=True)
        return await asyncio.to_thread(_view, request, job)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, "invalid_dataset_config") from exc


@router.get("/jobs/{job_id}", response_model=DatasetJobView)
async def get_job(request: Request, job_id: str) -> DatasetJobView:
    enforce_dashboard_access(request)
    return await asyncio.to_thread(_view, request, _job(request, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=DatasetJobView)
async def cancel_job(request: Request, job_id: str) -> DatasetJobView:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    job = _job(request, job_id)
    await asyncio.to_thread(_service(request).cancel_run, job.run_id)
    return await asyncio.to_thread(_view, request, _job(request, job_id))


def _sample(request: Request, dataset_id: str, sample_id: str) -> DatasetSampleView:
    job = _job(request, dataset_id, dataset=True)
    try:
        safe_component(sample_id)
        root = _root(request, job)
        record = next((r for r in _published_records(root) if r.sample_id == sample_id), None)
        if record is None:
            raise HTTPException(404, "dataset_sample_not_found")
        observation = load_offline_observation(record)  # validates payload paths and SHA values
        depth = np.array(observation.depth_values())
        valid = depth[depth > 0]
        splits = _splits(root)
        return DatasetSampleView(
            dataset_id=dataset_id, sample_id=sample_id, group_id=record.group_id,
            status=record.status,
            split=splits.sample_assignments.get(sample_id) if splits else None,
            rgb_data_url=f"data:image/png;base64,{observation.rgb_png_base64}",
            depth_data_url=f"data:image/png;base64,{observation.depth_png_base64()}",
            depth_min_m=float(valid.min()) if len(valid) else None,
            depth_max_m=float(valid.max()) if len(valid) else None,
            valid_depth_fraction=len(valid) / len(depth),
            observation_metadata=observation.evidence(),
            rejection_reasons=[str(r) for r in record.labels.get("negative_reasons", [])],
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(409, "dataset_sample_evidence_invalid") from exc


@router.get("/{dataset_id}/samples/{sample_id}", response_model=DatasetSampleView)
async def sample(request: Request, dataset_id: str, sample_id: str) -> DatasetSampleView:
    enforce_dashboard_access(request)
    return await asyncio.to_thread(_sample, request, dataset_id, sample_id)
