"""Read-only source-bound research diagnostics; no experiment or shell entry point."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.dashboard.security import enforce_dashboard_access
from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
from cloud_edge_robot_arm.research.acceptance import CORE_METHODS, GOAL_IDS, evaluate_goals
from cloud_edge_robot_arm.research.assignments import (
    EpisodeAssignment,
    build_assignments,
    episode_record_from_payload,
    validate_formal_protocol,
)
from cloud_edge_robot_arm.research.metrics import compute_research_metrics
from cloud_edge_robot_arm.research.protocol import load_protocol

router = APIRouter(prefix="/api/v1/research", tags=["research-results"])
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}")


class ResearchRunRegistration(BaseModel):
    """Server-owned paths relative to one configured artifact root, never request data."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    runs_path: str
    protocol_path: str
    analysis_path: str


class ResearchGoalView(BaseModel):
    goal_id: str
    diagnostic_status: str
    actual_status: Literal["NOT_RUN"] = "NOT_RUN"
    evidence_scope: str
    estimate: Any = None
    reasons: list[str] = Field(default_factory=list)


class ResearchStageView(BaseModel):
    stage: str
    declared_status_counts: dict[str, int]
    source_validation_status: Literal["NOT_RUN"] = "NOT_RUN"
    accepted_count: Literal[0] = 0


class ResearchTimelineView(BaseModel):
    status: Literal["NOT_RECORDED"] = "NOT_RECORDED"
    candidate_count: int | None = None
    accepted_count: int | None = None
    started_count: int | None = None
    independent_physical_success: Literal[0] = 0
    rule_scores: dict[str, float] | None = None
    candidate_probabilities: dict[str, float] | None = None


class ResearchFailureView(BaseModel):
    assignment_id: str
    group_id: str
    method_id: str
    status: str
    reason: str | None


class ResearchMethodView(BaseModel):
    method_id: str
    assigned_denominator: int
    cloud_requests_total: int
    model_requests_by_role: dict[str, int]
    application_bytes_total: int
    penalized_duration_p95_s: float | None
    unknown_episode_rate: float | None
    unknown_condition_rate: float | None
    fallback_episode_rate: float | None
    fallback_decision_rate: float | None
    no_progress_rate: float | None
    terminal_status_counts: dict[str, int]
    provider_versions: list[dict[str, Any]] = Field(default_factory=list)
    metric_scope: Literal["DECLARED_SOURCE_BOUND_DIAGNOSTIC"] = "DECLARED_SOURCE_BOUND_DIAGNOSTIC"


class ResearchRunView(BaseModel):
    run_id: str
    status: Literal["SOFTWARE_ONLY", "NOT_RUN"] = "NOT_RUN"
    scope: Literal["SOFTWARE_ONLY", "UNVERIFIED"] = "UNVERIFIED"
    actual_research_status: Literal["NOT_RUN"] = "NOT_RUN"
    formal_accepted: Literal[False] = False
    physical_success: Literal[0] = 0
    protocol_hash: str | None = None
    selected_n: int | None = None
    assigned_denominator: int | None = None
    paired_group_denominator: int | None = None
    coverage_status: str = "INCOMPLETE"
    strata_counts_by_method: dict[str, dict[str, int]] = Field(default_factory=dict)
    terminal_status_counts: dict[str, int] = Field(default_factory=dict)
    methods: list[ResearchMethodView] = Field(default_factory=list)
    goals: list[ResearchGoalView] = Field(default_factory=list)
    effects: dict[str, Any] = Field(default_factory=dict)
    primary_family: dict[str, Any] = Field(default_factory=dict)
    stages: list[ResearchStageView] = Field(default_factory=list)
    timeline: ResearchTimelineView = Field(default_factory=ResearchTimelineView)
    failures: list[ResearchFailureView] = Field(default_factory=list)
    source_missing: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class ResearchRunList(BaseModel):
    runs: list[ResearchRunView]
    actual_research_status: Literal["NOT_RUN"] = "NOT_RUN"
    reasons: list[str] = Field(default_factory=list)


def _authorize(request: Request) -> None:
    enforce_dashboard_access(request)
    if request.query_params:
        raise HTTPException(422, "research_query_parameters_not_supported")


def _registry(request: Request) -> Mapping[str, ResearchRunRegistration]:
    registry = getattr(request.app.state, "research_runs_registry", {})
    if not isinstance(registry, Mapping):
        raise HTTPException(409, "research_registry_invalid")
    return registry


