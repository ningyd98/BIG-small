"""Pure Task1 policy/preregistration shape validation; no runtime authority."""

from __future__ import annotations

import json
import re
from typing import Any, cast

POLICY_V1: dict[str, Any] = {
    "schema_version": "simulation.operational-prefix.startup.v1",
    "clock_schema": "simulation.operational-time.v1",
    "source_scope": "EXCLUDED_SOURCE_ONLY_PREFIX",
    "scenario": "S01_NORMAL_STATIC",
    "seed": 0,
    "settle_steps": 120,
    "explicit_capture_count": 1,
    "ordinary_max_age_ns": 5_000_000_000,
    "task_timeout_s": 60,
    "max_attempts": 1,
    "recipe_id": "oc2-reset120-capture-v1",
}
LIMITS_V1: dict[str, Any] = {
    "formal_accepted": False,
    "native_authority": "UNAVAILABLE",
    "UTC_SI_accuracy": "UNVERIFIED",
    "utc_accuracy": None,
    "si_accuracy": None,
    "future_H_D": "UNKNOWN",
    "geometry_motion": "UNKNOWN",
    "calibration_groups": 0,
    "restart_suspend_hostpause": "NOT_TESTED_OC3_GATE",
    "lease_clock_migration": "NOT_DONE_OC3",
    "consumer_feasibility": "UNAVAILABLE",
}


