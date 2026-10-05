"""Source-bound v2 resource planning; forecasts never accept physical research."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.cost_ledger import RequestCost
from cloud_edge_robot_arm.research.pilot import derive_tcap, stage_source_paths
from cloud_edge_robot_arm.research.protocol import file_hash

METHOD_IDS = ("JOINT", "B0", "B1", "B2", "NO_UNCERTAINTY", "NO_TIME_VALIDITY", "NO_LOCAL_REPAIR")
AUXILIARY_PHASES = (
    "g3_rules",
    "source_verification",
    "reproduction",
    "calibration",
    "data_source",
    "source_generation",
)
QUANTITIES = (
    "wall_s",
    "storage_bytes",
    "cloud_model_requests",
    "application_bytes",
    "monetary_cost",
)
CEILING_KEYS = ("wall_s", "storage_bytes", "cloud_model_requests", "monetary_cost")
RESERVE_RULE: dict[str, Any] = {
    "schema_version": "ced.resource-reserve.v1",
    "fraction": 0.2,
    "scope": "future_reference_terms",
    "kind": "PLANNING_RULE",
}
LOCAL_OPERATIONS = {
    "g3_rules": ("src/cloud_edge_robot_arm/edge/evidence/opportunities.py", "replay_opportunities"),
    "source_verification": (
        "src/cloud_edge_robot_arm/research/protocol_evidence.py",
        "verify_protocol_evidence",
    ),
    "reproduction": ("src/cloud_edge_robot_arm/research/reproducibility.py", "rebuild_analysis"),
    "calibration": ("src/cloud_edge_robot_arm/vision/risk/calibration.py", "calibrate_risk"),
    "data_source": ("src/cloud_edge_robot_arm/datasets/rgbd/generator.py", "generate_dataset"),
    "source_generation": (
        "src/cloud_edge_robot_arm/research/protocol_evidence.py",
        "prepare_protocol_evidence",
    ),
}


def _number(value: Any, *, integer: bool = False) -> float | int:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise ValueError("resource quantities require finite nonnegative numbers")
    if integer and type(value) is not int:
        raise ValueError("resource counts and actual bytes require integers")
    return cast(float | int, value)


def _amount(value: Mapping[str, Any]) -> dict[str, float | int | None]:
    if set(value) != set(QUANTITIES):
        raise ValueError("resource amount requires all quantities, including unknown fees")
    return {
        key: None
        if value[key] is None
        else _number(
            value[key],
            integer=key in {"storage_bytes", "cloud_model_requests", "application_bytes"},
        )
        for key in QUANTITIES
    }


def _sum(values: Sequence[Mapping[str, Any]]) -> dict[str, float | int | None]:
    return {
        key: None if any(row[key] is None for row in values) else sum(row[key] for row in values)
        for key in QUANTITIES
    }


def _scale(value: Mapping[str, Any], count: float) -> dict[str, float | int | None]:
    return {
        key: None
        if value[key] is None
        else (
            math.ceil(value[key] * count)
            if key in {"storage_bytes", "cloud_model_requests", "application_bytes"}
            else value[key] * count
        )
        for key in QUANTITIES
    }


def estimate_resource_terms(
    measurements: Mapping[str, Any],
    *,
    formal_n: int | None = None,
    declared_ceilings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure SOFTWARE_ONLY math; no caller-supplied measurements acquire source acceptance."""
    if formal_n is not None and formal_n not in (600, 1200, 1800, 2400):
        raise ValueError("formal N must be a fixed candidate and cannot be selected here")
    walls = measurements["successful_wall_s"]
    if not isinstance(walls, list) or not walls:
        raise ValueError("resource forecasts require independently successful complete paths")
    if any(_number(value) <= 0 for value in walls):
        raise ValueError("successful complete-path wall time must be positive")
    names = (
        "successful_storage_bytes",
        "successful_requests",
        "successful_application_bytes",
        "successful_monetary_costs",
    )
    if any(len(measurements[name]) != len(walls) for name in names):
        raise ValueError("successful complete-path costs must retain every successful original")
    tcap = derive_tcap(walls)
    unit: dict[str, Any] = {"wall_s": tcap}
    for key, name in zip(QUANTITIES[1:], names, strict=True):
        values = measurements[name]
        if any(value is None for value in values):
            unit[key] = None
        else:
            numbers = [_number(value, integer=key != "monetary_cost") for value in values]
            p99 = float(np.quantile(numbers, 0.99))
            unit[key] = p99 if key == "monetary_cost" else math.ceil(p99)
    unknown = []
    if not measurements.get("initialization_in_complete_path"):
        unknown.append("initialization")
    if any(value is None for value in unit.values()):
        unknown.append("successful_complete_path_costs")
    auxiliary = measurements["auxiliary"]
    terms: dict[str, Any] = {
        "initialization": {
            "included_in": "complete_success",
            "additional_amount": dict.fromkeys(QUANTITIES, 0),
        },
        "complete_success": {
            "successful_originals": len(walls),
            "amount": unit,
            "kind": "B0_CONDITIONAL_REFERENCE; wall uses frozen Tcap",
        },
        "selection_sunk": {"episodes": 480, "amount": _amount(measurements["selection_sunk"])},
        "foundation_sunk": {"episodes": 120, "amount": _amount(measurements["foundation_sunk"])},
        "power": {
            "episodes": 120 * len(METHOD_IDS),
            "methods": list(METHOD_IDS),
            "amount": _scale(unit, 120 * len(METHOD_IDS)),
        },
        "formal_chosen": None
        if formal_n is None
        else {
            "episodes": formal_n * len(METHOD_IDS),
            "amount": _scale(unit, formal_n * len(METHOD_IDS)),
        },
        "formal_worst": {
            "episodes": 2400 * len(METHOD_IDS),
            "amount": _scale(unit, 2400 * len(METHOD_IDS)),
        },
        "g4": {
            "groups": 200,
            "episodes": 400,
            "amount": {**_scale(unit, 400), "wall_s": 400 * 60},
            "wall_basis": "fixed Rcap60; other costs remain B0 conditional references",
        },
    }
    count = measurements["opportunity_count"]
    if type(count) is not int or count <= 0:
        raise ValueError("all fixed opportunities/actions require an exact positive count")
    for phase in AUXILIARY_PHASES:
        if phase not in auxiliary:
            unknown.append(phase)
            measured = dict.fromkeys(QUANTITIES)
        else:
            measured = _amount(auxiliary[phase])
            if any(v is None for v in measured.values()):
                unknown.append(phase)
        terms[phase] = {"amount": measured, "kind": "MEASURED_FULL_PHASE_REFERENCE"}
    terms["g3_rules"].update(opportunities=count, methods=["JOINT", "B3"], rule_passes=count * 2)
    disk = measurements["current_disk"]
    current_bytes = _number(disk["total_bytes"], integer=True)
    if any(
        terms[name]["amount"][key] is None
        for name in ("selection_sunk", "foundation_sunk")
        for key in QUANTITIES
    ):
        unknown.append("sunk_costs")
    totals: dict[str, Any] = {}
    checks: dict[str, Any] = {}
    for scenario in ("chosen", "worst"):
        formal = terms["formal_" + scenario]
        if formal is None:
            totals[scenario] = checks[scenario] = None
            continue
        future = _sum(
            [
                terms["power"]["amount"],
                formal["amount"],
                terms["g4"]["amount"],
                *(terms[name]["amount"] for name in AUXILIARY_PHASES),
            ]
        )
        reserve = _scale(future, RESERVE_RULE["fraction"])
        terms["rerun_reserve_" + scenario] = {"amount": reserve, "rule": RESERVE_RULE}
        sunk = _sum([terms["selection_sunk"]["amount"], terms["foundation_sunk"]["amount"]])
        sunk["storage_bytes"] = (
            current_bytes  # The complete current tree already contains sunk files.
        )
        totals[scenario] = _sum([sunk, future, reserve])
    if declared_ceilings is not None:
        if set(declared_ceilings) != set(CEILING_KEYS):
            raise ValueError("declare actual wall/storage/request/monetary limits explicitly")
        limits = {
            key: _number(
                declared_ceilings[key], integer=key in {"storage_bytes", "cloud_model_requests"}
            )
            for key in CEILING_KEYS
        }
        for scenario, total in totals.items():
            checks[scenario] = (
                None
                if total is None
                else {
                    key: None if total[key] is None else total[key] <= limits[key]
                    for key in CEILING_KEYS
                }
            )
    else:
        limits = None
    status = (
        "UNAVAILABLE"
        if limits is None
        else "INCOMPLETE"
        if unknown
        else (
            "WITHIN_DECLARED_CEILINGS"
            if all(checks["worst"].values())
            else "EXCEEDS_DECLARED_CEILINGS"
        )
    )
    return {
        "schema_version": "ced.resource-plan.v1",
        "scope": "SOFTWARE_ONLY",
        "available": False,
        "actual_research_status": "NOT_RUN",
        "physical_acceptance": False,
        "budget_status": status,
        "formal_n": formal_n,
        "methods": list(METHOD_IDS),
        "successful_p99_wall_s": float(np.quantile(walls, 0.99)),
        "tcap_s": tcap,
        "rcap_s": 60,
        "terms": terms,
        "reserve_rule": RESERVE_RULE,
        "current_disk": dict(disk),
        "totals": totals,
        "declared_ceilings": limits,
        "ceiling_checks": checks,
        "unknown_components": sorted(set(unknown)),
        "assumptions": [
            "Conditional B0-based cost references do not guarantee method upper bounds.",
            "Forecasts include all assigned formal/method episodes and failed penalties.",
            "Current raw/archive storage is enumerated, not inferred from failed means.",
        ],
    }


