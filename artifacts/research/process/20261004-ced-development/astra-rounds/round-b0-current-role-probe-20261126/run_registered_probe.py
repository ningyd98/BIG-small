"""Acquire the single registered current-source nominal B0 probe."""
import fcntl
import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from cloud_edge_robot_arm.model_control.secret_store import create_secret_store
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
from cloud_edge_robot_arm.vision.role_models import cloud_request_settings, resolve_cloud_role
from scripts.probe_rgbd_roles import read_role_config, run_probe, source_fingerprints

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
COMMON = ROOT.parents[2]
INPUT = ROOT / "cache/research/raw/20261119-b0-role-probe/current-nominal"
OUTPUT = ROOT / "cache/research/raw/20261126-b0-role-probe/current-source-01"
EGL_LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path, expected):
    if sha(path) != expected:
        raise ValueError(f"input digest mismatch: {path.name}")


def run():
    plan = json.loads((HERE / "plan.json").read_bytes())
    subprocess.run(["git", "merge-base", "--is-ancestor", plan["baseline"], "HEAD"], check=True)
    for path, expected in plan["source_sha256"].items():
        verified(ROOT / path, expected)
    historical = ROOT / plan["historical_directory"]
    for name, expected in plan["historical_sha256"].items():
        verified(historical / name, expected)
    manifest = json.loads((historical / "nominal-role-probe-manifest.json").read_bytes())
    for name, row in manifest["files"].items():
        verified(INPUT / name, row["sha256"])
    old = json.loads((INPUT / "role-probe-report.json").read_bytes())
    provider = old["bundle"]["cloud_snapshot"]["provider_id"]
    config_path = ROOT / "configs/research/ced_roles.yaml"
    config = read_role_config(config_path)
    if config["probe"] != old["probe_config"] or config["probe"]["warm_runs"] != 3:
        raise ValueError("historical nominal probe set differs")
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("native EGL is required")

    db = COMMON / "data/model_control.db"
    secrets = create_secret_store(db)
    if not secrets.has_secret(provider):
        raise ValueError("original model profile is unavailable")
    with TemporaryDirectory(prefix="bigsmall-nominal-profile-") as private:
        copy = Path(private) / "profile.db"
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copy)) as target:
                source.backup(target)
        service = ModelControlService(
            repository=SQLiteModelProfileRepository(copy), secret_store=secrets,
        )
        cloud = config["cloud"]
        planner, snapshot = resolve_cloud_role(
            service, provider, source_hashes=source_fingerprints(), allow_paid=True,
            image_size=tuple(cloud["image_size"]), coordinate_system=cloud["coordinate_system"],
            grasp_profile=cloud["grasp_profile"], available_model_ids=cloud["available_model_ids"],
            expected_model_family=cloud["model_family"],
        )
        if snapshot.model_id != "gpt-6.1-sol" or cloud_request_settings(planner) != old["request_settings"]:
            raise ValueError("historical authorized request configuration differs")

        lock = COMMON / "cache/research/raw/nominal-role-probe.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a") as shared, EGL_LOCK.open("a") as renderer:
            for handle in (shared, renderer):
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            OUTPUT.mkdir(parents=True, exist_ok=False)
            with (OUTPUT / "startup.json").open("x") as stream:
                json.dump({
                    "plan_sha256": sha(HERE / "plan.json"),
                    "driver_sha256": sha(Path(__file__)),
                    "maximum_sends": 4,
                    "baseline": plan["baseline"],
                }, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            result = run_probe(
                config_path, OUTPUT / "private-probe", service=service, profile_id=provider,
                execute=True, allow_paid=True,
            )
            print(json.dumps({"status": result["status"], "attempts": len(result["attempts"])}))
            return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(run())
