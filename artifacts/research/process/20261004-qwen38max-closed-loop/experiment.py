"""Development-only Qwen3.8-Max physical closed-loop evaluation; no production changes.

MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-qwen38max-closed-loop/experiment.py prepare
MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-qwen38max-closed-loop/experiment.py run
The API credential is requested with getpass, used only in memory, never persisted.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import socket
import sys
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
BASE = SCRIPT_DIR / "run-v2"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MUJOCO_GL", "egl")

from scripts.run_rgbd_smoke import _FaultCapture, apply_independent_semantics, build_assignments, summarize
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy, write_json
from cloud_edge_robot_arm.vision.execution import run_visual_episode
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter

ENDPOINT = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
NETWORK = {"mode": "direct", "interface": "enp7s0", "dns_servers": ["223.5.5.5", "223.6.6.6"],
           "allowed_hosts": ["token-plan.cn-beijing.maas.aliyuncs.com"]}
HISTORICAL = ROOT / "artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2"
CONFIG = ROOT / "configs/research/visual_smoke.yaml"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(UTC).isoformat()


def snapshot():
    return ModelConfigSnapshot(provider="openai_compatible", model="qwen3.8-max", endpoint=ENDPOINT,
        weight_digest="", quantization="HOSTED_UNKNOWN", image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512}, timeout_s=90,
        coordinate_system="normalized_1000", grasp_profile="mujoco_upright_box_v1")


def prepare():
    BASE.mkdir(parents=True, exist_ok=True)
    if (BASE / "protocol.json").exists():
        raise FileExistsError("protocol already exists; do not replace preregistration")
    settings = yaml.safe_load(CONFIG.read_text())
    assignments = read(HISTORICAL / "assignments.json")
    assert assignments == build_assignments(settings), "historical assignment mismatch"
    (BASE / "assignments.json").write_bytes((HISTORICAL / "assignments.json").read_bytes())
    (BASE / "config.yaml").write_bytes(CONFIG.read_bytes())
    write_json(BASE / "model.json", snapshot().evidence())
    historical_sources = read(HISTORICAL / "provenance.json")["source_sha256"]
    sources = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / "src").rglob("*.py")}
    sources.update({str(p.relative_to(ROOT)): digest(p) for p in (ROOT / "assets/robots/franka_panda").rglob("*") if p.is_file()})
    sources[str(Path(__file__).relative_to(ROOT))] = digest(Path(__file__))
    sources["scripts/run_rgbd_smoke.py"] = digest(ROOT / "scripts/run_rgbd_smoke.py")
    write_json(BASE / "protocol.json", {
        "created_at": now(), "scope": "VISION_CLOSED_LOOP", "formal_g1": False,
        "model": "qwen3.8-max", "endpoint": ENDPOINT, "model_snapshot_hash": snapshot().digest(),
        "hosted_weights_immutable": False, "quantization_and_weights": "NOT_DISCLOSED_BY_PROVIDER",
        "transport_extra_parameters": {"enable_thinking": False},
        "assignments_sha256": digest(BASE / "assignments.json"), "config_sha256": digest(BASE / "config.yaml"),
        "model_sha256": digest(BASE / "model.json"), "source_sha256": sources,
        "historical_source_differences": [p for p, h in historical_sources.items() if not (ROOT / p).is_file() or digest(ROOT / p) != h],
        "network": NETWORK, "trust_env": False, "follow_redirects": False, "tls_verification": True,
        "assigned": 20, "primary_denominator": "12 NORMAL episodes", "negative_and_faults": 8,
        "attempts_per_case": 1, "max_chat_requests": 60, "max_reobservations": 2, "max_action_retries": 0,
        "success": "online complete AND independent physical success AND no terminal reason AND assigned target present",
        "physical_criteria": "lift >= 0.05 m, continuous hold >= 0.5 s, release in target region stable >= 1 s, no scoped safety violation",
        "scope_note": "Cloud generates pixel/skill decisions; unchanged local RGBD grounding, tracking, safety and MuJoCo skill control execute. No local VLM or real robot.",
        "no_selection_or_retuning": True, "invoice_cost_cny": None,
    })
    print(json.dumps({"prepared": 20, "source_differences": read(BASE / "protocol.json")["historical_source_differences"]}), flush=True)


class CloudPlanner(RGBDPlannerAdapter):
    """Override only HTTP transport and record all inputs/receipts, preserving planner logic."""

    def __init__(self, client, key, directory):
        super().__init__(base_url=ENDPOINT, model="qwen3.8-max", provider="openai_compatible",
                         timeout_s=90, allow_paid=True, chat_path="/chat/completions", model_snapshot=snapshot())
        self.client, self.key, self.directory = client, key, directory
        self.calls = 0
        self.idle = threading.Event()
        self.idle.set()

    def redact(self, value):
        return re.sub(r"sk-[A-Za-z0-9_.-]+", "[REDACTED]", value.replace(self.key, "[REDACTED]"))

    def _post(self, path, body):
        if path != "/chat/completions" or body.get("model") != "qwen3.8-max" or self.calls >= 3:
            raise RGBDModelUnavailable("unexpected request or preregistered call budget exceeded")
        assert body["max_tokens"] == 512 and body["temperature"] == 0
        assert body["response_format"] == {"type": "json_object"}
        body = {**body, "enable_thinking": False}
        self.calls += 1
        directory = self.directory / "api" / f"{self.calls:02d}"
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "request.json", body)
        record = {"started_at": now(), "request_sha256": digest(directory / "request.json"),
                  "endpoint": ENDPOINT + path, "model_requested": body["model"], "ok": False}
        started = time.perf_counter()
        self.idle.clear()
        try:
            with self.client.stream("POST", ENDPOINT + path, json=body) as response:
                stream = response.extensions["network_stream"]
                sock = stream.get_extra_info("socket")
                record["network"] = {
                    "bound_interface": sock.getsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, 256).rstrip(b"\0").decode(),
                    "peer": sock.getpeername(), "local": sock.getsockname(),
                }
                if record["network"]["bound_interface"] != "enp7s0":
                    raise RuntimeError("physical interface verification failed")
                record["http_status"] = response.status_code
                record["response_headers"] = {k: v for k, v in response.headers.items()
                    if k.lower() in {"x-request-id", "request-id", "content-type", "date"}}
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 2_000_000:
                        raise ValueError("response size limit exceeded")
                decoded = json.loads(self.redact(raw.decode("utf8")))
                record["response"] = decoded
                if response.status_code != 200 or not isinstance(decoded, dict):
                    raise ValueError("API unsuccessful or invalid JSON object")
                record["ok"] = True
                return decoded
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": self.redact(str(exc))[:400]}
            raise RGBDModelUnavailable(f"cloud request failed: {type(exc).__name__}") from exc
        finally:
            record["wall_s"] = time.perf_counter() - started
            record["ended_at"] = now()
            write_json(directory / "receipt.json", record)
            self.idle.set()


def run():
    protocol = read(BASE / "protocol.json")
    for name in ("assignments", "config", "model"):
        file = name + (".yaml" if name == "config" else ".json")
        assert digest(BASE / file) == protocol[name + "_sha256"]
    for name, expected in protocol["source_sha256"].items():
        assert digest(ROOT / name) == expected, "source drift: " + name
    assert snapshot().digest() == protocol["model_snapshot_hash"]
    if (BASE / "run-start.json").exists():
        raise FileExistsError("one run only; no silent resume or overwrite")
    settings = yaml.safe_load((BASE / "config.yaml").read_text())
    assignments = read(BASE / "assignments.json")
    key = getpass.getpass("API key (no echo; memory only): ")
    if not key or "\n" in key:
        raise ValueError("invalid credential")
    write_json(BASE / "run-start.json", {"started_at": now(), "protocol_sha256": digest(BASE / "protocol.json")})
    records = []
    with httpx.Client(transport=create_direct_transport(NETWORK), trust_env=False, follow_redirects=False,
                      timeout=httpx.Timeout(90, connect=15), verify=True,
                      headers={"Authorization": "Bearer " + key}) as client:
        for case in assignments["cases"]:
            directory = BASE / "cases" / case["case_id"]
            directory.mkdir(parents=True, exist_ok=False)
            write_json(directory / "assignment.json", case)
            planner = CloudPlanner(client, key, directory)
            row = {"case_id": case["case_id"], "kind": case["kind"], "scene_hash": case["scene_hash"],
                   "success": False, "blocked": False, "model_calls": 0, "executed_actions": 0, "observation_count": 0}
            started = time.perf_counter()
            try:
                with _FaultCapture(SimulatorConfig(render_rgb=True, render_depth=True,
                        domain_randomization=False, seed=case["seed"])) as capture:
                    capture.apply_scene(SceneSpec.model_validate(case["scene"]))
                    capture._backend.step(steps=120)
                    capture.fault = case["kind"] == "INVALID_DEPTH"
                    capture.raw_output = directory / "raw-fault-frames"
                    if case["kind"] == "SAFETY_STOP":
                        capture._backend.emergency_stop()
                    started = time.perf_counter()
                    result = run_visual_episode(planner, MuJoCoSkillRobot(capture._backend), capture,
                        ExecutionPolicy(instruction=case["instruction"], timeout_s=settings["timeout_s"],
                            model_snapshot_hash=snapshot().digest(), output_dir=directory,
                            verification_budget=VerificationBudget(**settings["verification_budget"])))
                    row.update({k: v for k, v in asdict(result).items() if k != "verification_records"})
                    row["blocked"] = bool(result.terminal_reason and result.terminal_reason.startswith("BLOCKED_BY_ENV"))
            except Exception as exc:
                row.update(blocked=True, terminal_reason=f"BLOCKED_BY_ENV: {type(exc).__name__}: {planner.redact(str(exc))[:400]}")
            row["wall_latency_s"] = time.perf_counter() - started
            # A timed-out model worker can still finish a receipt; retain it without rerunning the episode.
            if not planner.idle.wait(timeout=95):
                raise RuntimeError("model transport still running; preserve incomplete run")
            row = apply_independent_semantics(case, row)
            row["absent_misoperation"] = case["kind"] == "MISSING_TARGET" and row["executed_actions"] > 0
            row["api_calls_recorded"] = planner.calls
            write_json(directory / "case-result.json", row)
            records.append(row)
            write_json(BASE / "progress.json", summarize(assignments, records))
            write_json(BASE / "results.json", records)
            print(f"{case['case_id']} {case['kind']} success={row['task_success']} "
                  f"reason={row.get('terminal_reason')} actions={row['executed_actions']} "
                  f"calls={row['model_calls']} wall={row['wall_latency_s']:.2f}s", flush=True)
    write_json(BASE / "summary.json", summarize(assignments, records))
    write_json(BASE / "run-end.json", {"ended_at": now(), "recorded": len(records)})
    print(json.dumps(read(BASE / "summary.json"), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "run"))
    args = parser.parse_args()
    prepare() if args.stage == "prepare" else run()