def _resolve(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ValueError("research path must be server-owned and relative")
    if root.absolute() != root.resolve():
        raise ValueError("research artifact root cannot follow symlinks")
    target = root / path
    cursor = root
    for part in path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("research artifact symlinks are forbidden")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("research artifact escapes configured root")
    return target


def _missing(run_id: str, missing: list[str]) -> ResearchRunView:
    return ResearchRunView(
        run_id=run_id,
        source_missing=missing,
        reasons=["required research artifacts are not available; no actual research acceptance"],
        goals=[
            ResearchGoalView(
                goal_id=goal,
                diagnostic_status="NOT_RUN",
                evidence_scope="UNVERIFIED",
                reasons=["required source missing"],
            )
            for goal in GOAL_IDS
        ],
    )


def _load_view(request: Request, run_id: str) -> ResearchRunView:
    registry = _registry(request)
    if _RUN_ID.fullmatch(run_id) is None or run_id not in registry:
        raise HTTPException(404, "research_run_not_found")
    try:
        registered = registry[run_id]
        config = (
            registered
            if isinstance(registered, ResearchRunRegistration)
            else ResearchRunRegistration.model_validate(registered)
        )
        configured_root = getattr(request.app.state, "research_artifact_root", None)
        if configured_root is None:
            return _missing(run_id, ["configured_artifact_root"])
        root = Path(configured_root).absolute()
        paths = {
            "protocol": _resolve(root, config.protocol_path + "/protocol.json"),
            "assignments": _resolve(root, config.runs_path + "/assignments.json"),
            "records": _resolve(root, config.runs_path + "/records.jsonl"),
            "pools": _resolve(root, config.runs_path + "/pools.json"),
            "report": _resolve(root, config.analysis_path + "/report.json"),
            "metrics": _resolve(root, config.analysis_path + "/metrics.json"),
            "goals": _resolve(root, config.analysis_path + "/goal_verdicts.json"),
        }
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            return _missing(run_id, missing)
        source_bytes = {name: path.read_bytes() for name, path in paths.items()}
        fingerprints = {name: hashlib.sha256(raw).hexdigest() for name, raw in source_bytes.items()}
        cache = getattr(request.app.state, "research_results_cache", {})
        fingerprint = content_digest({"paths": config.model_dump(), "hashes": fingerprints})
        cached = cache.get(run_id)
        if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == fingerprint:
            cached_view = cached[1]
            if isinstance(cached_view, ResearchRunView):
                return cached_view.model_copy(deep=True)
        frozen = load_protocol(paths["protocol"].parent)
        validate_formal_protocol(frozen)
        report = json.loads(source_bytes["report"])
        metrics = json.loads(source_bytes["metrics"])
        goals = json.loads(source_bytes["goals"])
        if (
            not isinstance(report, Mapping)
            or not isinstance(metrics, Mapping)
            or (not isinstance(goals, list) or not isinstance(report.get("source_hashes"), Mapping))
        ):
            raise ValueError("research report/metrics/goals/source hashes have invalid shapes")
        if report.get("schema_version") != "ced.research-analysis.v1" or (
            metrics.get("schema_version") != "ced.research-metrics.v1"
            or report.get("formal_accepted") is not False
            or report.get("physical_success") != 0
        ):
            raise ValueError("unsupported research report or unverified acceptance declaration")
        if any(
            report.get("source_hashes", {}).get(name) != fingerprints[name]
            for name in ("protocol", "assignments", "records", "pools")
        ):
            raise ValueError("research report input source hash mismatch")
        software_only = report.get("scope") == "SOFTWARE_ONLY"
        if report.get("scope") not in {"SOFTWARE_ONLY", "UNVERIFIED"}:
            raise ValueError("research report scope unsupported")
        manifest = json.loads(source_bytes["assignments"])
        if not isinstance(manifest, dict) or (
            not isinstance(manifest.get("assignments"), list)
            or any(not isinstance(raw, Mapping) for raw in manifest["assignments"])
        ):
            raise ValueError("research assignment manifest must contain an array of objects")
        expected_hash = manifest.pop("content_hash", None)
        if manifest.get("schema_version") != "ced.assignments.v1" or (
            expected_hash != content_digest(manifest)
            or manifest.get("protocol_hash") != frozen.content_hash
        ):
            raise ValueError("research assignment hash/protocol mismatch")
        assignments = [EpisodeAssignment(**raw) for raw in manifest["assignments"]]
        pools = json.loads(source_bytes["pools"])
        if not isinstance(pools, Mapping) or (
            not isinstance(pools.get("formal"), list)
            or any(not isinstance(raw, Mapping) for raw in pools["formal"])
        ):
            raise ValueError("research formal pool must contain an array of scene objects")
        rebuilt = build_assignments(frozen, CORE_METHODS, scene_pool=pools["formal"])
        if assignments != rebuilt:
            raise ValueError("research coverage differs from all frozen methods/scenes/strata")
        raw_rows = [json.loads(line) for line in source_bytes["records"].splitlines()]
        if any(not isinstance(raw, Mapping) or (
            not isinstance(raw.get("assignment"), Mapping)
        ) for raw in raw_rows):
            raise ValueError("research record lines must contain assignment objects")
        rows = [episode_record_from_payload(raw, protocol=frozen) for raw in raw_rows]
        actual = {row.assignment.assignment_id: row for row in rows}
        if (
            len(actual) != len(rows)
            or set(actual) != {row.assignment_id for row in rebuilt}
            or any(actual[row.assignment_id].assignment != row for row in rebuilt)
        ):
            raise ValueError("research source must retain every blocked/failed original assignment")
        recomputed = {
            **compute_research_metrics(rows, (), (), software_only=software_only),
            "coverage_status": "COMPLETE",
            "coverage_assignment_denominator": len(rebuilt),
            "coverage_group_denominator": frozen.spec.selected_n,
            "coverage_methods": list(CORE_METHODS),
        }
        recomputed_goals = [
            asdict(value)
            for value in evaluate_goals(recomputed, frozen, software_only=software_only)
        ]
        if canonical_json(metrics) != canonical_json(recomputed) or (
            canonical_json(goals) != canonical_json(recomputed_goals)
            or report.get("goal_verdicts") != goals
            or report.get("status") != ("SOFTWARE_ONLY" if software_only else "NOT_RUN")
        ):
            raise ValueError("research summaries differ from source-bound numeric rebuild")
        method_views = [
            ResearchMethodView(
                method_id=method,
                **{
                    name: values.get(name)
                    for name in ResearchMethodView.model_fields
                    if name not in {"method_id", "metric_scope"}
                },
            )
            for method, values in metrics["methods"].items()
        ]
        stage_counts: dict[str, Counter[str]] = {}
        for row in rows:
            for stage in row.provenance.stages:
                stage_counts.setdefault(stage.stage, Counter())[str(stage.status)] += 1
        strata = {
            method: dict(Counter(row.stratum_id for row in rebuilt if row.method_id == method))
            for method in CORE_METHODS
        }
        view = ResearchRunView(
            run_id=run_id,
            status=report["status"],
            scope=report["scope"],
            protocol_hash=frozen.content_hash,
            selected_n=frozen.spec.selected_n,
            assigned_denominator=len(rows),
            paired_group_denominator=frozen.spec.selected_n,
            coverage_status="COMPLETE",
            strata_counts_by_method=strata,
            terminal_status_counts=dict(Counter(row.run_status for row in rows)),
            methods=method_views,
            goals=[
                ResearchGoalView(
                    goal_id=value["goal_id"],
                    diagnostic_status=value["status"],
                    evidence_scope=value["evidence_scope"],
                    estimate=value["estimate"],
                    reasons=list(value["reasons"]),
                )
                for value in goals
            ],
            effects=metrics["effects"],
            primary_family=metrics["primary_family"],
            stages=[
                ResearchStageView(stage=stage, declared_status_counts=dict(counts))
                for stage, counts in sorted(stage_counts.items())
            ],
            failures=[
                ResearchFailureView(
                    assignment_id=row.assignment.assignment_id,
                    group_id=row.assignment.group_id,
                    method_id=row.assignment.method_id,
                    status=row.run_status,
                    reason=row.outcome.terminal_reason or row.outcome.failure_reason,
                )
                for row in rows
                if not row.accepted_task_success
            ],
            reasons=[
                "independent raw physical source verifier is not integrated",
                "condition UNKNOWN and decision fallback need source-qualified round counts",
                "candidate/accepted/started timeline and rule probabilities are not recorded",
            ],
        )
        cache[run_id] = (fingerprint, view.model_copy(deep=True))
        request.app.state.research_results_cache = cache
        return view
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(409, "research_artifact_invalid") from error


@router.get("/runs", response_model=ResearchRunList)
def list_research_runs(request: Request) -> ResearchRunList:
    _authorize(request)
    return ResearchRunList(
        runs=[_load_view(request, run_id) for run_id in sorted(_registry(request))],
        reasons=["actual research evidence remains NOT_RUN"],
    )


@router.get("/runs/{run_id}/evidence", response_model=ResearchRunView)
def get_research_evidence(request: Request, run_id: str) -> ResearchRunView:
    _authorize(request)
    return _load_view(request, run_id)


@router.get("/runs/{run_id}/export", response_model=ResearchRunView)
def export_research_evidence(request: Request, run_id: str) -> JSONResponse:
    _authorize(request)
    view = _load_view(request, run_id)
    return JSONResponse(
        view.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{run_id}.research.json"'},
    )