def compile_resource_plan(
    foundation: Path,
    *,
    formal_n: int | None = None,
    declared_ceilings: Mapping[str, Any] | None = None,
    auxiliary_cost_evidence: Path | None = None,
) -> dict[str, Any]:
    """Recompute actual raw inputs; unavailable sources cannot become a resource acceptance."""
    from cloud_edge_robot_arm.research.freeze_evidence import audit_ced_pilot_stage

    result: dict[str, Any] = {
        "schema_version": "ced.resource-plan.v1",
        "available": False,
        "scope": "SOURCE_RESOURCE_DIAGNOSTIC",
        "budget_status": "UNAVAILABLE",
        "actual_research_status": "NOT_RUN",
        "physical_acceptance": False,
        "errors": [],
    }
    audit = audit_ced_pilot_stage(foundation, "foundation")
    if not audit["available"]:
        result["errors"] = [
            "independent successful foundation sources unavailable",
            *audit["errors"],
        ]
        return result
    # The source reader is implemented below; no summary/YAML acceptance flag is consumed.
    try:
        return _compile_sources(
            foundation, audit, formal_n, declared_ceilings, auxiliary_cost_evidence
        )
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        result["errors"] = [f"resource source unavailable: {type(error).__name__}: {error}"]
        return result


def _path(root: Path, relative: str) -> Path:
    from cloud_edge_robot_arm.research.freeze_evidence import _inside

    return _inside(root, relative)


