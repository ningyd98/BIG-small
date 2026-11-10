"""Classify the one R550 real exchange offline; never rebuild a live contract."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.vision import grounded_planner, planner

ROUND = Path(__file__).resolve().parents[1]
WORKTREE = ROUND.parents[5]
BASE = WORKTREE / "datasets/model-cache/molmo-sol-r550-20261110"


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def verify_manifest(folder: Path, name: str) -> dict[str, Any]:
    manifest = folder / name
    rows = read(manifest)["files"]
    total = 0
    for row in rows:
        path = (folder / row["path"]).resolve(strict=True)
        assert path.is_relative_to(folder.resolve()), "manifest escapes evidence root"
        assert path.stat().st_size == row["bytes"], "raw size mismatch"
        assert digest(path) == row["sha256"], "raw hash mismatch"
        total += row["bytes"]
    return {"files_verified": len(rows), "bytes_verified": total, "sha256": digest(manifest)}


def age(captured: datetime, timestamp: str) -> float:
    return (datetime.fromisoformat(timestamp) - captured).total_seconds()


def main() -> None:
    live, probe, execution = BASE / "live-01", BASE / "probe-01", BASE / "execution-01"
    report = read(live / "report.json")
    actual = read(probe / "pipeline-return-01.json")
    probe_summary = read(probe / "probe-summary.json")
    request_path = live / "raw/cloud/attempt-01/request-0001.json"
    response_path = live / "raw/cloud/attempt-01/response-0001.json"
    outbound, response = read(request_path), read(response_path)
    choice = response["choices"][0]
    content = choice["message"]["content"]
    content_path = live / "raw/attempt-01/cloud-content.txt"
    assert content_path.read_bytes() == content.encode(), "cloud content byte mismatch"
    assert outbound["model"] == response["model"] == "gpt-6.1-sol"
    assert outbound["reasoning_effort"] == "low"
    assert outbound["max_completion_tokens"] == 4096
    assert outbound["response_format"] == {"type": "json_object"}
    assert all(isinstance(m["content"], str) for m in outbound["messages"])
    decision = grounded_planner.SkillDecision.model_validate(
        grounded_planner._strict_skill_json(content), strict=True
    )
    function = ast.parse(inspect.getsource(planner.build_grounded_contract)).body[0]
    required = next(
        node.value
        for node in function.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "required"
    )
    core = list(decision.skills)
    if core and core[0] == "HOME":
        core = core[1:]
    if core and core[-1] == "HOME":
        core = core[:-1]
    sequence_passed = core == ast.literal_eval(required)
    row = report["attempts"][0]
    evidence = row["evidence"]
    captured = datetime.fromisoformat(evidence["captured_at"])
    post = read(probe / "post-end-01.json")
    pipeline = read(probe / "pipeline-end-01.json")
    native = evidence["native_results"]
    timings = {
        "native_queries_inclusive_s": [n["provider_evidence"]["end_to_end_s"] for n in native],
        "native_queries_sum_s": sum(n["provider_evidence"]["end_to_end_s"] for n in native),
        "cloud_inclusive_s": post["end"]["monotonic_s"] - post["start"]["monotonic_s"],
        "pipeline_inclusive_s": (pipeline["end"]["monotonic_s"] - pipeline["start"]["monotonic_s"]),
        "capture_age_at_cloud_start_s": age(captured, post["start"]["utc"]),
        "capture_age_at_cloud_return_s": age(captured, post["end"]["utc"]),
        "capture_age_at_pipeline_return_s": age(captured, pipeline["end"]["utc"]),
        "immutable_ttl_s": 5,
        "scope": "inclusive wrapper boundaries, not exact private freshness check/provider time",
    }
    checks = {
        "cli_raw": verify_manifest(live, "raw-manifest.local.json"),
        "probe": verify_manifest(probe, "probe-manifest.local.json"),
    }
    prior_round = ROUND.parent / "round547-molmo-point-component-association-20261110"
    prior = read(prior_round / "native-cumulative-summary.json")
    prior_checks = []
    for old in prior["runs"]:
        folder = Path(old["local_raw_path"])
        assert digest(folder / "report.json") == old["report_sha256"]
        assert digest(folder / "raw-manifest.local.json") == old["raw_manifest_sha256"]
        prior_checks.append(
            {"run": old["name"], **verify_manifest(folder, "raw-manifest.local.json")}
        )
    files = []
    for path in sorted(BASE.rglob("*")):
        if path.is_file() and "runtime-cache" not in path.relative_to(BASE).parts:
            files.append(
                {
                    "path": str(path.relative_to(BASE)),
                    "bytes": path.stat().st_size,
                    "sha256": digest(path),
                    "attempt": "r550-live-s01-01",
                    "mtime_ns": path.stat().st_mtime_ns,
                }
            )
    combined = BASE / "local-evidence-manifest.json"
    write_new(combined, {"files": files, "excluded": ["runtime-cache; immutable assets external"]})
    checks["combined"] = verify_manifest(BASE, combined.name)
    attempt = actual["attempts"][0]
    assert report["model_loads_started"] == 1
    assert report["generation_calls_started"] == report["generation_calls_completed"] == 2
    assert report["paid_cloud_calls_started"] == probe_summary["paid_starts"] == 1
    assert probe_summary["pipeline_calls"] == 1 and not probe_summary["capture_gaps"]
    assert actual["outcome"] == "REQUEST_MORE_OBSERVATION"
    assert actual["reason"] == "capture_time_not_fresh" and actual["contract"] is None
    assert not attempt["repaired"] and attempt["repair_attempts"] == 0
    assert sequence_passed and decision.skills
    summary = {
        "status": "REAL_CLOUD_RESPONSE_RECEIVED_LIVE_PLAN_REJECTED_STALE",
        "baseline_commit": read(ROUND / "plan.json")["baseline_commit"],
        "scope": "single fresh simulated S01 capture; real native and official cloud inference",
        "exit_code": read(execution / "process-end.json")["exit_code"],
        "resource_admission": report["resource_admission"],
        "native": {
            "model": "allenai/Molmo2-ER",
            "precision": "BF16",
            "load_s": read(live / "raw/native/loaded.json")["load_s"],
            "loads_started": 1,
            "generations_started": 2,
            "generations_completed": 2,
            "original_target_pixel": evidence["native_original_pixel_target"],
            "associated_target_pixel": evidence["associated_pixel_target"],
            "original_destination_pixel": evidence["native_original_pixel_destination"],
            "association": "one bounded unique red component; original prediction retained",
        },
        "geometry": {
            "status": row["local_geometry_status"],
            "depth_source": "original aligned optical_z_m float32",
            "grounded_target": evidence["grounded_target"],
            "grounded_destination": evidence["grounded_destination"],
            "resolved_top_grasp_tcp": evidence["resolved_top_grasp_tcp"],
            "extent_complete": evidence["opencv_initial_geometry"]["target"]["extent_complete"],
            "depth_error_bound_m": evidence["opencv_initial_geometry"]["target"][
                "depth_error_bound_m"
            ],
            "acceptance": "calibrated development estimate only",
        },
        "observation": {
            key: evidence[key]
            for key in [
                "source",
                "scene_id",
                "episode_id",
                "observation_id",
                "captured_at",
                "checksum_sha256",
                "rgb_sha256",
                "depth_sha256",
            ]
        },
        "cloud": {
            "status": "REAL_RESPONSE_RECEIVED",
            "attempts": 1,
            "profile_id": "profile-4f24f5330ad644ad",
            "config_version": 2,
            "requested_model": outbound["model"],
            "returned_model": response["model"],
            "identity_match": True,
            "route": "https://api.openai.com/v1/chat/completions",
            "settings_hash": evidence["cloud_request_settings_hash"],
            "reasoning_effort": outbound["reasoning_effort"],
            "max_completion_tokens": outbound["max_completion_tokens"],
            "timeout_s": 30,
            "response_format": outbound["response_format"],
            "image_count": 0,
            "request_sha256": digest(request_path),
            "response_sha256": digest(response_path),
            "content_sha256": digest(content_path),
            "finish_reason": choice.get("finish_reason"),
            "usage_counts": response.get("usage"),
            "http_numeric_status": "NOT_CAPTURED",
            "monetary_cost": "NOT_EXPOSED",
            "raw_content_and_token_ids": "LOCAL_ONLY",
        },
        "offline_content_check": {
            "label": "OFFLINE_CONTENT_CHECK",
            "strict_json_and_schema": "PASS",
            "skills_whitelist": "PASS",
            "skills_count": len(decision.skills),
            "nonempty": bool(decision.skills),
            "sequence_matches_existing_core": sequence_passed,
            "sequence_policy_source_sha256": digest(
                WORKTREE / "src/cloud_edge_robot_arm/vision/planner.py"
            ),
            "contract_built_offline": False,
            "changes_live_outcome": False,
        },
        "actual_pipeline": {
            "outcome": actual["outcome"],
            "reason": actual["reason"],
            "contract": actual["contract"],
            "dispatch": actual["dispatch"],
            "validation": actual["validation"],
            "repaired": attempt["repaired"],
            "repair_attempts": attempt["repair_attempts"],
            "validation_scope": "accepted more-observation sentinel; no executable contract",
            "live_skill_parse": "NOT_REACHED_AFTER_FRESHNESS_REJECTION",
            "trusted_contract_field_audit": "NOT_PERFORMED_NO_CONTRACT",
            "exact_result_sha256": digest(probe / "pipeline-return-01.json"),
        },
        "timing": timings,
        "cumulative": {
            "native_loads_started": 3,
            "generations_started": 6,
            "generations_completed": 6,
            "paid_starts": 1,
            "current_allocation_exhausted": True,
            "hardware_dispatch": False,
        },
        "evidence_verification": checks,
        "prior_frozen_evidence_unchanged": prior_checks,
        "physical": "NOT_PERFORMED",
        "formal_research": "NOT_PERFORMED",
        "next_step": (
            "New actual Astra plan for separating cloud intent from fresh local grounding/"
            "contract validation; preserve stale rejection and do not merely increase TTL."
        ),
    }
    write_new(ROUND / "execution-result.json", summary)
    print(json.dumps({"status": summary["status"], "timing": timings, "verified": checks}))


if __name__ == "__main__":
    main()
