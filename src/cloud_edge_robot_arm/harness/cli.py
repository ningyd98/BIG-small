"""Validate, prepare and explicitly run the registered BIGsmall simulation."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cloud_edge_robot_arm import __version__
from cloud_edge_robot_arm.harness._ownership import canonical_output, reserve_output
from cloud_edge_robot_arm.harness.checkout import (
    ENTRY,
    SourceCheckout,
    native_source_bindings,
    sha256_file,
    verify_checkout,
)
from cloud_edge_robot_arm.harness.config import CONFIG_RESOURCE, HarnessConfig, load_config
from cloud_edge_robot_arm.harness.evidence import (
    MANIFEST,
    EpisodeExpectation,
    EvidenceOwnershipError,
    stage_files,
    verify_evidence,
)
from cloud_edge_robot_arm.vision.marker_families import marker_family


def _config_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config", type=Path, help=f"JSON configuration (default {CONFIG_RESOURCE})",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bigsmall-harness", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    validation = sub.add_parser("validate", help="validate offline configuration")
    _config_option(validation)
    doctor = sub.add_parser("doctor", help="inspect resource requirements without model startup")
    _config_option(doctor)
    doctor.add_argument("--source-checkout", type=Path)
    prepare = sub.add_parser("prepare", help="run the original no-render, no-model preparation")
    run = sub.add_parser("run-simulation", help="explicit real-model MuJoCo component diagnostic")
    for command in (prepare, run):
        _config_option(command)
        command.add_argument("--source-checkout", required=True, type=Path)
        command.add_argument(
            "--output", required=True, type=Path, help="a new local episode directory",
        )
    run.add_argument("--native-python", required=True, type=Path)
    run.add_argument("--profile-id", required=True)
    run.add_argument("--model-control-db", required=True, type=Path)
    run.add_argument("--model-directory", required=True, type=Path)
    run.add_argument("--asset-manifest", required=True, type=Path)
    run.add_argument("--gpu-lock", required=True, type=Path)
    run.add_argument("--application-site-packages", type=Path)
    run.add_argument("--allow-paid", action="store_true")
    evidence = sub.add_parser("evidence", help="verify an existing local episode manifest")
    evidence.add_argument("output", type=Path)
    return parser


def _configured(config: HarnessConfig) -> dict[str, object]:
    return {
        "configuration": config.model_dump(mode="json"),
        "configuration_sha256": config.fingerprint(),
    }


def _diagnose(config: HarnessConfig, checkout: Path | None) -> dict[str, object]:
    family = marker_family(config.marker_family)
    report: dict[str, object] = {
        "status": "OFFLINE_READY",
        **_configured(config),
        "resources": {
            "package_example": CONFIG_RESOURCE,
            "source_checkout": (
                "CHECKED_SELECTED_FILES" if checkout else "REQUIRED_FOR_PREPARE_OR_SIMULATION"
            ),
            "scene_asset": {"path": family.asset_path, "sha256": family.asset_sha256},
            "native_model_runtime": "EXTERNAL_UNVERIFIED",
            "runtime_files": [
                "approved native Python and dependencies",
                "existing Sol profile in an encrypted model-control database",
                "local Molmo2-ER model directory and registered asset manifest",
                "existing shared GPU lock",
            ],
        },
        "execution_scope": "MUJOCO_COMPONENT_DIAGNOSTIC",
        "hardware_dispatch": False,
        "edge_dispatch": False,
        "local_recover_enabled": False,
        "formal_research": "NOT_ACCEPTED",
    }
    if checkout is not None:
        report["source"] = verify_checkout(checkout, config).provenance()
    return report


def _native_command(
    python: Path, source: SourceCheckout, receipt: Path, flags: list[str],
) -> list[str]:
    """Use the installed bootstrap as a script so the selected interpreter owns all imports."""
    bootstrap = Path(__file__).with_name("_native.py")
    bindings = json.dumps(native_source_bindings(source))
    return [str(python), "-I", "-B", str(bootstrap), str(receipt), bindings, *flags]


@dataclass(frozen=True)
class _ChildExit:
    code: int
    stdout: str
    stop_reason: str | None

    def exit_fields(self, fallback: int = 2) -> dict[str, object]:
        code = 128 - self.code if self.code < 0 else self.code
        if self.stop_reason == "TIMEOUT":
            code = 124
        elif self.stop_reason == "WRAPPER_INTERRUPT":
            code = 130
        return {
            "episode_exit_code": self.code,
            "signal": -self.code if self.code < 0 else None,
            "wrapper_exit_code": code or fallback,
            "wrapper_stop_reason": self.stop_reason,
        }


def _run_child(
    command: list[str],
    *,
    source: SourceCheckout,
    env: dict[str, str],
    timeout: int,
    pass_fds: tuple[int, ...] = (),
) -> _ChildExit:
    with subprocess.Popen(
        command, cwd=source.root, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
        start_new_session=True, pass_fds=pass_fds,
    ) as child:
        stop_reason = None
        try:
            stdout, _ = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            stdout, _ = child.communicate()
            stop_reason = "TIMEOUT"
        except KeyboardInterrupt:
            child.send_signal(signal.SIGINT)
            try:
                stdout, _ = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                stdout, _ = child.communicate()
            stop_reason = "WRAPPER_INTERRUPT"
        return _ChildExit(child.returncode, stdout, stop_reason)


def _native_receipt(path: Path) -> dict[str, Any] | None:
    try:
        receipt = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return receipt if isinstance(receipt, dict) else None


def _child_rejection(
    child: _ChildExit, receipt: dict[str, Any] | None,
) -> Literal["PRE_DELEGATION", "ORIGINAL_CLI"] | None:
    if child.stop_reason is not None or child.code != 2:
        return None
    if receipt is not None and receipt.get("status") == "REJECTED_BEFORE_EPISODE":
        return "PRE_DELEGATION"
    try:
        reply = json.loads(child.stdout)
    except ValueError:
        return None
    if (
        isinstance(reply, dict) and set(reply) == {"status", "error_type"}
        and reply["status"] == "NOT_STARTED" and isinstance(reply["error_type"], str)
    ):
        return "ORIGINAL_CLI"
    return None


def _finish_launch(
    report: dict[str, Any],
    config: HarnessConfig,
    output: Path,
    child: _ChildExit,
    receipt: dict[str, Any] | None,
    *,
    expected: EpisodeExpectation | None = None,
) -> tuple[int, dict[str, object]]:
    if receipt is not None:
        report["native_python"] = receipt
    rejected = _child_rejection(child, receipt)
    if rejected == "PRE_DELEGATION" or (rejected is not None and not os.path.lexists(output)):
        return 2, {**report, **child.exit_fields(), "status": "NOT_STARTED"}
    attributed = rejected is None
    index = None
    if attributed:
        try:
            index = verify_evidence(output, expected=expected)
        except EvidenceOwnershipError:
            attributed = False
        except (OSError, ValueError):
            pass
    if index is not None:
        episode = index["episode"]
        phase = episode["status"]
        if (child.code >= 0 and child.stop_reason is None) or phase == "INTERRUPTED":
            exit_fields = child.exit_fields(fallback=0)
            report.update(
                exit_fields, status=phase, episode=episode,
                evidence={key: value for key, value in index.items() if key not in (
                    "effective_configuration", "episode",
                )},
            )
            if phase == "PREPARED":
                report["effective_configuration"] = index["effective_configuration"]
                report["not_applied"] = [
                    key for key in ("scene_split", "visual_servo", "camera_position_m")
                    if getattr(config, key) != index["effective_configuration"][key]
                ]
            return int(exit_fields["wrapper_exit_code"]), report
    incomplete = child.exit_fields()
    return int(incomplete["wrapper_exit_code"]), {
        **report, **incomplete, "status": "INCOMPLETE_UNKNOWN",
        "costs": None, "present_stage_files": stage_files(output) if attributed else [],
    }


def _launch(args: argparse.Namespace, config: HarnessConfig) -> tuple[int, dict[str, object]]:
    native = args.command == "run-simulation"
    if native and not args.allow_paid:
        raise ValueError("run-simulation requires explicit --allow-paid")
    source = verify_checkout(args.source_checkout, config)
    output = canonical_output(args.output)
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    python = Path(sys.executable)
    flags = [
        "--output", str(output), "--seed", str(config.seed),
        "--marker-family", config.marker_family,
    ]
    report: dict[str, Any] = {
        "planned_configuration": config.model_dump(mode="json"),
        "planned_configuration_sha256": config.fingerprint(),
        "source": source.provenance(),
        "output": str(output),
    }
    if native:
        # Preserve the executable path in the virtual environment even if it is a symlink.
        python = Path(os.path.abspath(args.native_python))
        if not python.is_file() or not os.access(python, os.X_OK):
            raise ValueError("native Python executable unavailable")
        for option in ("model_control_db", "asset_manifest", "gpu_lock"):
            path = getattr(args, option).resolve()
            if not path.is_file():
                raise ValueError(f"required --{option.replace('_', '-')} file unavailable")
            flags.extend((f"--{option.replace('_', '-')}", str(path)))
        model = args.model_directory.resolve()
        if not model.is_dir():
            raise ValueError("required local --model-directory unavailable")
        site = args.application_site_packages
        if site is not None:
            site = site.resolve()
            if not site.is_dir():
                raise ValueError("application site-packages directory unavailable")
            flags.extend(("--application-site-packages", str(site)))
        if not args.profile_id.strip():
            raise ValueError("nonempty existing Sol --profile-id required")
        flags.extend((
            "--execute", "--component-diagnostic", "--allow-paid", "--visual-servo",
            "--model-directory", str(model), "--profile-id", args.profile_id,
        ))
        if config.scene_split is not None:
            flags.extend(("--scene-split", config.scene_split))
        if config.camera_position_m is not None:
            flags.extend(("--camera-position", *map(str, config.camera_position_m)))
        report["model_asset_manifest_sha256"] = sha256_file(args.asset_manifest)
    expected = EpisodeExpectation(source, config, native)
    with reserve_output(output) as descriptor:
        if native:
            with tempfile.TemporaryDirectory(prefix="bigsmall-harness-native-") as temporary:
                receipt_path = Path(temporary) / "admission.json"
                command = _native_command(python, source, receipt_path, flags)
                child = _run_child(
                    command, source=source, env=env, timeout=900, pass_fds=(descriptor,),
                )
                receipt = _native_receipt(receipt_path)
        else:
            command = [str(python), "-I", "-B", str(source.root / ENTRY), *flags]
            child = _run_child(
                command, source=source, env=env, timeout=30, pass_fds=(descriptor,),
            )
            receipt = None
        return _finish_launch(report, config, output, child, receipt, expected=expected)


def _dispatch(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    if args.command == "evidence":
        try:
            return 0, verify_evidence(args.output)
        except FileNotFoundError:
            present = stage_files(args.output)
            if not present or MANIFEST in present:
                raise
            return 2, {
                "status": "INCOMPLETE_UNKNOWN", "costs": None, "present_stage_files": present,
            }
    config = load_config(args.config)
    if args.command == "validate":
        return 0, {"status": "VALIDATED", **_configured(config)}
    if args.command == "doctor":
        return 0, _diagnose(config, args.source_checkout)
    return _launch(args, config)


def main(argv: list[str] | None = None) -> int:
    """Return the diagnostic status and emit one JSON object."""
    args = _parser().parse_args(argv)
    try:
        code, report = _dispatch(args)
    except ValueError as error:
        code, report = 2, {"status": "NOT_STARTED", "error": str(error)}
    except OSError as error:
        code, report = 2, {"status": "NOT_STARTED", "error": type(error).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return code