def _json(root: Path, relative: str) -> Any:
    return json.loads(_path(root, relative).read_bytes())


def _tree_sizes(root: Path) -> dict[str, Any]:
    root = root.absolute()
    if root.resolve() != root or root.is_symlink() or not root.is_dir():
        raise ValueError("resource source tree must be a real non-symlink directory")
    inventory, hashes = {}, {}
    raw_bytes = archive_bytes = allocated_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("resource source tree cannot contain symlinks")
        if not path.is_file() or path == root / "resource-plan.json":
            continue
        relative = str(path.relative_to(root))
        size = path.stat().st_size
        inventory[relative] = size
        hashes[relative] = file_hash(path)
        allocated_bytes += path.stat().st_blocks * 512
        parts = path.relative_to(root).parts
        if "source" in parts or path.suffix in {".zip", ".tar"}:
            archive_bytes += size
        elif set(parts) & {"raw", "raw-frames", "cases", "frames", "supervision-frames", "wire"}:
            raw_bytes += size
    return {
        "total_bytes": sum(inventory.values()),
        "raw_bytes": raw_bytes,
        "archive_bytes": archive_bytes,
        "allocated_bytes": allocated_bytes,
        "file_sizes": inventory,
        "file_hashes": hashes,
        "scope": "whole current tree; own resource-plan.json receipt excluded",
    }


