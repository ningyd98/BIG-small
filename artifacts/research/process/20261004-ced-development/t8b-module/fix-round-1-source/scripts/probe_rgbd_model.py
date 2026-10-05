"""Probe a real local Ollama VLM using synchronized MuJoCo RGB-D frames.

No model download, ground-truth prompt injection or synthetic response occurs here.
The offline instance pass is inspected only *after* each actual model response.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from cloud_edge_robot_arm.vision.defaults import DEFAULT_FROZEN_DIR, DEFAULT_MODEL_CONFIG

SNAPSHOT_FIELDS = (
    "provider", "model", "endpoint", "weight_digest", "quantization", "image_size",
    "generation_parameters", "timeout_s",
)
OPTIONAL_SNAPSHOT_FIELDS = ("coordinate_system", "grasp_profile")
PROBE_FIELDS = ("scenario_id", "seed", "instruction", "warm_runs")
MAX_RESPONSE_BYTES = 2_000_000


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _source_fingerprints() -> dict[str, str]:
    """Bind a probe to the actual prompt, geometry, transport and capture implementation."""
    root = Path(__file__).resolve().parents[1]
    files = [
        "scripts/probe_rgbd_model.py",
        "assets/robots/franka_panda/scene.xml",
        *[f"src/cloud_edge_robot_arm/vision/{name}.py" for name in
          ("planner", "messages", "observations", "model_resolver", "capture", "top_grasp",
           "defaults", "frozen_model", "task_semantics")],
    ]
    return {name: _sha256((root / name).read_bytes()) for name in files}


def _valid_snapshot_fields(snapshot: Mapping[str, Any]) -> bool:
    from cloud_edge_robot_arm.vision.top_grasp import GRASP_CALIBRATION_ASSETS

    return (
        set(SNAPSHOT_FIELDS) <= set(snapshot)
        and not set(snapshot) - set(SNAPSHOT_FIELDS) - set(OPTIONAL_SNAPSHOT_FIELDS)
        and isinstance(snapshot.get("coordinate_system", "pixel"), str)
        and snapshot.get("coordinate_system", "pixel") in {"pixel", "normalized_1000"}
        and isinstance(snapshot.get("grasp_profile", "unconfigured"), str)
        and snapshot.get("grasp_profile", "unconfigured")
        in {"unconfigured", *GRASP_CALIBRATION_ASSETS}
    )


def summarize_chat_request(body: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the actual wire body without copying prompts or encoded images."""
    messages = body.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("chat messages must be a list")
    image_blobs: list[bytes] = []
    text_hashes: list[str] = []
    roles: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("chat message must be an object")
        roles.append(str(message.get("role", "")))
        text_hashes.append(_sha256(str(message.get("content", "")).encode("utf-8")))
        for encoded in message.get("images", []):
            if not isinstance(encoded, str):
                raise ValueError("image must be base64 text")
            image_blobs.append(base64.b64decode(encoded, validate=True))
    digests = [_sha256(blob) for blob in image_blobs]
    return {
        "model": body.get("model"),
        "stream": body.get("stream"),
        "think": body.get("think"),
        "message_roles": roles,
        "message_text_sha256": text_hashes,
        "image_count": len(image_blobs),
        "distinct_image_count": len(set(digests)),
        "image_sha256": digests,
        "image_bytes": [len(blob) for blob in image_blobs],
        "format_sha256": _sha256(json.dumps(body.get("format"), sort_keys=True).encode()),
        "options": body.get("options"),
    }