def canonical_bytes_v1(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate original JSON key")
        result[name] = value
    return result


def decode_original_json_v1(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_unique_object)


def _shape(value: Any, names: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != names:
        raise ValueError("complete exact operational original schema required")
    return cast(dict[str, Any], value)


def _text(value: Any) -> None:
    if type(value) is not str or not value:
        raise ValueError("nonempty original identity required")


def _integer(value: Any, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError("original integer required without boolean/coercion")


def validate_policy_v1(value: Any) -> dict[str, Any]:
    data = _shape(value, set(POLICY_V1))
    for name, expected in POLICY_V1.items():
        if type(data[name]) is not type(expected) or data[name] != expected:
            raise ValueError("fixed source-only operational startup policy required")
    return dict(data)


def validate_inventory_v1(value: Any, *, allow_empty_instances: bool = False) -> None:
    if type(value) is not dict or not value:
        raise ValueError("complete source inventory required")
    for path, pin in value.items():
        _text(path)
        if (
            path.startswith("/")
            or "\\" in path
            or any(p in {"", ".", ".."} for p in path.split("/"))
        ):
            raise ValueError("repository relative original source path required")
        row = _shape(pin, {"sha256", "bytes"})
        digest = row["sha256"]
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("lowercase original SHA256 required")
        minimum = (
            0
            if allow_empty_instances is True
            and re.fullmatch(r"frames/acquisition-[1-9][0-9]*/instances\.i32", path) is not None
            else 1
        )
        _integer(row["bytes"], minimum=minimum)


def validate_preregistration_v1(value: Any) -> dict[str, Any]:
    data = _shape(
        value,
        {
            "schema_version",
            "application_id",
            "source_session_id",
            "policy",
            "config_sha256",
            "source_inventory",
            "recipe",
            "worker_source",
            "clock_domain",
            "group_inventory",
            "limits",
        },
    )
    if data["schema_version"] != "simulation.operational-prefix.preregistration.v1":
        raise ValueError("operational preregistration schema required")
    _text(data["application_id"])
    _text(data["source_session_id"])
    validate_policy_v1(data["policy"])
    validate_inventory_v1(data["source_inventory"])
    config_sha = data["config_sha256"]
    if (
        type(config_sha) is not str
        or len(config_sha) != 64
        or any(c not in "0123456789abcdef" for c in config_sha)
    ):
        raise ValueError("original policy SHA256 required")
    recipe = _shape(
        data["recipe"],
        {
            "recipe_id",
            "reset_count",
            "settle_steps",
            "explicit_capture_count",
            "scenario",
            "seed",
            "scene",
            "camera",
            "simulator_config",
        },
    )
    for name in ("recipe_id", "settle_steps", "explicit_capture_count", "scenario", "seed"):
        if type(recipe[name]) is not type(POLICY_V1[name]) or recipe[name] != POLICY_V1[name]:
            raise ValueError("original recipe differs from policy")
    if type(recipe["reset_count"]) is not int or recipe["reset_count"] != 1:
        raise ValueError("one preregistered RESET required")
    scene = _shape(recipe["scene"], {"path", "sha256", "bytes"})
    if scene["path"] != "assets/robots/franka_panda/scene.xml" or {
        key: scene[key] for key in ("sha256", "bytes")
    } != data["source_inventory"].get(scene["path"]):
        raise ValueError("original scene asset/source join required")
    if recipe["camera"] != {"width": 320, "height": 240, "render_rgb": True, "render_depth": True}:
        raise ValueError("fixed original RGB-D camera policy required")
    if type(recipe["simulator_config"]) is not dict:
        raise ValueError("complete simulator policy required")
    worker = _shape(
        data["worker_source"],
        {
            "job_id",
            "run_id",
            "attempt",
            "lease_id",
            "worker_id",
            "lease",
            "task_origin",
            "lease_clock_migration",
        },
    )
    for key in ("job_id", "run_id", "lease_id", "worker_id"):
        _text(worker[key])
    if type(worker["attempt"]) is not int or worker["attempt"] != 1:
        raise ValueError("sole original attempt required")
    lease = _shape(
        worker["lease"],
        {
            "scope",
            "job_id",
            "run_id",
            "worker_id",
            "lease_id",
            "attempt",
            "acquired_at",
            "observed_at",
            "expires_at",
            "job_state_hash",
            "lease_state_hash",
            "attempt_state_hash",
        },
    )
    if lease["scope"] != "WORKER_LEASE_SOURCE_ONLY" or any(
        lease[key] != worker[key]
        for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt")
    ):
        raise ValueError("original job/lease/attempt join required")
    if worker["lease_clock_migration"] != "NOT_DONE_OC3":
        raise ValueError("original UTC lease guard must remain explicit")
    domain = data["clock_domain"]
    if type(domain) is not dict or domain.get("schema") != "simulation.operational-time.v1":
        raise ValueError("original OC1 domain description required")
    if any(
        domain.get(key) != "UNAVAILABLE"
        for key in ("worker_authority", "lease_authority", "native_authority")
    ):
        raise ValueError("OC1 descriptor cannot authorize a worker/lease/native source")
    groups = _shape(
        data["group_inventory"],
        {"source_session_ids", "source_session_count", "independence", "support_group_count"},
    )
    if groups != {
        "source_session_ids": [data["source_session_id"]],
        "source_session_count": 1,
        "independence": "UNESTABLISHED",
        "support_group_count": 0,
    }:
        raise ValueError("one source session is not an independent support/calibration group")
    if data["limits"] != LIMITS_V1:
        raise ValueError("original source-only acceptance boundaries required")
    return data


def validate_operational_originals_v1(value: Any) -> dict[str, Any]:
    """Pure exact slab/event shape; live token authority remains with OC1 owner."""
    data = _shape(
        value,
        {
            "schema_version",
            "source_session_id",
            "domain_sha256",
            "events",
            "current",
            "allocated_acquisition_ids",
            "allocated_action_ids",
            "failures",
            "backend_observer_failures",
            "super_audit_failures",
        },
    )
    if data["schema_version"] != "simulation.operational-prefix.originals.v1":
        raise ValueError("original operational slab schema required")
    for key in ("source_session_id", "domain_sha256"):
        _text(data[key])
    for key in (
        "events",
        "allocated_acquisition_ids",
        "allocated_action_ids",
        "failures",
        "backend_observer_failures",
        "super_audit_failures",
    ):
        if type(data[key]) is not list:
            raise ValueError("complete original slab list required")
    for row in data["events"]:
        _shape(
            row,
            {
                "attempt_seq",
                "operation_id",
                "kind",
                "source_session_id",
                "domain_sha256",
                "begin",
                "end",
                "begin_seq",
                "mark_seq",
                "end_seq",
                "token_identity",
                "begin_ns",
                "bracket",
                "acquisition_id",
                "error",
            },
        )
        for key in ("attempt_seq", "operation_id", "begin_seq"):
            _integer(row[key], minimum=1)
        for key in ("begin", "end"):
            if row[key] is not None:
                boundary = _shape(
                    row[key],
                    {
                        "operation_id",
                        "kind",
                        "phase",
                        "episode_id",
                        "physics_step",
                        "sim_time_s",
                        "parameters",
                        "result",
                        "error_type",
                        "error",
                    },
                )
                _integer(boundary["operation_id"], minimum=1)
                _integer(boundary["physics_step"])
        for key in ("mark_seq", "end_seq", "begin_ns"):
            if row[key] is not None:
                _integer(row[key])
        if row["bracket"] is not None:
            bracket = _shape(
                row["bracket"], {"event_identity", "lower_ns", "upper_ns", "domain_sha256"}
            )
            for key in ("lower_ns", "upper_ns"):
                _integer(bracket[key])
    if data["current"] is not None:
        current = _shape(
            data["current"],
            {
                "source_acquisition_id",
                "returned_acquisition_id",
                "after_token_identity",
                "domain_sha256",
                "current_identity",
                "lower_ns",
                "upper_ns",
                "current_seq",
                "episode_id",
                "physics_step",
                "sim_time_s",
                "age_lower_ns",
                "age_upper_ns",
                "within_5s",
            },
        )
        for key in (
            "lower_ns",
            "upper_ns",
            "current_seq",
            "physics_step",
            "age_lower_ns",
            "age_upper_ns",
        ):
            _integer(current[key])
        if type(current["within_5s"]) is not bool:
            raise ValueError("recorded boolean comparison required")
    return data