def _read_request_costs(
    root: Path,
    requests_path: str,
    wire_path: str,
    *,
    zero_request_proven: bool = False,
    require_request_ids: bool = True,
    expected_provider_version: str | None = None,
) -> dict[str, Any]:
    payload = _json(root, requests_path)
    if isinstance(payload, dict):
        payload = payload["requests"]
    if not isinstance(payload, list):
        raise ValueError("raw request ledger must retain all original rows")
    requests = [RequestCost.model_validate(row) for row in payload]
    if len({row.request_id for row in requests}) != len(requests) or any(
        row.status == "IN_FLIGHT" for row in requests
    ):
        raise ValueError("request costs require unique fully settled original attempts")
    sent = [row for row in requests if row.sent_at is not None]
    if expected_provider_version is not None and any(
        row.provider_location == "REMOTE_SERVICE"
        and row.provider_version != expected_provider_version
        for row in sent
    ):
        raise ValueError("actual cloud cost provider version differs from the frozen role")
    wire = _json(root, wire_path)
    if not isinstance(wire, list) or len(wire) != len(sent):
        raise ValueError("complete actual request/wire attempt denominator differs")
    by_id = {row.request_id: row for row in sent}
    seen, actual_lengths = set(), []
    for entry in wire:
        if not isinstance(entry, dict):
            raise ValueError("actual wire index rows must be objects")
        request = _path(root, entry["request_path"]).read_bytes()
        response_path = entry.get("response_path")
        if response_path:
            if entry.get("response_present", True) is not True:
                raise ValueError("response presence contradicts its original payload")
            response = _path(root, response_path).read_bytes()
            if hashlib.sha256(response).hexdigest() != entry.get("response_sha256"):
                raise ValueError("original response wire hash differs, including empty payloads")
        else:
            if entry.get("response_present") is not False or (
                entry.get("response_sha256") is not None
            ):
                raise ValueError("absent response requires explicit absence and no payload hash")
            response = b""
        if hashlib.sha256(request).hexdigest() != entry["request_sha256"] or (
            response_path is None and entry.get("serialized_received_bytes", 0) != 0
        ):
            raise ValueError("original request/response wire hash differs")
        actual_lengths.append((len(request), len(response)))
        if require_request_ids:
            identity = entry.get("request_id")
            if identity not in by_id or identity in seen:
                raise ValueError("actual request IDs do not join each original wire attempt")
            seen.add(identity)
            row = by_id[identity]
            if not response_path and row.status == "SUCCESS":
                raise ValueError("successful request cannot have an absent original response")
            if (row.serialized_sent_bytes, row.serialized_received_bytes) != actual_lengths[-1]:
                raise ValueError("actual original wire lengths differ from request costs")
    if sorted(actual_lengths) != sorted(
        (row.serialized_sent_bytes, row.serialized_received_bytes) for row in sent
    ):
        raise ValueError("actual serialized wire bytes differ from full settled request ledger")
    fees = [row.monetary_cost for row in sent]
    proven = bool(sent) or zero_request_proven
    declared_money = (
        None
        if not proven or any(f is None for f in fees)
        else sum(fee for fee in fees if fee is not None)
    )
    remote = any(row.provider_location == "REMOTE_SERVICE" for row in sent)
    # The transport emits no independently measured remote charge. Original
    # ledger numbers remain diagnostics; editing them cannot certify billing.
    verified_money = None if remote else declared_money
    billing_status = (
        "REMOTE_BILLING_UNAVAILABLE"
        if remote
        else "UNKNOWN"
        if declared_money is None
        else "NO_MODEL_REQUESTS_PROVEN"
        if not sent
        else "LOCAL_LEDGER_ONLY"
    )
    return {
        "model_requests": len(sent) if proven else None,
        "cloud_model_requests": sum(r.provider_location == "REMOTE_SERVICE" for r in sent)
        if proven
        else None,
        "local_model_requests": sum(r.provider_location == "LOCAL_HOST" for r in sent)
        if proven
        else None,
        "requests_by_role": dict(Counter(r.model_role for r in sent)),
        "application_bytes": sum(a + b for a, b in actual_lengths),
        "monetary_cost": verified_money,
        "declared_monetary_cost": declared_money,
        "declared_monetary_costs_by_request": {
            row.request_id: row.monetary_cost for row in requests
        },
        "billing_status": billing_status,
        "original_attempts": len(requests),
        "source_bound_wire_attempts": len(sent),
    }


