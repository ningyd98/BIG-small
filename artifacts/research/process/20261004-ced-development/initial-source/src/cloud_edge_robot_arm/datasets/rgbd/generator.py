"""Bounded, resumable offline RGB-D production; never invokes a model service."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from cloud_edge_robot_arm.datasets.rgbd.models import (
    DatasetConfig,
    DatasetManifest,
    SampleRecord,
    SplitManifest,
    canonical_json,
    content_digest,
)
from cloud_edge_robot_arm.datasets.rgbd.quality import (
    find_duplicate,
    perceptual_signature,
    validate_dataset,
)
from cloud_edge_robot_arm.datasets.rgbd.splitter import ROLES, assign_splits, write_splits
from cloud_edge_robot_arm.datasets.rgbd.writer import (
    DatasetWriter,
    load_manifest,
    save_manifest,
)
from cloud_edge_robot_arm.datasets.rgbd.writer import (
    load_records as load_records,
)
from cloud_edge_robot_arm.simulation.config import SimulatorConfig


def _capture_dependencies() -> tuple[Any, Any, Any, Any]:
    # Import renderer-facing code only after resume, budget, and cancellation checks.
    from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter
    from cloud_edge_robot_arm.datasets.rgbd.labels import label_frame
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    return MuJoCoCaptureSession, OfflineSceneAdapter, sample_scene, label_frame


def _source_evidence(config: DatasetConfig) -> dict[str, Any]:
    package = Path(__file__).resolve().parents[2]
    relevant = [
        *Path(__file__).parent.glob("*.py"),
        package / "vision" / "capture.py",
        package / "vision" / "observations.py",
        package / "vision" / "offline_reader.py",
        package / "simulation" / "config.py",
        package / "simulation" / "models.py",
        package / "simulation" / "mujoco" / "backend.py",
        package / "simulation" / "mujoco" / "camera.py",
        package / "contracts" / "models.py",
        package / "contracts" / "__init__.py",
        package / "errors.py",
        package / "simulation" / "backend.py",
        package / "simulation" / "mujoco" / "spec_randomization.py",
        *(
            package / relative / "__init__.py"
            for relative in (".", "datasets", "vision", "simulation", "simulation/mujoco")
        ),
    ]
    hashes = {
        str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(relevant))
    }
    model = Path(config.model_path).resolve()
    assets = {
        str(path.relative_to(model.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(model.parent.rglob("*"))
        if path.is_file()
    }
    versions = {}
    for name in ("mujoco", "numpy", "pillow", "pydantic"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "NOT_INSTALLED"
    return {
        "source_hash": content_digest(hashes),
        "source_files": hashes,
        "asset_hash": content_digest(assets),
        "asset_files": assets,
        "model_path": str(model),
        "model_exists": model.is_file(),
        "python": platform.python_version(),
        "dependencies": versions,
        "evidence_kind": "REAL_CAPTURE",
        "model_calls": 0,
    }


def _atomic_json(path: Path, value: Any) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical_json(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _journal(path: Path, event: str, attempt: int, **details: Any) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical_json({"event": event, "attempt": attempt, **details}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_attempts(path: Path) -> tuple[int, int, int]:
    if not path.exists():
        return 0, 0, 0
    if path.is_symlink():
        raise ValueError("symlink attempt journal is forbidden")
    raw = path.read_bytes()
    attempts = rejected = failures = 0
    offset = 0
    outcomes: set[int] = set()
    lines = raw.splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            item = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            if index != len(lines) - 1 or line.endswith(b"\n"):
                raise ValueError("invalid attempt journal") from None
            # A partial append cannot have reached capture: started events are fsynced first.
            _atomic_json(
                path.with_name("attempt-journal-recovery.json"),
                {
                    "discarded_tail_sha256": hashlib.sha256(line).hexdigest(),
                    "reason": "interrupted final journal append",
                    "retained_bytes": offset,
                },
            )
            with path.open("r+b") as stream:
                stream.truncate(offset)
                stream.flush()
                os.fsync(stream.fileno())
            break
        number = item.get("attempt")
        if type(number) is not int or number < 1:
            raise ValueError("invalid attempt number")
        event = item.get("event")
        if event == "started":
            if number != attempts + 1:
                raise ValueError("attempt journal is not consecutive")
            attempts = number
        elif event in {"rejected", "published", "failed"}:
            if number > attempts or number in outcomes:
                raise ValueError("duplicate or unmatched attempt outcome")
            outcomes.add(number)
            rejected += int(event == "rejected")
            failures += int(event == "failed")
        else:
            raise ValueError("unknown attempt journal event")
        offset += len(line)
        if index == len(lines) - 1 and not line.endswith(b"\n"):
            with path.open("ab") as stream:
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())
    return attempts, rejected, failures


def _counts(manifest: DatasetManifest, records: list[SampleRecord]) -> None:
    manifest.completed_groups = len({record.group_id for record in records})
    manifest.sample_count = len(records)
    manifest.positive_count = sum(record.status == "POSITIVE" for record in records)
    manifest.negative_count = sum(record.status == "NEGATIVE" for record in records)
    manifest.content_hash = content_digest(sorted(record.content_hash for record in records))
    manifest.updated_at = datetime.now(UTC)


def _disk_reason(config: DatasetConfig, root: Path, used: int, needed: int = 0) -> str | None:
    if used + needed > config.max_bytes:
        return "disk dataset byte budget exhausted"
    if shutil.disk_usage(root).free - needed < config.min_free_bytes:
        return "disk free-space reserve would be violated"
    return None


def _payload_reserve(record: SampleRecord) -> int:
    observation = record.captured_frame.observation if record.captured_frame else None
    if observation is None:
        return 0
    # Upper bound for encoded PNGs, numeric arrays, metadata, index replacement and staging.
    copies = 2 if record.raw_captured_frame is not None else 1
    return observation.width * observation.height * (24 * copies) + 131072


def _json_size(value: Any) -> int:
    return len((canonical_json(value) + "\n").encode("utf-8"))


def _reserve_replacements(
    config: DatasetConfig, output: Path, replacements: list[tuple[Path, int]]
) -> None:
    """Bound retained dataset bytes and free space for sequential atomic writes.

    max_bytes covers every persistent file under the dataset root, including
    indexes/reports/manifests. Temporary atomic copies are separately charged
    against available filesystem space while preserving min_free_bytes.
    """
    used = sum(
        path.stat().st_size
        for path in output.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    growth = peak_growth = 0
    previous_sizes: dict[Path, int] = {}
    for path, new_size in replacements:
        if path.is_symlink():
            raise ValueError("symlink finalization output is forbidden")
        old_size = previous_sizes.get(path, path.stat().st_size if path.is_file() else 0)
        peak_growth = max(peak_growth, growth + new_size)
        growth += new_size - old_size
        previous_sizes[path] = new_size
        if used + growth > config.max_bytes:
            raise OSError(errno.ENOSPC, "disk dataset byte budget exhausted during finalization")
    if shutil.disk_usage(output).free - peak_growth < config.min_free_bytes:
        raise OSError(
            errno.ENOSPC, "disk free-space reserve for atomic finalization would be violated"
        )


def _finalization_sizes(
    output: Path, records: list[SampleRecord], split: SplitManifest, manifest: DatasetManifest
) -> list[tuple[Path, int]]:
    sizes = dict.fromkeys(ROLES, 0)
    for record in records:
        sizes[split.sample_assignments[record.sample_id]] += _json_size(
            record.model_dump(mode="json")
        )
    replacements = [(output / "splits" / f"{role}.jsonl", sizes[role]) for role in ROLES]
    replacements.append(
        (output / "reports" / "split_audit.json", _json_size(split.model_dump(mode="json")))
    )
    # Report errors may grow with samples; actual payload sizes are checked again
    # before publication. Leave bounded room for status/resource metadata as well.
    replacements.extend(
        [
            (output / "manifest.json", _json_size(manifest.model_dump(mode="json"))),
            (output / "reports" / "quality.json", 4096 + 1024 * len(records)),
            (output / "manifest.json", _json_size(manifest.model_dump(mode="json")) + 4096),
        ]
    )
    return replacements


def _save_final_manifest(output: Path, config: DatasetConfig, manifest: DatasetManifest) -> None:
    """Include the final manifest itself in the reported retained-byte count."""
    used = sum(
        path.stat().st_size
        for path in output.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    path = output / "manifest.json"
    previous_size = path.stat().st_size if path.exists() else 0
    manifest.resources["dataset_bytes_measurement"] = "all retained files including final manifest"
    for _ in range(8):
        projected = used - previous_size + _json_size(manifest.model_dump(mode="json"))
        if manifest.resources.get("dataset_bytes") == projected:
            break
        manifest.resources["dataset_bytes"] = projected
        manifest.resources["bytes_per_sample"] = (
            projected / manifest.sample_count if manifest.sample_count else None
        )
    _reserve_replacements(config, output, [(path, _json_size(manifest.model_dump(mode="json")))])
    save_manifest(output, manifest)


def _generate_locked(
    config: DatasetConfig, output: Path, cancel: Callable[[], bool]
) -> DatasetManifest:
    started = perf_counter()
    existing = load_manifest(output)
    if existing is not None and existing.config_hash != config.config_hash:
        raise ValueError("cannot resume incompatible dataset config")
    source = _source_evidence(config)
    source_path = output / "source.json"
    if source_path.is_symlink():
        raise ValueError("symlink source evidence is forbidden")
    if source_path.exists() and json.loads(source_path.read_text()) != source:
        raise ValueError("cannot resume dataset with changed source or assets")
    if existing is not None and existing.source != source:
        raise ValueError("cannot resume dataset with changed source or assets")
    manifest = existing or DatasetManifest(
        dataset_id=config.dataset_id,
        config=config,
        config_hash=config.config_hash,
        status="RUNNING",
        requested_groups=config.groups,
        source=source,
    )
    if existing is None and not (output / "config.json").exists():
        try:
            _reserve_replacements(
                config,
                output,
                [
                    (output / "config.json", _json_size(config.model_dump(mode="json"))),
                    (source_path, _json_size(source)),
                    (output / "samples.jsonl", 0),
                    (output / "manifest.json", _json_size(manifest.model_dump(mode="json")) + 4096),
                ],
            )
        except OSError as exc:
            manifest.status, manifest.reason = "INCOMPLETE", f"initial disk metadata reserve: {exc}"
            manifest.resources["manifest_persisted"] = False
            return manifest
    elapsed_before = float(manifest.resources.get("generation_wall_time_s", 0))
    journal_path = output / "attempts.jsonl"
    attempts, rejected, failures = _read_attempts(journal_path)
    if manifest.attempts > attempts:
        raise ValueError("attempt journal missing previously recorded attempts")
    if attempts > config.groups * config.max_attempt_multiplier:
        raise ValueError("attempt journal exceeds configured sampling budget")
    writer = DatasetWriter(output, config)
    if writer.records and not source_path.exists() and existing is None:
        raise ValueError("cannot resume existing episodes without source evidence")
    if len({record.group_id for record in writer.records}) > config.groups:
        raise ValueError("committed groups exceed requested dataset size")
    if len(writer.records) > attempts:
        raise ValueError("committed samples lack a durable attempt history")
    if not source_path.exists():
        _atomic_json(source_path, source)
    manifest.attempts = attempts
    manifest.rejected_count = rejected
    manifest.status = "RUNNING"
    manifest.reason = None
    _counts(manifest, writer.records)
    save_manifest(output, manifest)
    stage = "preflight"
    active_attempt: int | None = None

    def persist_progress() -> None:
        _counts(manifest, writer.records)
        manifest.resources["failed_attempts"] = failures
        _reserve_replacements(
            config,
            output,
            [
                (output / "manifest.json", _json_size(manifest.model_dump(mode="json")) + 4096),
            ],
        )
        save_manifest(output, manifest)

    def record_attempt(event: str, attempt: int, **details: Any) -> None:
        current_size = journal_path.stat().st_size if journal_path.exists() else 0
        appended_size = _json_size({"event": event, "attempt": attempt, **details})
        # Before consuming a new attempt, reserve its outcome plus enough terminal
        # manifest space to record resource/status diagnostics without crossing cap.
        outcome_reserve = 4096 if event == "started" else 0
        _reserve_replacements(
            config,
            output,
            [
                (journal_path, current_size + appended_size + outcome_reserve),
                (output / "manifest.json", _json_size(manifest.model_dump(mode="json")) + 4096),
            ],
        )
        _journal(journal_path, event, attempt, **details)

    try:
        initial_stop = _disk_reason(config, output, writer.total_bytes)
        if cancel():
            manifest.status, manifest.reason = "CANCELLED", "user cancellation"
        elif initial_stop:
            manifest.status, manifest.reason = "INCOMPLETE", initial_stop
        elif manifest.completed_groups < config.groups and attempts < (
            config.groups * config.max_attempt_multiplier
        ):
            stage = "renderer"
            session_type, adapter_type, sample_scene, label_frame = _capture_dependencies()
            simulator = SimulatorConfig(
                model_path=config.model_path,
                seed=config.seed,
                render_rgb=True,
                render_depth=True,
                camera_width=config.width,
                camera_height=config.height,
            )
            with session_type(simulator) as session:
                adapter = adapter_type(session, settle_steps=config.settle_steps)
                while manifest.completed_groups < config.groups:
                    stage = "preflight"
                    if cancel():
                        manifest.status, manifest.reason = "CANCELLED", "user cancellation"
                        break
                    if manifest.attempts >= config.groups * config.max_attempt_multiplier:
                        break
                    disk_stop = _disk_reason(config, output, writer.total_bytes)
                    if disk_stop:
                        manifest.status, manifest.reason = "INCOMPLETE", disk_stop
                        break
                    number = manifest.attempts + 1
                    seed = config.seed + number - 1
                    record_attempt("started", number, seed=seed)
                    active_attempt = number
                    manifest.attempts = number
                    persist_progress()
                    stage = "sampling"
                    try:
                        scene = sample_scene(config, seed)
                        previous = next(
                            (
                                record
                                for record in writer.records
                                if record.group_id == scene.group_id
                                or record.scene.scene_hash == scene.scene_hash
                            ),
                            None,
                        )
                        if previous is not None:
                            record_attempt(
                                "rejected",
                                number,
                                reason="duplicate scene",
                                duplicate_sample_id=previous.sample_id,
                            )
                            manifest.rejected_count += 1
                            active_attempt = None
                            persist_progress()
                            continue
                        stage = "capture"
                        session.apply_scene(scene)
                        frame, truth = adapter.capture()
                        stage = "labeling"
                        raw_frame = truth.get("_raw_captured_frame")
                        labels = dict(
                            label_frame(
                                frame,
                                {
                                    key: value
                                    for key, value in truth.items()
                                    if key != "_raw_captured_frame"
                                },
                            )
                        )
                        record = SampleRecord.from_capture(
                            scene, frame, labels, raw_captured_frame=raw_frame
                        )
                        record.perceptual_hash = perceptual_signature(frame.observation)
                        duplicate = find_duplicate(record, writer.records)
                        if duplicate is not None:
                            record_attempt(
                                "rejected",
                                number,
                                reason="duplicate visual evidence",
                                duplicate_sample_id=duplicate,
                            )
                            manifest.rejected_count += 1
                            active_attempt = None
                            persist_progress()
                            continue
                        disk_stop = _disk_reason(
                            config, output, writer.total_bytes, _payload_reserve(record)
                        )
                        if disk_stop:
                            record_attempt("failed", number, reason=disk_stop)
                            failures += 1
                            active_attempt = None
                            manifest.status, manifest.reason = "INCOMPLETE", disk_stop
                            break
                        stage = "write"
                        writer.write_episode([record])
                        record_attempt(
                            "published",
                            number,
                            sample_id=record.sample_id,
                            group_id=record.group_id,
                        )
                        active_attempt = None
                        persist_progress()
                    except ValueError as exc:
                        if stage == "write":
                            raise
                        record_attempt("rejected", number, reason=str(exc), stage=stage)
                        manifest.rejected_count += 1
                        active_attempt = None
                        persist_progress()
        if manifest.status == "RUNNING" and manifest.completed_groups < config.groups:
            manifest.status, manifest.reason = "INCOMPLETE", "sampling attempt budget exhausted"
    except KeyboardInterrupt:
        manifest.status, manifest.reason = "CANCELLED", "user interruption"
    except (OSError, RuntimeError, ImportError, ValueError) as exc:
        if isinstance(exc, OSError) and exc.errno in {errno.ENOSPC, errno.EDQUOT}:
            manifest.status = "INCOMPLETE"
        elif stage in {"renderer", "capture"}:
            manifest.status = "BLOCKED"
        else:
            manifest.status = "FAILED"
        manifest.reason = f"{stage}: {type(exc).__name__}: {exc}"
        if active_attempt is not None:
            failures += 1
            try:
                record_attempt("failed", active_attempt, reason=manifest.reason)
            except OSError:
                pass  # The fsynced started event still preserves the consumed attempt.
        # Atomic publication may have succeeded before index replacement failed.
        try:
            writer = DatasetWriter(output, config)
        except OSError:
            pass

    _counts(manifest, writer.records)
    manifest.resources.update(
        {
            "generation_wall_time_s": elapsed_before + perf_counter() - started,
            "last_invocation_wall_time_s": perf_counter() - started,
            "dataset_bytes": writer.total_bytes,
            "bytes_per_sample": writer.total_bytes / manifest.sample_count
            if manifest.sample_count
            else None,
            "process_lifetime_peak_rss_bytes": (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
            "gpu_peak_memory_bytes": "NOT_MEASURED",
            "gpu_peak_memory_reason": "No per-process GPU memory sampler attached to this run",
            "renderer_processes": 1,
            "failed_attempts": failures,
            "disk_budget_semantics": "max_bytes covers all retained dataset files; "
            "atomic temporary copies additionally preserve min_free_bytes of filesystem free space",
        }
    )
    try:
        split = assign_splits(writer.records, config.seed)
        _reserve_replacements(
            config, output, _finalization_sizes(output, writer.records, split, manifest)
        )
        write_splits(output, split, writer.records)
        _reserve_replacements(
            config,
            output,
            [(output / "manifest.json", _json_size(manifest.model_dump(mode="json")))],
        )
        save_manifest(output, manifest)
        if manifest.status == "RUNNING" and manifest.completed_groups == config.groups:
            report = validate_dataset(output)
            _reserve_replacements(
                config,
                output,
                [
                    (
                        output / "reports" / "quality.json",
                        _json_size(report.model_dump(mode="json")),
                    ),
                    (output / "manifest.json", _json_size(manifest.model_dump(mode="json")) + 4096),
                ],
            )
            _atomic_json(output / "reports" / "quality.json", report.model_dump(mode="json"))
            if report.valid:
                manifest.status, manifest.reason = "COMPLETE", None
            else:
                manifest.status, manifest.reason = "FAILED", "; ".join(report.errors)
        manifest.resources.update(
            {
                "generation_wall_time_s": elapsed_before + perf_counter() - started,
                "last_invocation_wall_time_s": perf_counter() - started,
            }
        )
        _save_final_manifest(output, config, manifest)
    except (OSError, ValueError) as exc:
        manifest.status = (
            "INCOMPLETE"
            if isinstance(exc, OSError) and exc.errno in {errno.ENOSPC, errno.EDQUOT}
            else "FAILED"
        )
        manifest.reason = f"finalization: {type(exc).__name__}: {exc}"
        try:
            _save_final_manifest(output, config, manifest)
        except OSError:
            manifest.resources["manifest_persisted"] = False
    return manifest


def generate_dataset(
    config: DatasetConfig, output: Path, cancel: Callable[[], bool]
) -> DatasetManifest:
    """Continue one source/config-bound dataset, preserving all committed episodes."""
    config = DatasetConfig.model_validate(config.model_dump(mode="json"))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock_path = output / ".generator.lock"
    if lock_path.is_symlink():
        raise ValueError("symlink generator lock is forbidden")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another process owns this dataset generator") from exc
        try:
            return _generate_locked(config, output, cancel)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
