"""Probe a selected cloud profile with real synchronized RGB-D, without dispatch.

The default CLI records NOT_STARTED. --execute runs the service and renderer;
software tests and dry runs never create a role acceptance snapshot.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud_edge_robot_arm.model_control.models import SecretStoreKind
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    RoleProviderSnapshot,
    cloud_request_settings,
    configuration_hash,
    resolve_cloud_role,
)
from scripts.probe_rgbd_model import _pixel_hit, _source_fingerprints, summarize_chat_request

ROOT = Path(__file__).resolve().parents[1]


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, value: object) -> str:
    raw = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return _sha(raw)


def summarize_role_request(body: Mapping[str, Any]) -> dict[str, Any]:
    """Read the production compatible wire body, retaining byte/hash evidence."""
    canonical = dict(body)
    messages = []
    for message in body.get("messages", []):
        if not isinstance(message, dict):
            raise ValueError("invalid request message")
        current = dict(message)
        content = current.get("content")
        if isinstance(content, list):
            text, images = [], []
            for part in content:
                if part.get("type") == "text":
                    text.append(part["text"])
                elif part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    if not isinstance(url, str) or not url.startswith("data:image/png;base64,"):
                        raise ValueError("probe requires inline PNG images")
                    encoded = url.split(",", 1)[1]
                    base64.b64decode(encoded, validate=True)
                    images.append(encoded)
            current["content"] = "\n".join(text)
            current["images"] = images
        messages.append(current)
    canonical["messages"] = messages
    summary = summarize_chat_request(canonical)
    summary["serialized_sent_bytes"] = len(json.dumps(dict(body)).encode())
    summary["wire_sha256"] = _sha(json.dumps(dict(body)).encode())
    summary["response_format"] = body.get("response_format")
    summary["generation_parameters"] = {
        key: body[key] for key in ("temperature", "max_tokens") if key in body
    }
    return summary


def _hash_sources(paths: list[str]) -> dict[str, str]:
    if not paths:
        raise ValueError("source_paths must not be empty")
    sources = {}
    for name in paths:
        if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("source path must be repository relative")
        target = (ROOT / name).resolve()
        if not target.is_relative_to(ROOT):
            raise ValueError("source path leaves repository")
        sources[name] = _sha(target.read_bytes())
    return sources


def source_fingerprints() -> dict[str, str]:
    return _source_fingerprints() | _hash_sources(
        [
            "src/cloud_edge_robot_arm/vision/role_models.py",
            "scripts/probe_rgbd_roles.py",
            "src/cloud_edge_robot_arm/model_control/service.py",
            "src/cloud_edge_robot_arm/model_control/endpoint_security.py",
        ]
    )


def read_role_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or set(config) != {
        "schema_version",
        "cloud",
        "edge",
        "device",
        "probe",
    }:
        raise ValueError("invalid role config fields")
    if config["schema_version"] != "ced.roles.v1":
        raise ValueError("invalid role config schema")
    if set(config["cloud"]) != {
        "profile_id",
        "model_family",
        "available_model_ids",
        "image_size",
        "coordinate_system",
        "grasp_profile",
    }:
        raise ValueError("cloud config must reference a profile, never credentials")
    if config["cloud"]["model_family"] != "qwen3.8-max" or config["cloud"]["image_size"] != [
        320,
        240,
    ]:
        raise ValueError("cloud requires Max family and fixed 320x240 RGB-D")
    if not isinstance(config["cloud"]["available_model_ids"], list):
        raise ValueError("available_model_ids must be provider-advertised IDs")
    if set(config["edge"]) != {
        "provider_id",
        "provider_location",
        "model_id",
        "source_paths",
        "policy",
    }:
        raise ValueError("invalid edge provider config")
    if config["edge"]["model_id"] is not None:
        raise ValueError("current edge provider is rules without a forced model")
    if set(config["device"]) != {"source_paths"}:
        raise ValueError("invalid device config")
    probe = config["probe"]
    if set(probe) != {"scenario_id", "seed", "instruction", "warm_runs"}:
        raise ValueError("invalid probe config")
    if probe["scenario_id"] != "S01_NORMAL_STATIC" or type(probe["seed"]) is not int:
        raise ValueError("role probe requires S01 and integer seed")
    if type(probe["warm_runs"]) is not int or not 3 <= probe["warm_runs"] <= 10:
        raise ValueError("probe requires 3 to 10 warm runs")
    if not isinstance(probe["instruction"], str) or not probe["instruction"].strip():
        raise ValueError("probe instruction cannot be empty")
    return cast(dict[str, Any], config)


def validate_role_probe_bindings(report: Mapping[str, Any]) -> bool:
    """Validate the full nominal role/config binding, independent of task success."""
    try:
        cloud = RoleProviderSnapshot(**report["bundle"]["cloud_snapshot"])
        bundle = RoleModelBundle(
            cloud,
            report["bundle"]["edge_provider_id"],
            report["bundle"]["edge_provider_hash"],
            report["bundle"]["device_pipeline_hash"],
        )
        edge = RoleProviderSnapshot(**report["edge_snapshot"])
        device_sources = report["device_source_hashes"]
        settings = report["request_settings"]
        if _sha(Path(report["config_path"]).read_bytes()) != report["config_sha256"]:
            return False
        if cloud.role != "CLOUD" or cloud.provider_location != "REMOTE_SERVICE":
            return False
        if bundle.digest() != report["bundle_hash"]:
            return False
        if edge.role != "EDGE" or edge.provider_id != bundle.edge_provider_id:
            return False
        if edge.digest() != bundle.edge_provider_hash:
            return False
        if dict(cloud.source_hashes) != source_fingerprints():
            return False
        if dict(edge.source_hashes) != _hash_sources(list(edge.source_hashes)):
            return False
        if device_sources != _hash_sources(list(device_sources)):
            return False
        if configuration_hash(device_sources) != bundle.device_pipeline_hash:
            return False
        if configuration_hash(report["edge_policy"]) != edge.request_config_hash:
            return False
        if configuration_hash(settings) != cloud.request_config_hash:
            return False
        if settings["model"] != cloud.model_id or settings["allow_paid"] is not True:
            return False
        if report["final_request_settings"] != settings:
            return False
        for attempt in report["attempts"]:
            if attempt["actual_request_settings"] != settings:
                return False
        return True
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _validate_wire_artifacts(attempt: Mapping[str, Any]) -> bool:
    try:
        directory = Path(attempt["artifact_directory"])
        request_raw = (directory / "request.raw").read_bytes()
        response_raw = (directory / "response.raw").read_bytes()
        return (
            not attempt.get("wire_artifact_suppressed", False)
            and len(request_raw) <= 2_000_000
            and len(response_raw) <= 2_000_000
            and _sha(request_raw) == attempt["request_sha256"]
            and _sha(response_raw) == attempt["response_sha256"]
            and len(request_raw) == attempt["serialized_sent_bytes"]
            and len(response_raw) == attempt["serialized_received_bytes"]
            and summarize_role_request(json.loads(request_raw)) == attempt["request_summary"]
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False


def can_accept_role_probe(report: Mapping[str, Any]) -> bool:
    """Nominal role-probe gate; never means physical, edge, or final acceptance."""
    try:
        if report.get("source") != "mujoco_camera" or report.get("transport") != "REAL_HTTP":
            return False
        if report["capture"]["synchronized"] is not True:
            return False
        if report["capture"]["image_size"] != [320, 240]:
            return False
        if not validate_role_probe_bindings(report):
            return False
        cloud = RoleProviderSnapshot(**report["bundle"]["cloud_snapshot"])
        if cloud.role != "CLOUD" or cloud.provider_location != "REMOTE_SERVICE":
            return False
        if dict(cloud.source_hashes) != source_fingerprints():
            return False
        attempts = report["attempts"]
        if (
            not isinstance(attempts, list)
            or len(attempts) != report["probe_config"]["warm_runs"] + 1
        ):
            return False
        if report["probe_config"]["warm_runs"] < 3:
            return False
        for attempt in attempts:
            if not _validate_wire_artifacts(attempt):
                return False
            if not all(
                attempt.get(key) is True
                for key in (
                    "transport_two_images",
                    "parsed",
                    "grounded",
                    "target_hit",
                    "destination_hit",
                )
            ):
                return False
            summary = attempt["request_summary"]
            if summary != attempt["expected_request_summary"] or summary["model"] != cloud.model_id:
                return False
            if summary["image_count"] != 2 or summary["distinct_image_count"] != 2:
                return False
            if summary["serialized_sent_bytes"] <= 0 or attempt["serialized_received_bytes"] <= 0:
                return False
            evidence = attempt["observation_evidence"]
            if evidence["top_grasp_offset_status"] != "CALIBRATED_RGBD_TOP_GRASP_V1":
                return False
            if evidence["cloud_snapshot_hash"] != cloud.digest():
                return False
        return True
    except (KeyError, TypeError, ValueError, OSError):
        return False


def run_probe(
    config_path: Path,
    output: Path,
    *,
    service: ModelControlService | None = None,
    profile_id: str | None = None,
    execute: bool = False,
    allow_paid: bool = False,
) -> dict[str, Any]:
    """Use a caller's model-control service; no activation, fallback, or actuation."""
    config = read_role_config(config_path)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("role probe requires a fresh output directory")
    report: dict[str, Any] = {
        "schema_version": "ced.role-probe.v1",
        "status": "NOT_STARTED",
        "source": None,
        "transport": None,
        "capture": {"synchronized": False},
        "attempts": [],
        "started_at": datetime.now(UTC).isoformat(),
        "probe_config": config["probe"],
        "config_sha256": _sha(config_path.read_bytes()),
        "config_path": str(config_path.resolve()),
        "bundle": None,
        "acceptance_scope": "nominal cloud RGB-D planning probe only",
        "physical_acceptance": False,
        "edge_acceptance": False,
        "dispatch": False,
        "billing_cost": None,
        "pure_inference_duration_s": None,
        "planned_attempt_count": config["probe"]["warm_runs"] + 1,
    }
    try:
        selected = profile_id or config["cloud"]["profile_id"]
        if not execute:
            report["reason"] = "execution not requested; no service or renderer contacted"
        elif service is None or not selected:
            raise ValueError(
                "probe requires an existing model-control service and selected profile"
            )
        else:
            if not service.secret_store.has_secret(selected):
                raise ValueError("selected cloud profile secret is unavailable")
            cloud_config, edge_config = config["cloud"], config["edge"]
            planner, cloud = resolve_cloud_role(
                service,
                selected,
                source_hashes=source_fingerprints(),
                allow_paid=allow_paid,
                image_size=tuple(cloud_config["image_size"]),
                coordinate_system=cloud_config["coordinate_system"],
                grasp_profile=cloud_config["grasp_profile"],
                available_model_ids=cloud_config["available_model_ids"],
            )
            edge = RoleProviderSnapshot(
                role="EDGE",
                provider_id=edge_config["provider_id"],
                provider_location=edge_config["provider_location"],
                model_id=None,
                revision=None,
                weight_digest=None,
                quantization=None,
                request_config_hash=configuration_hash(edge_config["policy"]),
                source_hashes=_hash_sources(edge_config["source_paths"]),
            )
            device_sources = _hash_sources(config["device"]["source_paths"])
            request_settings = cloud_request_settings(planner)
            bundle = RoleModelBundle(
                cloud,
                edge.provider_id,
                edge.digest(),
                configuration_hash(device_sources),
            )
            report.update(
                bundle=bundle.evidence(),
                bundle_hash=bundle.digest(),
                edge_snapshot=edge.evidence(),
                edge_policy=edge_config["policy"],
                device_source_hashes=device_sources,
                request_settings=request_settings,
            )
            if cloud.provider_location != "REMOTE_SERVICE" or not allow_paid:
                raise ValueError("real cloud probe requires a remote profile and --allow-paid")
            # Import renderer only after config/profile/payment boundaries succeed.
            os.environ.setdefault("MUJOCO_GL", "egl")
            from cloud_edge_robot_arm.cloud.planning.models import (
                InitialPlanningRequest,
                SceneSummary,
            )
            from cloud_edge_robot_arm.simulation.config import SimulatorConfig
            from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

            simulator = SimulatorConfig(
                camera_width=320,
                camera_height=240,
                render_rgb=True,
                render_depth=True,
                domain_randomization=False,
                seed=config["probe"]["seed"],
            )
            report["transport"] = "REAL_HTTP"
            with MuJoCoCaptureSession(simulator) as session:
                for index in range(config["probe"]["warm_runs"] + 1):
                    frame = session.capture_with_instances()
                    synchronized = len(frame.pass_state_hashes) == 3 and (
                        set(frame.pass_state_hashes) == {frame.physics_state_hash}
                    )
                    report["source"] = frame.observation.source
                    report["capture"] = {
                        "synchronized": synchronized
                        and (index == 0 or report["capture"]["synchronized"]),
                        "image_size": [320, 240],
                    }
                    if not synchronized:
                        raise ValueError("capture passes are not synchronized")
                    request = InitialPlanningRequest(
                        request_id=f"cloud-role-probe-{index:02d}",
                        user_instruction=config["probe"]["instruction"],
                        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
                        observation=frame.observation,
                    )
                    attempt = _attempt(
                        planner,
                        request,
                        frame,
                        output,
                        index,
                        cloud,
                        request_settings=request_settings,
                    )
                    report["attempts"].append(attempt)
                    if attempt["status"] == "BLOCKED":
                        raise RuntimeError("cloud attempt failed; preserve unexecuted denominator")
            report["final_request_settings"] = cloud_request_settings(planner)
            report["status"] = "PASS" if can_accept_role_probe(report) else "FAIL"
    except Exception as exc:
        # Endpoint, HTTP errors and credential-bearing exception text are never persisted.
        report.update(status="BLOCKED", blocked_reason=type(exc).__name__)
    report["unexecuted_attempt_count"] = report["planned_attempt_count"] - len(report["attempts"])
    report["finished_at"] = datetime.now(UTC).isoformat()
    digest = _write(output / "role-probe-report.json", report)
    (output / "role-probe-report.sha256").write_text(digest + "\n")
    if report["status"] == "PASS":
        _write(output / "roles-frozen.json", report["bundle"])
    return report