def can_freeze(report: Mapping[str, Any]) -> bool:
    """Require actual paired transport, strict geometry and GPU evidence on every call."""
    from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

    capture = report.get("capture", {})
    model = report.get("model", {})
    device = report.get("device", {})
    timing = report.get("timing", {})
    attempts = report.get("attempts", [])
    snapshot = report.get("snapshot", {})
    probe_config = report.get("probe_config", {})
    if not (
        report.get("source") == "mujoco_camera"
        and isinstance(capture, dict) and capture.get("synchronized") is True
        and isinstance(model, dict) and model.get("digest_matches") is True
        and model.get("quantization_matches") is True
        and model.get("vision") is True
        and isinstance(device, dict) and device.get("cuda") is True
        and isinstance(timing, dict) and timing.get("warm_samples", 0) >= 3
        and isinstance(attempts, list) and len(attempts) >= 4
        and isinstance(snapshot, dict) and _valid_snapshot_fields(snapshot)
        and calibration_asset_sha256(snapshot.get("grasp_profile")) is not None
        and isinstance(probe_config, dict) and set(probe_config) == set(PROBE_FIELDS)
        and probe_config.get("scenario_id") == "S01_NORMAL_STATIC"
        and model.get("name") == snapshot.get("model")
        and model.get("expected_digest") == snapshot.get("weight_digest")
        and isinstance(model.get("inherited_parameters"), str)
    ):
        return False
    asset_hash = calibration_asset_sha256(snapshot["grasp_profile"])
    try:
        sources = _source_fingerprints()
        if (
            report.get("source_fingerprints") != sources
            or sources["assets/robots/franka_panda/scene.xml"] != asset_hash
        ):
            return False
    except OSError:
        return False
    generation = snapshot.get("generation_parameters")
    if not isinstance(generation, dict):
        return False
    expected_options = dict(generation)
    expected_think = expected_options.pop("think", False)
    required = ("transport_two_images", "parsed", "grounded", "target_hit", "destination_hit")
    for attempt in attempts:
        if not isinstance(attempt, dict) or not all(attempt.get(key) is True for key in required):
            return False
        running = attempt.get("loaded_model_after_call")
        if not (
            isinstance(running, dict)
            and running.get("name") == snapshot["model"]
            and running.get("digest") == snapshot["weight_digest"]
            and type(running.get("size_vram")) is int and running["size_vram"] > 0
        ):
            return False
        evidence = attempt.get("observation_evidence")
        if not isinstance(evidence, dict):
            return False
        tcp = evidence.get("resolved_top_grasp_tcp")
        if not (
            evidence.get("top_grasp_offset_status") == "CALIBRATED_RGBD_TOP_GRASP_V1"
            and evidence.get("grasp_profile") == snapshot["grasp_profile"]
            and evidence.get("grasp_calibration_asset_sha256") == asset_hash
            and isinstance(tcp, dict) and set(tcp) == {"x", "y", "z"}
            and all(type(value) in {int, float} and math.isfinite(value) for value in tcp.values())
        ):
            return False
        summary = attempt.get("request_summary")
        expected = attempt.get("expected_request_summary")
        request_texts = attempt.get("request_texts")
        if not (
            isinstance(request_texts, list) and len(request_texts) == 2
            and all(isinstance(message, dict) and set(message) == {"role", "content"}
                    and isinstance(message["role"], str) and isinstance(message["content"], str)
                    for message in request_texts)
        ):
            return False
        if not (
            isinstance(summary, dict)
            and isinstance(expected, dict) and summary == expected
            and summary.get("message_roles") == [message["role"] for message in request_texts]
            and summary.get("message_text_sha256") == [
                _sha256(message["content"].encode("utf-8")) for message in request_texts
            ]
            and summary.get("model") == snapshot["model"]
            and summary.get("stream") is False
            and summary.get("think") is expected_think
            and summary.get("options") == expected_options
            and isinstance(summary.get("format_sha256"), str)
            and len(summary["format_sha256"]) == 64
            and isinstance(summary.get("message_text_sha256"), list)
            and len(summary["message_text_sha256"]) == 2
            and all(isinstance(value, str) and len(value) == 64
                    for value in summary["message_text_sha256"])
            and attempt.get("inherited_parameters") == model["inherited_parameters"]
        ):
            return False
    return True