def _local_request_proof(root: Path, record: Mapping[str, Any], opportunity_ids: list[str]) -> bool:
    proof = record["local_execution_proof"]
    if proof is None:
        return False
    if not isinstance(proof, dict) or proof.get("schema_version") != "ced.local-cost-proof.v1":
        raise ValueError("zero-model costs require typed original closed local execution proof")
    events = _json(root, proof["events_path"])
    if (
        not isinstance(events, list)
        or len(events) < 3
        or (
            events[0].get("event") != "START"
            or events[-1].get("event") != "FINISH"
            or any(event.get("run_id") != record["run_id"] for event in events)
        )
    ):
        raise ValueError("local request proof must include original whole execution boundaries")
    if any(event.get("event") not in {"START", "FINISH", "LOCAL_OPERATION"} for event in events):
        raise ValueError("local request proof contains an unaccounted model/network operation")
    clock = _json(root, record["clock_path"])
    if events[0] != clock[0] or events[-1] != clock[-1]:
        raise ValueError("local no-model execution proof must join the exact whole raw clock span")
    operations = events[1:-1]
    expected_path, expected_function = LOCAL_OPERATIONS[record["phase"]]
    if any(
        operation["phase"] != record["phase"]
        or operation["source_path"] not in record["source_hashes"]
        or operation["source_sha256"] != record["source_hashes"][operation["source_path"]]
        or operation["source_path"] != expected_path
        or operation.get("function") != expected_function
        or not clock[0]["monotonic_s"]
        <= _number(operation["monotonic_s"])
        <= clock[-1]["monotonic_s"]
        for operation in operations
    ):
        raise ValueError("local operation trace does not bind the exact actual source path")
    if record["phase"] == "g3_rules":
        from dataclasses import asdict

        from scripts.run_rgbd_gate_replay import _opportunity

        from cloud_edge_robot_arm.research.runner import run_gate_replay

        payload = _json(root, proof["opportunities_path"])
        raw = payload["opportunities"]
        if payload.get("schema_version") != "ced.opportunity-set.v1" or (
            payload["content_hash"] != content_digest(raw)
        ):
            raise ValueError("local replay proof requires untouched fixed opportunity payloads")
        values = [_opportunity(row) for row in raw]
        if sorted(v.opportunity_id for v in values) != sorted(opportunity_ids):
            raise ValueError("zero-model replay proof omitted an assigned fixed opportunity")
        original = _json(root, proof["records_path"])
        expected = [
            asdict(row) for method in ("JOINT", "B3") for row in run_gate_replay(values, method)
        ]
        if content_digest(original) != content_digest(expected):
            raise ValueError(
                "local JOINT/B3 rule result does not reproduce from fixed online facts"
            )
        pairs = [(row["opportunity_id"], row["method_id"]) for row in operations]
        if Counter(pairs) != Counter(
            (identity, method) for identity in opportunity_ids for method in ("JOINT", "B3")
        ):
            raise ValueError("closed local trace does not cover every original JOINT/B3 rule pass")
    else:
        # These source-qualified cost operations never declare physical acceptance.
        # The complete raw trace and current archived implementation bind the no-model path.
        if any(operation.get("operation") != "LOCAL_SOURCE_PROCESSING" for operation in operations):
            raise ValueError("unrecognized local source processing cost proof")
        for operation in operations:
            references = operation["input_refs"]
            if (
                not isinstance(references, dict)
                or not references
                or any(
                    file_hash(_path(root, name)) != digest for name, digest in references.items()
                )
            ):
                raise ValueError("local source operation raw input references are unavailable")
    return True


