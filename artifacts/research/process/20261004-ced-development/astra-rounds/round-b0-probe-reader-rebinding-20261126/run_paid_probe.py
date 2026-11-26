"""Conditional original HTTPS probe. This entry sends simulated RGB and depth."""

import argparse
import fcntl
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import probe_scope as scope
from scripts import probe_rgbd_roles as roles

COMMON = scope.ROOT.parents[2]
OUTPUT = scope.ROOT / scope.PLAN["current_nominal_real_output"]
LOCK = COMMON / "cache/research/raw/nominal-role-probe.lock"
EGL = scope.ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"
CONFIG = scope.ROOT / "configs/research/ced_roles.yaml"


def guarded_attempt(fence, original, expected_settings):
    from cloud_edge_robot_arm.vision.role_models import cloud_request_settings

    def call(planner, request, frame, output, index, cloud, *, request_settings):
        scope.require(
            cloud.model_id == scope.PLAN["authorized_model_if_later_approved"],
            "unexpected cloud model",
        )
        scope.require(
            cloud_request_settings(planner) == request_settings == expected_settings,
            "authorized provider route or original settings changed",
        )
        current = planner.raw_transport_observer

        def guard(phase, path, raw):
            if phase == "REQUEST":
                body = json.loads(raw)
                wire = roles.summarize_role_request(body)
                scope.require(
                    path == expected_settings["chat_path"]
                    and body.get("model") == expected_settings["model"]
                    and wire.get("image_count") == wire.get("distinct_image_count") == 2
                    and cloud_request_settings(planner) == expected_settings,
                    "unregistered route, model or payload",
                )
                fence.reserve(index, path, raw)
            if current is not None:
                current(phase, path, raw)

        planner.raw_transport_observer = guard
        try:
            return original(
                planner, request, frame, output, index, cloud, request_settings=request_settings
            )
        finally:
            planner.raw_transport_observer = current

    return call


def execute():
    from cloud_edge_robot_arm.model_control.secret_store import create_secret_store
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.research.freeze_evidence import verify_role_probe_evidence
    from cloud_edge_robot_arm.vision.role_models import cloud_request_settings, resolve_cloud_role

    scope.require(os.environ.get("MUJOCO_GL") == "egl", "original EGL mode required")
    _, history = scope.preflight_inputs()
    settings = history["request_settings"]
    config = roles.read_role_config(CONFIG)
    scope.require(
        history["probe_config"] == config["probe"]
        and config["probe"]["warm_runs"] + 1 == scope.MAX_SENDS,
        "original experiment schedule changed",
    )
    current = json.loads((scope.ROOT / scope.PLAN["current_preflight_public"]).read_bytes())
    scope.require(
        {
            "cloud": roles.source_fingerprints(),
            "edge": roles._hash_sources(config["edge"]["source_paths"]),
            "device": roles._hash_sources(config["device"]["source_paths"]),
        }
        == current["active_role_fingerprints"],
        "current role implementation no longer matches the preregistration",
    )
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as shared, EGL.open("rb") as renderer:
        for lease in (shared, renderer):
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        scope.require(
            not any(OUTPUT.parent.glob("current-source-*")),
            "an earlier nominal probe invocation already consumed or may have consumed this batch",
        )
        fence = scope.SendFence(
            OUTPUT,
            {
                "plan_sha256": scope.sha(scope.PLAN_PATH),
                "driver_sha256": scope.sha(Path(__file__)),
                "budget_implementation_sha256": scope.sha(Path(scope.__file__)),
                "maximum_sends": scope.MAX_SENDS,
                "active_git": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=scope.ROOT, text=True
                ).strip(),
                "active_role_map": current["active_role_fingerprints"],
            },
        )
        try:
            database = COMMON / "data/model_control.db"
            secrets = create_secret_store(database)
            profile = history["bundle"]["cloud_snapshot"]["provider_id"]
            scope.require(secrets.has_secret(profile), "original model profile secret unavailable")
            with TemporaryDirectory(prefix="bigsmall-current-nominal-role-") as tmp:
                copy = Path(tmp) / "profiles.db"
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as old:
                    with closing(sqlite3.connect(copy)) as disposable:
                        old.backup(disposable)
                service = ModelControlService(
                    repository=SQLiteModelProfileRepository(copy),
                    secret_store=secrets,
                )
                cloud = config["cloud"]
                planner, actual = resolve_cloud_role(
                    service,
                    profile,
                    source_hashes=roles.source_fingerprints(),
                    allow_paid=True,
                    image_size=tuple(cloud["image_size"]),
                    coordinate_system=cloud["coordinate_system"],
                    grasp_profile=cloud["grasp_profile"],
                    available_model_ids=cloud["available_model_ids"],
                    expected_model_family=cloud["model_family"],
                )
                scope.require(
                    actual.provider_location == "REMOTE_SERVICE"
                    and actual.model_id == scope.PLAN["authorized_model_if_later_approved"]
                    and cloud_request_settings(planner) == settings,
                    "original remote provider or effective settings changed",
                )
                original = roles._attempt
                with patch.object(roles, "_attempt", guarded_attempt(fence, original, settings)):
                    result = roles.run_probe(
                        CONFIG,
                        OUTPUT / "private-probe",
                        service=service,
                        profile_id=profile,
                        execute=True,
                        allow_paid=True,
                    )
            verification = verify_role_probe_evidence(OUTPUT / "private-probe")
            sent = sum(
                item["sent_at"] is not None
                for attempt in result["attempts"]
                for item in attempt.get("cost_ledger", {}).get("requests", [])
            )
            scope.require(
                0 <= sent <= fence.cursor <= scope.MAX_SENDS, "report and reserved slots conflict"
            )
            scope.write_once(
                OUTPUT / "readback.json",
                {
                    "status": result["status"],
                    "measured_sends": sent,
                    "reserved_slots": fence.cursor,
                    "independent_nominal_probe_available": verification["available"],
                    "historical_replay": False,
                    "actual_b0": 0,
                    "formal_g2": 0,
                    "report_sha256": scope.sha(OUTPUT / "private-probe/role-probe-report.json"),
                },
            )
            return 0 if result["status"] == "PASS" and verification["available"] else 2
        except Exception as error:
            scope.write_once(
                OUTPUT / "interrupted.json",
                {
                    "failure_class": type(error).__name__,
                    "reserved_slots": fence.cursor,
                },
            )
            return 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    if not (args.execute and args.allow_paid):
        parser.exit(3, "No external request was started. Both execution flags are required.\n")
    os.umask(0o077)
    raise SystemExit(execute())