def write_frozen_if_verified(
    target: Path, snapshot: Mapping[str, Any], report: Mapping[str, Any]
) -> bool:
    if not can_freeze(report):
        return False
    if not _valid_snapshot_fields(snapshot):
        raise ValueError("snapshot must have exactly the immutable model fields")
    if dict(snapshot) != report.get("snapshot"):
        raise ValueError("snapshot differs from verified report")
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot_text = _json_text(dict(snapshot))
    evidence_target = target.with_name(f"{target.stem}-evidence.json")
    frozen_evidence = {
        "snapshot_sha256": _sha256(snapshot_text.encode("utf-8")),
        "source_fingerprints": report["source_fingerprints"],
        "inherited_parameters": report["model"]["inherited_parameters"],
        "probe_config": report["probe_config"],
        "effective_requests": [attempt["request_summary"] for attempt in report["attempts"]],
        "request_evidence": [
            {key: attempt[key] for key in (
                "capture_path", "observation", "request_texts", "request_summary",
                "expected_request_summary",
            )}
            for attempt in report["attempts"]
        ],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=".model-frozen-", suffix=".tmp",
        dir=target.parent, delete=False,
    ) as stream:
        staged = Path(stream.name)
        stream.write(snapshot_text)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=".model-frozen-evidence-", suffix=".tmp",
        dir=target.parent, delete=False,
    ) as stream:
        staged_evidence = Path(stream.name)
        stream.write(_json_text(frozen_evidence))
    evidence_published = False
    try:
        # Publish the complete evidence first; the exclusive snapshot link is the commit point.
        os.link(staged_evidence, evidence_target)
        evidence_published = True
        os.link(staged, target)
    except BaseException:
        if evidence_published:
            evidence_target.unlink()
        raise
    finally:
        staged.unlink()
        staged_evidence.unlink()
    return True


def verify_frozen_bundle(output: Path) -> bool:
    """Read-only verification before a consumer resolves the frozen snapshot."""
    try:
        frozen = output / "model-frozen.json"
        sidecar = output / "model-frozen-evidence.json"
        report_raw = (output / "probe-report.json").read_bytes()
        snapshot_raw = frozen.read_bytes()
        sidecar_raw = sidecar.read_bytes()
        report = json.loads(report_raw)
        snapshot = json.loads(snapshot_raw)
        evidence = json.loads(sidecar_raw)
        if not all(isinstance(value, dict) for value in (report, snapshot, evidence)):
            return False
        return bool(
            (output / "probe-report.sha256").read_text().strip() == _sha256(report_raw)
            and report.get("status") == "PASS"
            and Path(str(report.get("frozen_path", ""))).resolve() == frozen.resolve()
            and Path(str(report.get("frozen_evidence_path", ""))).resolve() == sidecar.resolve()
            and report.get("frozen_sha256") == _sha256(snapshot_raw)
            and report.get("frozen_evidence_sha256") == _sha256(sidecar_raw)
            and evidence.get("snapshot_sha256") == _sha256(snapshot_raw)
            and snapshot == report.get("snapshot")
            and evidence.get("source_fingerprints") == report.get("source_fingerprints")
            and evidence.get("source_fingerprints") == _source_fingerprints()
            and evidence.get("probe_config") == report.get("probe_config")
            and can_freeze(report)
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def archive_previous_owned_freeze(output: Path) -> Path | None:
    """Move only a freeze authenticated by our previous PASS report out of the next run."""
    frozen = output / "model-frozen.json"
    if not frozen.exists():
        return None
    previous_report_path = output / "probe-report.json"
    report_digest_path = output / "probe-report.sha256"
    evidence = output / "model-frozen-evidence.json"
    try:
        previous = json.loads(previous_report_path.read_text(encoding="utf-8"))
        owned = (
            isinstance(previous, dict)
            and previous.get("status") == "PASS"
            and Path(str(previous.get("frozen_path", ""))).resolve() == frozen.resolve()
            and previous.get("frozen_sha256") == _sha256(frozen.read_bytes())
        )
        if owned and (evidence.exists() or previous.get("frozen_evidence_path")):
            owned = (
                evidence.is_file()
                and Path(str(previous.get("frozen_evidence_path", ""))).resolve()
                == evidence.resolve()
                and previous.get("frozen_evidence_sha256") == _sha256(evidence.read_bytes())
            )
        if owned and report_digest_path.exists():
            owned = report_digest_path.read_text().strip() == _sha256(
                previous_report_path.read_bytes()
            )
    except (OSError, ValueError, TypeError):
        owned = False
    if not owned:
        raise RuntimeError(
            "cannot establish ownership of existing model-frozen.json; use a fresh output directory"
        )
    archive = output / "previous-probes" / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "-" + _sha256(frozen.read_bytes())[:12]
    )
    archive.mkdir(parents=True, exist_ok=False)
    previous_report_path.replace(archive / "probe-report.json")
    frozen.replace(archive / "model-frozen.json")
    if evidence.exists():
        evidence.replace(archive / "model-frozen-evidence.json")
    if report_digest_path.exists():
        report_digest_path.replace(archive / "probe-report.sha256")
    return archive