def _read_resource_phase(
    root: Path,
    phase: str,
    role_bundle_hash: str,
    opportunity_ids: list[str],
    *,
    expected_provider_version: str | None = None,
) -> dict[str, Any]:
    record = _json(root, "phase.json")
    if not isinstance(record, dict) or (
        record.get("schema_version") != "ced.resource-phase.v1"
        or record.get("scope") != "REAL_RUNTIME"
        or record.get("phase") != phase
        or record.get("role_bundle_hash") != role_bundle_hash
        or not isinstance(record.get("run_id"), str)
        or not record["run_id"]
    ):
        raise ValueError("resource phase requires exact actual role/source/phase identities")
    hashes = record["source_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != {str(path) for path in stage_source_paths()}:
        raise ValueError("resource phase cannot narrow the actual implementation source inventory")
    for name, expected in hashes.items():
        if (
            file_hash(Path(name)) != expected
            or file_hash(_path(root, "source/" + name)) != expected
        ):
            raise ValueError("resource phase current/archive source hash drift")
    clock = _json(root, record["clock_path"])
    if (
        not isinstance(clock, list)
        or len(clock) != 2
        or (
            [row["event"] for row in clock] != ["START", "FINISH"]
            or any(row["run_id"] != record["run_id"] for row in clock)
        )
    ):
        raise ValueError("resource phase requires original start-to-finish raw clock records")
    start, finish = (_number(row["monotonic_s"]) for row in clock)
    if finish <= start:
        raise ValueError("resource phase raw wall clock interval is invalid")
    coverage = record["coverage"]
    if phase in {"g3_rules", "source_verification", "reproduction"}:
        if sorted(coverage["opportunity_ids"]) != sorted(opportunity_ids):
            raise ValueError("resource phase must retain all fixed opportunities and actions")
        if phase == "g3_rules" and coverage.get("methods") != ["JOINT", "B3"]:
            raise ValueError("G3 requires both JOINT and B3 rule passes")
    elif (
        not isinstance(coverage.get("group_ids"), list)
        or not coverage["group_ids"]
        or (len(set(coverage["group_ids"])) != len(coverage["group_ids"]))
    ):
        raise ValueError("source/calibration/data cost coverage requires original group identities")
    proven = _local_request_proof(root, record, opportunity_ids)
    costs = _read_request_costs(
        root,
        record["requests_path"],
        record["wire_path"],
        zero_request_proven=proven,
        expected_provider_version=expected_provider_version,
    )
    if proven and costs["source_bound_wire_attempts"]:
        raise ValueError("no-model local proof conflicts with actual recorded model requests")
    size = _tree_sizes(root)
    return {
        "wall_s": finish - start,
        "storage_bytes": size["total_bytes"],
        "cloud_model_requests": costs["cloud_model_requests"],
        "application_bytes": costs["application_bytes"],
        "monetary_cost": costs["monetary_cost"],
        "coverage": coverage,
        "request_costs": costs,
        "disk": size,
    }


def _case_measurement(
    root: Path, row: Mapping[str, Any], *, expected_provider_version: str
) -> dict[str, Any]:
    case = _path(root, "cases/" + row["assignment_id"])
    # Strict stage audit and the collector bind every original attempt ID and role.
    # The resource reader independently repeats the exact per-attempt wire join.
    costs = _read_request_costs(
        case,
        "costs.json",
        "wire-index.json",
        require_request_ids=True,
        expected_provider_version=expected_provider_version,
    )
    return {
        "wall_s": _number(row["wall_duration_s"]),
        "storage_bytes": _tree_sizes(case)["total_bytes"],
        "cloud_model_requests": costs["cloud_model_requests"],
        "application_bytes": costs["application_bytes"],
        "monetary_cost": costs["monetary_cost"],
        "requests_by_role": costs["requests_by_role"],
        "request_costs": costs,
    }


def _compile_sources(
    foundation: Path,
    audit: Mapping[str, Any],
    formal_n: int | None,
    ceilings: Mapping[str, Any] | None,
    auxiliary: Path | None,
) -> dict[str, Any]:
    from cloud_edge_robot_arm.research.freeze_evidence import audit_ced_pilot_stage

    selection_root = _path(foundation, "selection-evidence")
    selection = audit_ced_pilot_stage(selection_root, "selection")
    if not selection["available"] or any(
        audit[name] != selection[name]
        for name in ("pools", "role_bundle_hash", "selected_period_s")
    ):
        raise ValueError("resource selection/foundation roles, pools and selected period differ")
    if (
        len(audit["cases"]) != 120
        or len(selection["cases"]) != 480
        or any(row.get("scope") != "REAL_RUNTIME" for row in [*audit["cases"], *selection["cases"]])
    ):
        raise ValueError(
            "resource planning retains all real selection/foundation original outcomes"
        )
    success_rows = [row for row in audit["cases"] if row["success"] is True]
    if not success_rows:
        raise ValueError("no independently successful complete B0 path; failed means are forbidden")
    provider = audit["cloud_model_snapshot_hash"]
    if provider != selection["cloud_model_snapshot_hash"]:
        raise ValueError("selection/foundation actual model cost versions differ")
    foundation_costs = [
        _case_measurement(foundation, row, expected_provider_version=provider)
        for row in audit["cases"]
    ]
    selection_costs = [
        _case_measurement(selection_root, row, expected_provider_version=provider)
        for row in selection["cases"]
    ]
    successful = [
        measured
        for row, measured in zip(audit["cases"], foundation_costs, strict=True)
        if row["success"] is True
    ]
    disk = _tree_sizes(foundation)
    opportunities = _json(foundation, "protocol-evidence/opportunities.json")
    if not isinstance(opportunities, list) or not opportunities:
        raise ValueError("budget requires the whole fixed opportunity source set")
    identities = [row["seed"]["opportunity_id"] for row in opportunities]
    if len(set(identities)) != len(identities):
        raise ValueError("fixed resource opportunity identities must remain unique")
    auxiliary_costs, auxiliary_details, auxiliary_errors = {}, {}, {}
    all_groups = {row["scene"]["group_id"] for pool in audit["pools"].values() for row in pool}
    if auxiliary is not None:
        auxiliary = auxiliary.absolute()
        for phase in AUXILIARY_PHASES:
            directory = _path(auxiliary, phase)
            if not directory.is_dir():
                continue
            try:
                measured = _read_resource_phase(
                    directory,
                    phase,
                    audit["role_bundle_hash"],
                    identities,
                    expected_provider_version=provider,
                )
                if phase in {"calibration", "data_source"} and (
                    set(measured["coverage"]["group_ids"]) & all_groups
                ):
                    raise ValueError(
                        "calibration/development source costs reuse a frozen research pool"
                    )
                auxiliary_costs[phase] = {key: measured[key] for key in QUANTITIES}
                auxiliary_details[phase] = measured
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                auxiliary_errors[phase] = f"{type(error).__name__}: {error}"
        if not auxiliary.is_relative_to(foundation.absolute()):
            extra = _tree_sizes(auxiliary)
            for key in ("total_bytes", "raw_bytes", "archive_bytes", "allocated_bytes"):
                disk[key] += extra[key]
            disk["external_auxiliary_disk"] = extra
    data = {
        "successful_wall_s": [row["wall_s"] for row in successful],
        "successful_storage_bytes": [row["storage_bytes"] for row in successful],
        "successful_requests": [row["cloud_model_requests"] for row in successful],
        "successful_application_bytes": [row["application_bytes"] for row in successful],
        "successful_monetary_costs": [row["monetary_cost"] for row in successful],
        "selection_sunk": _sum(selection_costs),
        "foundation_sunk": _sum(foundation_costs),
        "current_disk": disk,
        "auxiliary": auxiliary_costs,
        "opportunity_count": len(identities),
        "initialization_in_complete_path": True,
    }
    plan = estimate_resource_terms(data, formal_n=formal_n, declared_ceilings=ceilings)
    plan.update(
        scope="SOURCE_RESOURCE_DIAGNOSTIC",
        available=plan["budget_status"] == "WITHIN_DECLARED_CEILINGS",
        role_bundle_hash=audit["role_bundle_hash"],
        selection_evidence_hash=selection["evidence_hash"],
        foundation_evidence_hash=audit["evidence_hash"],
        original_denominators={"selection": 480, "foundation": 120},
        successful_originals=len(successful),
        auxiliary_details=auxiliary_details,
        auxiliary_errors=auxiliary_errors,
        billing_diagnostics={
            "scope": "DECLARED_LEDGER_ONLY",
            "independently_verified_remote_billing": False,
            **{
                stage: [
                    {
                        "assignment_id": original["assignment_id"],
                        "declared_monetary_cost": measured.get("request_costs", {}).get(
                            "declared_monetary_cost"
                        ),
                        "declared_monetary_costs_by_request": measured.get("request_costs", {}).get(
                            "declared_monetary_costs_by_request", {}
                        ),
                        "billing_status": measured.get("request_costs", {}).get(
                            "billing_status", "NOT_RECORDED"
                        ),
                    }
                    for original, measured in zip(originals, costs, strict=True)
                ]
                for stage, originals, costs in (
                    ("foundation", audit["cases"], foundation_costs),
                    ("selection", selection["cases"], selection_costs),
                )
            },
        },
        sunk_requests_by_role=dict(
            Counter(
                role
                for row in [*foundation_costs, *selection_costs]
                for role, count in row["requests_by_role"].items()
                for _ in range(count)
            )
        ),
        source_hashes={str(path): file_hash(path) for path in stage_source_paths()},
    )
    plan["content_hash"] = content_digest(plan)
    return plan


def verify_resource_plan_receipt(foundation: Path) -> dict[str, Any]:
    """INITIAL admission uses a fresh raw recompilation, never persisted flags."""
    settings = _json(foundation, "resource-inputs.json")
    if (
        not isinstance(settings, dict)
        or set(settings) != {"schema_version", "formal_n", "declared_ceilings"}
        or settings["schema_version"] != "ced.resource-inputs.v1"
        or settings["formal_n"] is not None
    ):
        raise ValueError(
            "initial resource inputs require explicit ceilings and no selected formal N"
        )
    receipt = _json(foundation, "resource-plan.json")
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"schema_version", "plan", "content_hash"}
        or receipt["schema_version"] != "ced.resource-plan-receipt.v1"
    ):
        raise ValueError("unsupported initial resource receipt")
    plan = receipt["plan"]
    if not isinstance(plan, dict) or receipt["content_hash"] != content_digest(plan):
        raise ValueError("resource receipt content differs")
    if plan.get("content_hash") != content_digest(
        {key: value for key, value in plan.items() if key != "content_hash"}
    ):
        raise ValueError("resource plan source/content hash differs")
    auxiliary = _path(foundation, "resource-evidence")
    recomputed = compile_resource_plan(
        foundation,
        formal_n=None,
        declared_ceilings=settings["declared_ceilings"],
        auxiliary_cost_evidence=auxiliary if auxiliary.is_dir() else None,
    )
    if recomputed != plan or (
        recomputed.get("scope") != "SOURCE_RESOURCE_DIAGNOSTIC"
        or recomputed.get("available") is not True
        or recomputed.get("budget_status") != "WITHIN_DECLARED_CEILINGS"
        or recomputed.get("physical_acceptance") is not False
        or recomputed.get("actual_research_status") != "NOT_RUN"
    ):
        raise ValueError(
            "initial resource budget is unavailable, incomplete, exceeded or unreproducible"
        )
    return recomputed
