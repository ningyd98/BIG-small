import hashlib
import importlib.util
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import cloud_edge_robot_arm.harness
from cloud_edge_robot_arm.harness.cli import (
    _finish_launch,
    _native_command,
    _native_receipt,
    _run_child,
)
from cloud_edge_robot_arm.harness.checkout import verify_checkout
from cloud_edge_robot_arm.harness.config import load_config

checkout = Path("/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall")
primary = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
runtime = primary / "datasets/model-cache/ordered-small-vlm-20261109/runtimes"
prefix = Path(sys.prefix)
assert Path(cloud_edge_robot_arm.harness.__file__).is_relative_to(prefix)
assert not any(importlib.util.find_spec(item) for item in ("mujoco", "cv2", "torch", "transformers"))
cwd = Path(tempfile.mkdtemp(prefix="bigsmall-h1-review-outside-20261118-", dir="/tmp"))
base_env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "CUDA_VISIBLE_DEVICES": ""}
cli = prefix / "bin" / "bigsmall-harness"
print(f"cwd {cwd}", flush=True)
print(f"installed CLI {cli}", flush=True)
print(f"installed package {cloud_edge_robot_arm.harness.__file__}", flush=True)
print(f"Python {sys.version.split()[0]}", flush=True)
print("CLI subprocess environment only PATH, LANG and empty CUDA_VISIBLE_DEVICES", flush=True)

def run(label, *args, expected=0, executable=cli):
    argv = [str(executable), *map(str, args)]
    print("$", shlex.join(argv), flush=True)
    reply = subprocess.run(
        argv, cwd=cwd, env=base_env, capture_output=True, text=True, timeout=30, check=False,
    )
    (cwd / label).write_text(reply.stdout)
    print(f"exit={reply.returncode} stdout={label}", flush=True)
    assert reply.returncode == expected, reply.stderr or reply.stdout
    return reply.stdout

assert "run-simulation" in run("help.txt", "--help")
assert run("version.txt", "--version").strip() == "bigsmall-harness 0.1.0"
validated = json.loads(run("validate.json", "validate"))
assert validated["status"] == "VALIDATED"
old = json.loads((checkout / "artifacts/research/process/20261118-real-model-harness"
                  / "h0-h1/clean-validate.json").read_bytes())
assert validated["configuration_sha256"] == old["configuration_sha256"]
doctor = json.loads(run("doctor.json", "doctor"))
assert doctor["resources"]["native_model_runtime"] == "EXTERNAL_UNVERIFIED"
checked = json.loads(run("doctor-checkout.json", "doctor", "--source-checkout", checkout))
assert checked["source"]["root"] == str(checkout)
config_path = cwd / "requested.json"
requested = validated["configuration"] | {
    "seed": 44101, "scene_split": "development", "camera_position_m": [0.3, 0.1, 1.4],
}
config_path.write_text(json.dumps(requested))
episode = cwd / "prepare-episode"
prepared = json.loads(run(
    "prepare.json", "prepare", "--source-checkout", checkout, "--output", episode,
    "--config", config_path,
))
assert prepared["status"] == "PREPARED"
assert prepared["planned_configuration"] == requested
assert prepared["effective_configuration"]["scene_sampling"] == "FIXED_REGISTERED_SCENE"
assert prepared["effective_configuration"]["camera_position_m"] is None
assert set(prepared["not_applied"]) == {"scene_split", "visual_servo", "camera_position_m"}
assert prepared["episode"]["executed_actions"] == prepared["episode"]["model_calls"] == 0
assert prepared["episode"]["physical_success"] is None
manifest = episode / "evidence-manifest.json"
before = hashlib.sha256(manifest.read_bytes()).hexdigest()
index = json.loads(run("evidence.json", "evidence", episode))
assert index["manifest_sha256"] == before and index["file_count"] == 3
assert index["status"] == "VERIFIED"
run("prepare-rejected.json", "prepare", "--source-checkout", checkout, "--output", episode,
    expected=2)
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == before
run("pip-check.txt", "-m", "pip", "check", executable=prefix / "bin" / "python")
run("pip-freeze.txt", "-m", "pip", "freeze", executable=prefix / "bin" / "python")
print("offline checks passed", flush=True)

config = load_config()
source = verify_checkout(checkout, config)
native_env = dict(base_env, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
for name in ("molmoer-r505", "groundingpi-r505"):
    executable = runtime / name / "bin/python"
    receipt_path = cwd / f"{name}.json"
    output = cwd / f"{name}-episode"
    command = _native_command(executable, source, receipt_path, ["--help", "--output", str(output)])
    print(f"$ {executable} -I -B [installed native bootstrap] --help --output {output}", flush=True)
    child = _run_child(command, source=source, env=native_env, timeout=90)
    receipt = _native_receipt(receipt_path)
    (cwd / f"{name}-stdout.txt").write_text(child.stdout)
    print(f"exit={child.code} receipt={receipt_path.name}", flush=True)
    assert not output.exists(), "help/preflight may not create an episode"
    assert receipt is not None, "native bootstrap did not write admission receipt"
    assert receipt["executable"] == str(executable)
    if name == "molmoer-r505":
        assert child.code == 0, receipt
        assert "--component-diagnostic" in child.stdout
        assert receipt["status"] == "READY_TO_DELEGATE"
        proof = receipt["r545_admission"]
        assert proof["status"] == "IMPORT_AND_CPU_ABI_PASS"
        assert proof["cuda_initialized"] is False
        assert proof["model_loads"] == proof["generation_calls"] == proof["paid_calls"] == 0
        assert len(receipt["project_modules"]) == 6
    else:
        assert child.code == 2
        assert child.stdout == ""
        assert receipt["status"] == "REJECTED_BEFORE_EPISODE"
        code, report = _finish_launch({}, config, output, child, receipt)
        assert code == 2 and report["status"] == "NOT_STARTED"
        assert report["episode_exit_code"] == report["wrapper_exit_code"] == 2
print("native CPU --help pair and clean wheel verification complete", flush=True)