def _read_candidate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "probe" not in payload:
        raise ValueError("candidate must contain exactly snapshot fields and probe")
    snapshot = {key: value for key, value in payload.items() if key != "probe"}
    if not _valid_snapshot_fields(snapshot):
        raise ValueError("candidate has invalid snapshot fields or coordinate_system")
    probe = payload["probe"]
    if not isinstance(probe, dict) or set(probe) != set(PROBE_FIELDS):
        raise ValueError("probe settings must contain scenario_id, seed, instruction and warm_runs")
    if probe["scenario_id"] != "S01_NORMAL_STATIC":
        raise ValueError(
            "probe scenario_id must be S01_NORMAL_STATIC; other scenes need a scene probe"
        )
    if snapshot["provider"] != "ollama" or snapshot["endpoint"] != "http://127.0.0.1:11434":
        raise ValueError("probe only permits the local Ollama loopback endpoint")
    if not isinstance(snapshot["weight_digest"], str) or len(snapshot["weight_digest"]) != 64:
        raise ValueError("candidate requires a 64-character model digest")
    int(snapshot["weight_digest"], 16)
    if snapshot["image_size"] != [320, 240]:
        raise ValueError("probe image_size must be the fixed 320x240 research resolution")
    if type(probe["warm_runs"]) is not int or not 3 <= probe["warm_runs"] <= 10:
        raise ValueError("warm_runs must be an integer between 3 and 10")
    if type(probe["seed"]) is not int or not isinstance(probe["instruction"], str):
        raise ValueError("invalid probe seed or instruction")
    if not probe["instruction"].strip():
        raise ValueError("probe instruction cannot be blank")
    return snapshot, probe


def _local_json(endpoint: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if endpoint != "http://127.0.0.1:11434":
        raise ValueError("local metadata request cannot leave loopback")
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        endpoint + path,
        data=data,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=15) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("local Ollama metadata response exceeded size limit")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("local Ollama response must be an object")
    return parsed


def _model_entry(endpoint: str, model_name: str) -> dict[str, Any]:
    models = _local_json(endpoint, "/api/tags").get("models", [])
    if not isinstance(models, list):
        raise ValueError("local model registry response is malformed")
    matching = [
        item for item in models if isinstance(item, dict) and item.get("name") == model_name
    ]
    if len(matching) != 1:
        raise RuntimeError("candidate model is not installed exactly once")
    return matching[0]


def _running_model(endpoint: str, model_name: str) -> dict[str, Any] | None:
    models = _local_json(endpoint, "/api/ps").get("models", [])
    if not isinstance(models, list):
        raise ValueError("local running-model response is malformed")
    return next(
        (item for item in models if isinstance(item, dict) and item.get("name") == model_name),
        None,
    )