def _attempt(
    planner: Any,
    request: Any,
    frame: Any,
    output: Path,
    index: int,
    cloud: RoleProviderSnapshot,
    *,
    request_settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.vision.capture import save_captured_frame
    from cloud_edge_robot_arm.vision.messages import build_visual_messages
    from cloud_edge_robot_arm.vision.planner import VisualDecision, compatible_messages

    directory = output / f"attempt-{index:02d}"
    directory.mkdir()
    save_captured_frame(frame, directory)
    settings = dict(request_settings or cloud_request_settings(planner))
    messages = build_visual_messages(
        request.user_instruction,
        frame.observation,
        image_size=tuple(settings["image_size"]),
        coordinate_system=settings["coordinate_system"],
        decision_schema=VisualDecision.model_json_schema(),
    )
    expected = summarize_role_request(
        {
            "model": settings["model"],
            "messages": compatible_messages(messages),
            "temperature": settings["generation_parameters"]["temperature"],
            "max_tokens": settings["generation_parameters"]["num_predict"],
            "response_format": {"type": "json_object"},
        }
    )
    actual: dict[str, Any] = {"artifact_directory": str(directory.resolve())}
    # The transport ledger measures the actual received raw bytes before parsing.
    ledger = CostLedger()
    previous_ledger = planner.cost_ledger
    planner.cost_ledger = ledger
    previous_observer = planner.raw_transport_observer

    def observe(phase: str, path: str, raw: bytes) -> None:
        label = "request" if phase == "REQUEST" else "response"
        actual[f"{label}_sha256"] = _sha(raw)
        actual[f"serialized_{'sent' if phase == 'REQUEST' else 'received'}_bytes"] = len(raw)
        secret = planner._api_key
        patterns = (secret.encode(), json.dumps(secret)[1:-1].encode()) if secret else ()
        if any(pattern and pattern in raw for pattern in patterns):
            actual["wire_artifact_suppressed"] = True
            raise ValueError("credential-bearing body withheld")
        with (directory / f"{label}.raw").open("xb") as stream:
            stream.write(raw)
        try:
            parsed = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            parsed = None
        if parsed is not None:
            actual[f"{label}_parsed_sha256"] = _write(directory / f"{label}.json", parsed)
        if phase == "REQUEST":
            actual["actual_request_settings"] = cloud_request_settings(planner) | {
                "chat_path": path
            }
            actual["request_summary"] = summarize_role_request(parsed)
        if previous_observer is not None:
            previous_observer(phase, path, raw)

    planner.raw_transport_observer = observe
    started = time.monotonic()
    try:
        draft = planner.plan(request)
    except Exception as exc:
        actual.update(
            status="BLOCKED",
            failure_type=type(exc).__name__,
            transport_two_images=False,
            parsed=False,
            grounded=False,
            target_hit=False,
            destination_hit=False,
            wall_latency_ms=(time.monotonic() - started) * 1000,
            cost_ledger=ledger.export(),
            serialized_received_bytes=sum(
                row.serialized_received_bytes for row in ledger.requests()
            ),
            serialized_sent_bytes=sum(row.serialized_sent_bytes for row in ledger.requests()),
        )
        _write(directory / "attempt.json", actual)
        return actual
    finally:
        planner.raw_transport_observer = previous_observer
        planner.cost_ledger = previous_ledger
    rows = ledger.requests()
    actual["cost_ledger"] = ledger.export()
    actual["serialized_received_bytes"] = sum(row.serialized_received_bytes for row in rows)
    actual["serialized_sent_bytes"] = sum(row.serialized_sent_bytes for row in rows)
    evidence = draft.observation_evidence or {}
    target_hit, target_evidence = _pixel_hit(
        frame, evidence.get("original_pixel_target"), "object_geom"
    )
    destination_hit, destination_evidence = _pixel_hit(
        frame, evidence.get("original_pixel_destination"), "target_region_geom"
    )
    summary = actual.get("request_summary", {})
    attempt = actual | {
        "status": "COMPLETE",
        "index": index,
        "phase": "first" if index == 0 else "warm",
        "expected_request_summary": expected,
        "wall_latency_ms": (time.monotonic() - started) * 1000,
        "transport_two_images": summary.get("image_count") == 2
        and summary.get("distinct_image_count") == 2,
        "parsed": draft.parse_error is None,
        "grounded": draft.observed_scene is not None,
        "target_hit": target_hit,
        "destination_hit": destination_hit,
        "target_offline_check": target_evidence,
        "destination_offline_check": destination_evidence,
        "observation_evidence": evidence | {"cloud_snapshot_hash": cloud.digest()},
        "parse_error": draft.parse_error,
        "parsed_json": draft.parsed_json,
    }
    _write(directory / "attempt.json", attempt)
    return attempt


class _EnvironmentProfileSecrets:
    """Read-only implementation of the existing SecretStore boundary for the CLI."""

    kind = SecretStoreKind.ENVIRONMENT

    def __init__(self, profile_id: str, variable: str) -> None:
        self.profile_id, self.variable = profile_id, variable

    def get_secret(self, profile_id: str) -> str | None:
        return os.environ.get(self.variable) if profile_id == self.profile_id else None

    def has_secret(self, profile_id: str) -> bool:
        return bool(self.get_secret(profile_id))

    def set_secret(self, profile_id: str, value: str) -> None:
        raise ValueError("CLI secret store is read-only")

    def delete_secret(self, profile_id: str) -> None:
        raise ValueError("CLI secret store is read-only")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/research/ced_roles.yaml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-id")
    parser.add_argument("--model-control-db", type=Path, default=Path("data/model_control.db"))
    parser.add_argument("--secret-env", default="BIGSMALL_VLM_API_KEY")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    service = None
    if args.execute:
        from cloud_edge_robot_arm.model_control.sqlite_repository import (
            SQLiteModelProfileRepository,
        )

        selected = args.profile_id or read_role_config(args.config)["cloud"]["profile_id"]
        if args.model_control_db.is_file() and selected:
            service = ModelControlService(
                repository=SQLiteModelProfileRepository(args.model_control_db),
                secret_store=_EnvironmentProfileSecrets(selected, args.secret_env),
            )
    report = run_probe(
        args.config,
        args.output,
        service=service,
        profile_id=args.profile_id,
        execute=args.execute,
        allow_paid=args.allow_paid,
    )
    print(
        json.dumps(
            {"status": report["status"], "report_path": str(args.output / "role-probe-report.json")}
        )
    )
    return 0 if report["status"] in {"PASS", "NOT_STARTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
