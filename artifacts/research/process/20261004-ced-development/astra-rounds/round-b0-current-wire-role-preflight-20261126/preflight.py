"""Check the current B0 role inputs and reproduce the unexecuted selection only."""

import hashlib
import json
import socket
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import yaml
from scripts.probe_rgbd_roles import _hash_sources, read_role_config, source_fingerprints
from scripts.run_rgbd_pilot import run_ced_pilot

from cloud_edge_robot_arm.research.freeze_evidence import verify_role_probe_evidence

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
COMMON = ROOT.parents[2]
PLAN = json.loads((HERE / "plan.json").read_bytes())
OUT = ROOT / PLAN["private_output"]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def deny(*args, **kwargs):
    raise AssertionError("offline B0 preflight attempted a network connection")


def changed(old, new):
    return sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))


def run():
    for key in ("source_sha256", "historical_sha256"):
        base = ROOT if key == "source_sha256" else ROOT / PLAN["historical_directory"]
        for p, pin in PLAN[key].items():
            require(sha(base / p) == pin, f"changed source: {p}")
    historical = ROOT / PLAN["historical_role_probe"]
    manifest = json.loads(
        (ROOT / PLAN["historical_directory"] / "nominal-role-probe-manifest.json").read_bytes()
    )
    for p, item in manifest["files"].items():
        full = (historical / p).resolve()
        require(
            full.is_relative_to(historical.resolve()) and sha(full) == item["sha256"],
            "historical original changed",
        )
    old = json.loads((historical / "role-probe-report.json").read_bytes())
    verified = verify_role_probe_evidence(historical)
    require(
        not verified["available"], "original historical probe unexpectedly qualifies current roles"
    )
    config = read_role_config(ROOT / "configs/research/ced_roles.yaml")
    require(old["probe_config"] == config["probe"], "nominal probe config changed")
    require(
        [x["phase"] for x in old["attempts"]] == ["first", "warm", "warm", "warm"]
        and all(
            x["transport_two_images"] and x["serialized_sent_bytes"] > 0 for x in old["attempts"]
        )
        and old["request_settings"]["model"] == "gpt-6.1-sol"
        and old["request_settings"]["image_size"] == [320, 240]
        and old["request_settings"]["coordinate_system"] == "normalized_1000",
        "historical probe transport or count differs",
    )
    maps = {
        "cloud": source_fingerprints(),
        "edge": _hash_sources(config["edge"]["source_paths"]),
        "device": _hash_sources(config["device"]["source_paths"]),
    }
    old_maps = {
        "cloud": old["bundle"]["cloud_snapshot"]["source_hashes"],
        "edge": old["edge_snapshot"]["source_hashes"],
        "device": old["device_source_hashes"],
    }
    alterations = {k: changed(old_maps[k], v) for k, v in maps.items()}
    expect = {
        "cloud": [
            "src/cloud_edge_robot_arm/vision/capture.py",
            "src/cloud_edge_robot_arm/vision/planner.py",
        ],
        "edge": [],
        "device": ["src/cloud_edge_robot_arm/vision/capture.py"],
    }
    require(alterations == expect, "current role source changes differ from registered history")
    old_output = ROOT / PLAN["old_dedicated_attempt_output"]
    require(not old_output.exists(), "prior registered executable directory already exists")
    cfg = ROOT / "configs/research/ced_selection.yaml"
    settings = yaml.safe_load(cfg.read_text())
    cfg_sha = sha(cfg)
    source_paths = settings["exclude_datasets"]
    settings["exclude_datasets"] = [str(COMMON / x) for x in source_paths]
    require(
        all(Path(x).is_dir() for x in settings["exclude_datasets"]),
        "complete local exclusion sources unavailable",
    )
    revised = OUT / "dry-config.yaml"
    config_bytes = yaml.safe_dump(settings, sort_keys=False).encode()
    selection_dir = OUT / "selection"
    summary_path = selection_dir / "summary.json"
    if summary_path.is_file():
        require(revised.read_bytes() == config_bytes, "existing offline selection input changed")
        selection = json.loads(summary_path.read_bytes())
    else:
        OUT.mkdir(parents=True, exist_ok=False)
        with revised.open("xb") as stream:
            stream.write(config_bytes)
        selection = run_ced_pilot(
            revised,
            selection_dir,
            "selection",
            service=None,
            profile_id=None,
            execute=False,
            allow_paid=False,
        )
    require(sha(cfg) == cfg_sha, "active configuration changed")
    assignments_sha = sha(selection_dir / "assignments.json")
    records = json.loads((selection_dir / "results.json").read_bytes())
    assignments = json.loads((selection_dir / "assignments.json").read_bytes())
    periods = Counter(str(r["period_s"]) for r in assignments)
    groups = Counter(r["group_id"] for r in assignments)
    require(
        len(periods) == 4
        and set(periods.values()) == {120}
        and len(groups) == 120
        and set(groups.values()) == {4},
        "fixed-cadence placement grid changed",
    )
    require(
        selection["terminal_status_counts"] == {"NOT_EXECUTED": 480}
        and selection["group_denominator"] == 120
        and len(records) == 480
        and all(r["status"] == "NOT_EXECUTED" and r["cloud_requests"] == 0 for r in records)
        and assignments_sha == PLAN["expected_dry_assignment_sha256"]
        and selection["execution_mode"] == "NOT_EXECUTED"
        and selection["selected_period_s"] is None,
        "dry selection count or original assignment drifted",
    )
    with (OUT / "receipt.json").open("x") as stream:
        json.dump(
            {
                "plan_sha256": sha(HERE / "plan.json"),
                "code_sha256": sha(Path(__file__)),
                "historical_original_file_count": len(manifest["files"]),
                "historical_two_image_sends": len(old["attempts"]),
                "historical_probe_available_for_current_roles": verified["available"],
                "active_role_fingerprints": maps,
                "changed_files_by_role": alterations,
                "prior_execution_path_exists": False,
                "assignment_file_sha256": assignments_sha,
                "case_status_counts": selection["terminal_status_counts"],
                "period_counts": dict(periods),
                "distinct_groups": len(groups),
                "actual_cloud_requests": 0,
                "actual_b0": 0,
                "formal_g2": 0,
                "hardware": 0,
                "selection_summary_sha256": sha(OUT / "selection/summary.json"),
                "current_config_sha256": cfg_sha,
                "dry_copy_config_sha256": sha(revised),
            },
            stream,
            sort_keys=True,
            indent=2,
        )
        stream.write("\n")


if __name__ == "__main__":
    with patch.multiple(socket.socket, connect=deny, connect_ex=deny):
        run()