def _gpu_status() -> dict[str, Any]:
    command = [
        "nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
    row = result.stdout.strip().splitlines()[0].split(", ")
    if len(row) != 4:
        raise ValueError("unexpected nvidia-smi CSV output")
    return {
        "name": row[0], "driver_version": row[1],
        "total_mib": int(row[2]), "used_mib": int(row[3]),
    }


def _gpu_compute_processes() -> list[str]:
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,used_gpu_memory",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return result.stdout.strip().splitlines()


def _unload_model(endpoint: str, model_name: str) -> dict[str, Any]:
    binary = shutil.which("ollama") or str(Path.home() / ".local/bin/ollama")
    result = subprocess.run(
        [binary, "stop", model_name], capture_output=True, text=True, timeout=30,
        env={**os.environ, "OLLAMA_HOST": endpoint, "OLLAMA_NO_CLOUD": "1"},
    )
    after = _running_model(endpoint, model_name)
    return {
        "command_exit_code": result.returncode,
        "stdout": result.stdout.strip()[:500],
        "stderr": result.stderr.strip()[:500],
        "unloaded": after is None,
    }


def _percentile_ms(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("latency percentile requires measured samples")
    values = sorted(values)
    rank = (len(values) - 1) * fraction
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    return round(values[lower] + (values[upper] - values[lower]) * (rank - lower), 3)


def _pixel_hit(
    frame: Any, value: Any, expected_label: str
) -> tuple[bool, dict[str, Any]]:
    observation = frame.observation
    if (
        not isinstance(value, (list, tuple)) or len(value) != 2
        or any(type(coordinate) is not int for coordinate in value)
    ):
        return False, {"reason": "pixel is not a two-integer coordinate"}
    pixel = (value[0], value[1])
    try:
        point = observation.world_point(pixel)
    except ValueError as exc:
        return False, {"reason": str(exc), "pixel": list(pixel)}
    geom_id = frame.instance_ids[pixel[1] * observation.width + pixel[0]]
    actual_label = frame.instance_labels.get(geom_id)
    return actual_label == expected_label, {
        "pixel": list(pixel), "world_surface_point_m": point.model_dump(mode="json"),
        "offline_geom_id": geom_id, "offline_geom_label": actual_label,
        "expected_geom_label": expected_label,
    }


def _original_decision_pixel(
    planner: Any, frame: Any, evidence: Mapping[str, Any], decision: Mapping[str, Any], kind: str,
) -> Any:
    """Prefer the planner's recorded original pixel, otherwise use its explicit protocol."""
    from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel

    original_key = f"original_pixel_{kind}"
    if original_key in evidence:
        return evidence[original_key]
    snapshot = getattr(planner, "model_snapshot", None)
    value = decision.get(f"{kind}_pixel")
    if (
        not isinstance(value, (list, tuple)) or len(value) != 2
        or any(type(coordinate) is not int for coordinate in value)
    ):
        return None
    try:
        return model_to_observation_pixel(
            (value[0], value[1]), frame.observation,
            image_size=getattr(snapshot, "image_size", None),
            coordinate_system=getattr(snapshot, "coordinate_system", "pixel"),
        )
    except (TypeError, ValueError):
        return None


def _attempt(
    *, planner: Any, request: Any, frame: Any, index: int,
    output: Path, endpoint: str, model_name: str,
) -> dict[str, Any]:
    from cloud_edge_robot_arm.vision.capture import save_captured_frame
    from cloud_edge_robot_arm.vision.messages import build_visual_messages
    from cloud_edge_robot_arm.vision.planner import VisualDecision

    capture_dir = output / "captures" / f"attempt-{index:02d}"
    save_captured_frame(frame, capture_dir)
    snapshot = getattr(planner, "model_snapshot", None)
    schema = VisualDecision.model_json_schema()
    expected_messages = build_visual_messages(
        request.user_instruction, request.observation,
        image_size=getattr(snapshot, "image_size", None),
        coordinate_system=getattr(snapshot, "coordinate_system", "pixel"),
        decision_schema=schema,
    )
    generation = dict(getattr(snapshot, "generation_parameters", {
        "temperature": 0, "num_ctx": 4096, "num_predict": 512,
    }))
    expected_summary = summarize_chat_request({
        "model": model_name, "messages": expected_messages, "stream": False,
        "format": schema, "think": generation.pop("think", False), "options": generation,
    })
    record: dict[str, Any] = {
        "index": index, "phase": "cold" if index == 1 else "warm",
        "observation": frame.observation.evidence(),
        "physics_state_hash": frame.physics_state_hash,
        "pass_state_hashes": list(frame.pass_state_hashes),
        "capture_path": str(capture_dir),
        "transport_two_images": False,
        "parsed": False, "grounded": False, "target_hit": False, "destination_hit": False,
        "ttft": "NOT_MEASURED",
        "expected_request_summary": expected_summary,
    }
    captured_call: dict[str, Any] = {}
    original_post = cast(Callable[[str, dict[str, Any]], dict[str, Any]], planner._post)

    def instrumented_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path != "/api/chat":
            response = original_post(path, body)
            if path == "/api/show":
                captured_call["inherited_parameters"] = response.get("parameters", "")
            return response
        captured_call["request"] = summarize_chat_request(body)
        captured_call["request_texts"] = [
            {"role": message["role"], "content": message["content"]}
            for message in body["messages"]
        ]
        response = original_post(path, body)
        captured_call["response"] = response
        return response

    planner._post = instrumented_post
    gpu_samples: list[dict[str, Any]] = []
    gpu_stop = threading.Event()

    def sample_gpu() -> None:
        while not gpu_stop.is_set():
            try:
                gpu_samples.append(_gpu_status())
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            gpu_stop.wait(0.2)

    sampler = threading.Thread(target=sample_gpu, daemon=True)
    sampler.start()
    started = time.monotonic_ns()
    try:
        draft = planner.plan(request)
        record["observed_scene_present"] = draft.observed_scene is not None
        record["raw_model_output"] = draft.raw_text
        record["parse_error"] = draft.parse_error
        record["parsed"] = draft.parse_error is None and draft.observed_scene is not None
        record["grounded"] = record["parsed"] and draft.parsed_json is not None
        evidence = draft.observation_evidence
        record["observation_evidence"] = evidence
        decision = evidence.get("visual_decision", {})
        if not isinstance(decision, dict):
            decision = {}
        record["visual_decision"] = decision
        record["target_hit"], record["target_offline_check"] = _pixel_hit(
            frame, _original_decision_pixel(planner, frame, evidence, decision, "target"),
            "object_geom",
        )
        record["destination_hit"], record["destination_offline_check"] = _pixel_hit(
            frame, _original_decision_pixel(planner, frame, evidence, decision, "destination"),
            "target_region_geom",
        )
        record["contract_step_count"] = (
            len(draft.parsed_json.get("steps", [])) if draft.parsed_json else 0
        )
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        record["wall_latency_ms"] = round((time.monotonic_ns() - started) / 1_000_000, 3)
        planner._post = original_post
        gpu_stop.set()
        sampler.join(timeout=3)
    record["gpu_sample_count"] = len(gpu_samples)
    record["gpu_peak_used_mib"] = (
        max(item["used_mib"] for item in gpu_samples) if gpu_samples else None
    )
    try:
        record["gpu_compute_processes_after"] = _gpu_compute_processes()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        record["gpu_process_query_error"] = type(exc).__name__
    summary = captured_call.get("request", {})
    record["request_summary"] = summary
    record["request_texts"] = captured_call.get("request_texts", [])
    record["inherited_parameters"] = captured_call.get("inherited_parameters")
    response = captured_call.get("response", {})
    if response:
        record["response"] = response
        record["ollama_durations_ms"] = {
            key: round(response[key] / 1_000_000, 3)
            for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")
            if type(response.get(key)) is int
        }
    expected_image_hashes = expected_summary["image_sha256"]
    record["transport_two_images"] = (
        summary.get("model") == model_name
        and summary.get("stream") is False
        and summary.get("image_count") == 2
        and summary.get("distinct_image_count") == 2
        and summary.get("image_sha256") == expected_image_hashes
    )
    record["loaded_model_after_call"] = _running_model(endpoint, model_name)
    return record


def run_probe(config_path: Path, output: Path) -> dict[str, Any]:
    # MuJoCo selects the offscreen backend when imported. Set this before imports.
    os.environ.setdefault("MUJOCO_GL", "egl")
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )

    output.mkdir(parents=True, exist_ok=True)
    try:
        previous_archive = archive_previous_owned_freeze(output)
    except RuntimeError as exc:
        return {
            "status": "BLOCKED", "blocked_reason": str(exc),
            "report_path": None, "frozen_path": None,
        }
    snapshot_data, probe_data = _read_candidate(config_path)
    report: dict[str, Any] = {
        "status": "BLOCKED", "started_at": datetime.now(UTC).isoformat(),
        "candidate_path": str(config_path),
        "candidate_sha256": _sha256(config_path.read_bytes()),
        "previous_probe_archive": str(previous_archive) if previous_archive else None,
        "snapshot": snapshot_data,
        "probe_config": probe_data,
        "source_fingerprints": _source_fingerprints(),
        "source": None,
        "capture": {"synchronized": False},
        "model": {"digest_matches": False, "vision": False},
        "device": {"cuda": False},
        "attempts": [],
        "timing": {"ttft": "NOT_MEASURED", "warm_samples": 0},
    }
    report_path = output / "probe-report.json"
    report["report_path"] = str(report_path)
    try:
        snapshot = ModelConfigSnapshot(
            **{**snapshot_data, "image_size": tuple(snapshot_data["image_size"])}
        )
        endpoint = snapshot_data["endpoint"]
        model_name = snapshot_data["model"]
        entry = _model_entry(endpoint, model_name)
        show = _local_json(endpoint, "/api/show", {"model": model_name})
        version = _local_json(endpoint, "/api/version")
        digest_matches = entry.get("digest") == snapshot_data["weight_digest"]
        quantization_matches = (
            entry.get("details", {}).get("quantization_level")
            == snapshot_data["quantization"]
        )
        vision = "vision" in show.get("capabilities", [])
        report["model"] = {
            "name": model_name, "installed_digest": entry.get("digest"),
            "expected_digest": snapshot_data["weight_digest"],
            "digest_matches": digest_matches,
            "quantization": entry.get("details", {}).get("quantization_level"),
            "quantization_matches": quantization_matches,
            "capabilities": show.get("capabilities", []), "vision": vision,
            "ollama_version": version.get("version"),
            "size_bytes": entry.get("size"),
            "inherited_parameters": show.get("parameters", ""),
        }
        report["device"] = {"cuda": False, "gpu_before": _gpu_status()}
        if not digest_matches or not quantization_matches or not vision:
            raise RuntimeError(
                "installed model digest, quantization or vision capability differs from candidate"
            )
        report["cold_unload"] = _unload_model(endpoint, model_name)
        if not report["cold_unload"]["unloaded"]:
            raise RuntimeError("model was not unloaded; cold start cannot be measured")
        report["device"]["gpu_after_unload"] = _gpu_status()
        planner = resolve_visual_planner(snapshot)
        config = SimulatorConfig(
            camera_width=snapshot_data["image_size"][0],
            camera_height=snapshot_data["image_size"][1],
            render_rgb=True, render_depth=True,
            domain_randomization=False, seed=probe_data["seed"],
        )
        with MuJoCoCaptureSession(config) as session:
            for index in range(1, probe_data["warm_runs"] + 2):
                frame = session.capture_with_instances()
                observation = frame.observation
                report["source"] = observation.source
                report["capture"] = {
                    "synchronized": bool(report["capture"].get("synchronized", True))
                    if index > 1 else True,
                    "image_size": [observation.width, observation.height],
                    "calibration_version": observation.calibration_version,
                    "episode_id": observation.episode_id,
                }
                report["capture"]["synchronized"] &= (
                    len(frame.pass_state_hashes) == 3
                    and len(set(frame.pass_state_hashes)) == 1
                    and frame.pass_state_hashes[0] == frame.physics_state_hash
                    and observation.width == snapshot_data["image_size"][0]
                    and observation.height == snapshot_data["image_size"][1]
                )
                request = InitialPlanningRequest(
                    request_id=f"real-rgbd-probe-{index:02d}",
                    user_instruction=probe_data["instruction"],
                    scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
                    observation=observation,
                )
                attempt = _attempt(
                    planner=planner, request=request, frame=frame,
                    index=index, output=output, endpoint=endpoint, model_name=model_name,
                )
                report["attempts"].append(attempt)
                print(
                    f"{attempt['phase']} {index}: {attempt['wall_latency_ms']} ms, "
                    f"parsed={attempt['parsed']}, target={attempt['target_hit']}, "
                    f"destination={attempt['destination_hit']}",
                    flush=True,
                )
        gpu_after = _gpu_status()
        running = _running_model(endpoint, model_name)
        report["device"].update({
            "gpu_after": gpu_after, "ollama_ps": running,
            "gpu_peak_used_mib": max(
                [gpu_after["used_mib"]]
                + [item["gpu_peak_used_mib"] for item in report["attempts"]
                   if item.get("gpu_peak_used_mib") is not None]
            ),
            "gpu_compute_processes_after": _gpu_compute_processes(),
            "cuda": bool(running and int(running.get("size_vram", 0)) > 0),
        })
        warm = [
            float(item["wall_latency_ms"]) for item in report["attempts"][1:]
            if "response" in item
        ]
        report["timing"] = {
            "cold_wall_ms": report["attempts"][0]["wall_latency_ms"],
            "warm_wall_ms": warm,
            "warm_samples": len(warm),
            "warm_p50_ms": _percentile_ms(warm, 0.5) if warm else None,
            "warm_p95_ms": _percentile_ms(warm, 0.95) if warm else None,
            "warm_mean_ms": round(statistics.mean(warm), 3) if warm else None,
            "ttft": "NOT_MEASURED",
            "stream": False,
        }
        report["status"] = "PASS" if can_freeze(report) else "BLOCKED"
        if report["status"] == "BLOCKED":
            report["blocked_reason"] = (
                "real model transport, strict decision, geometry or GPU gate failed"
            )
        elif write_frozen_if_verified(output / "model-frozen.json", snapshot_data, report):
            report["frozen_path"] = str(output / "model-frozen.json")
            report["frozen_sha256"] = _sha256((output / "model-frozen.json").read_bytes())
            report["frozen_evidence_path"] = str(output / "model-frozen-evidence.json")
            report["frozen_evidence_sha256"] = _sha256(
                (output / "model-frozen-evidence.json").read_bytes()
            )
    except Exception as exc:
        report["status"] = "BLOCKED"
        report["blocked_reason"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report_path.write_text(_json_text(report), encoding="utf-8")
        (output / "probe-report.sha256").write_text(_sha256(report_path.read_bytes()) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_MODEL_CONFIG
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_FROZEN_DIR)
    parser.add_argument(
        "--verify-frozen", action="store_true", help="Verify a bundle without calls"
    )
    args = parser.parse_args()
    if args.verify_frozen:
        verified = verify_frozen_bundle(args.output)
        print(_json_text({
            "status": "VERIFIED" if verified else "BLOCKED", "output": str(args.output),
        }))
        return 0 if verified else 1
    report = run_probe(args.config, args.output)
    print(_json_text({
        "status": report["status"],
        "report": report.get("report_path"),
        "frozen": report.get("frozen_path"),
        "blocked_reason": report.get("blocked_reason"),
    }))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
