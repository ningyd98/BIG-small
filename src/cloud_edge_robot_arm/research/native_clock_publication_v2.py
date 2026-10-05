"""Startup-owned source-only prefix capture; historical signed UTC stays conditional."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from cloud_edge_robot_arm.research.native_clock_source_v2 import (
    BLIND_CONTEXT,
    DRAFT08,
    QUANTIZATION_NS,
    ClockExchangeOriginalV2,
    ClockTupleV2,
    GoWireVerifierV2,
    canonical_bytes,
    slab_commitment,
    verify_causal_slab,
)
from cloud_edge_robot_arm.research.native_reset_capture_v2 import VisualResetClockRecorderV2
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
from cloud_edge_robot_arm.vision.raw_recorder_v3 import RECORDER_SOURCE_PATHS, _plain
from cloud_edge_robot_arm.vision.worker_owner import (
    pin_worker_source_inventory,
    read_visual_worker_lease,
)

_TOKEN = object()
_ROOT = Path(__file__).resolve().parents[3]
_GO_METADATA = Path(
    "artifacts/research/process/20261004-ced-development/"
    "t7b-native-calibration-source/reset-utc-v2-design/fix-round-1/go/build-metadata.json"
)
REQUIRED_PREFIX_SOURCES = RECORDER_SOURCE_PATHS | frozenset(
    {
        "src/cloud_edge_robot_arm/research/native_clock_source_v2.py",
        "src/cloud_edge_robot_arm/research/native_reset_capture_v2.py",
        "src/cloud_edge_robot_arm/research/native_clock_publication_v2.py",
        "src/cloud_edge_robot_arm/simulation_runtime/worker.py",
        "src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py",
        "src/cloud_edge_robot_arm/simulation_runtime/models.py",
        "src/cloud_edge_robot_arm/simulation_runtime/state_machine.py",
        "src/cloud_edge_robot_arm/simulation/config.py",
        "src/cloud_edge_robot_arm/simulation/models.py",
        "src/cloud_edge_robot_arm/simulation_workbench/models.py",
        "scripts/run_native_clock_prefix_v2.py",
        "src/cloud_edge_robot_arm/vision/worker_owner.py",
        "assets/robots/franka_panda/scene.xml",
    }
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _regular(path: Path) -> Path:
    lexical = path.absolute()
    if any(p.is_symlink() for p in (lexical, *lexical.parents)) or not lexical.is_file():
        raise ValueError("regular lexical original without symlinks required")
    return lexical.resolve()


def validate_startup_inputs_v2(config_path: Path) -> dict[str, Any]:
    path = _regular(Path(config_path))
    config = json.loads(path.read_bytes())
    names = {
        "schema_version",
        "protocol",
        "hostname",
        "port",
        "public_key_b64",
        "issuer_accuracy",
        "quantization_ns",
        "exchange_timeout_s",
        "seed",
        "task_timeout_s",
        "ordinary_ttl_s",
        "source_scope",
        "policy_source",
    }
    if type(config) is not dict or set(config) != names:
        raise ValueError("exact frozen prefix startup policy required")
    if (
        config["schema_version"] != "native.clock.prefix.startup.v2"
        or config["protocol"] != DRAFT08
        or config["issuer_accuracy"] != "UNVERIFIED"
        or type(config["quantization_ns"]) is not int
        or config["quantization_ns"] != QUANTIZATION_NS
        or config["source_scope"] != "EXCLUDED_SOURCE_ONLY_PREFIX"
    ):
        raise ValueError("source-only draft08 policy required; no caller accuracy flag")
    key = base64.b64decode(config["public_key_b64"], validate=True)
    if len(key) != 32 or base64.b64encode(key).decode() != config["public_key_b64"]:
        raise ValueError("exact frozen32 byte public issuer key required")
    if (
        type(config["hostname"]) is not str
        or not config["hostname"]
        or type(config["port"]) is not int
        or not 1 <= config["port"] <= 65535
    ):
        raise ValueError("original endpoint required")
    for name, low, high in (
        ("exchange_timeout_s", 0.01, 10),
        ("task_timeout_s", 1, 300),
        ("ordinary_ttl_s", 0.01, 300),
    ):
        if type(config[name]) not in (int, float) or not low <= config[name] <= high:
            raise ValueError("bounded positive original timeout/diagnostic TTL required")
    if (
        type(config["seed"]) is not int
        or config["seed"] < 0
        or type(config["policy_source"]) is not str
    ):
        raise ValueError("original seed and policy provenance required")
    metadata_path = _regular(_ROOT / _GO_METADATA)
    metadata = json.loads(metadata_path.read_bytes())
    sources = {name: _sha(_regular(_ROOT / name)) for name in REQUIRED_PREFIX_SOURCES}
    sources.update(metadata["source_hashes"])
    verifier = GoWireVerifierV2(
        _ROOT / metadata["binary_path"],
        binary_sha256=metadata["binary_sha256"],
        source_root=_ROOT,
        source_hashes=metadata["source_hashes"],
    )
    pin_worker_source_inventory(_ROOT, sources, required_paths=REQUIRED_PREFIX_SOURCES)
    return {
        "config_path": str(path),
        "config_sha256": _sha(path),
        "config": config,
        "source_hashes": sources,
        "go_metadata_sha256": _sha(metadata_path),
        "go_binary_sha256": verifier.binary_sha256,
        "go_binary_path": str(verifier.binary),
    }


@dataclass
class _LiveApplication:
    repository: SQLiteSimulationJobRepository
    worker: SimulationWorker
    output: Path
    inputs: dict[str, Any]
    recorder: VisualResetClockRecorderV2 | None = None
    backend: Any = None
    capture: Any = None
    executor: Any = None
    source: ApplicationClockSourceV2 | None = None
    verifier: GoWireVerifierV2 | None = None
    job_id: str | None = None
    origin: tuple[Any, ...] | None = None
    published: str | None = None
    catalog_json: str | None = None
    assignment_json: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)


_REGISTRY: dict[NativeClockPrefixApplicationV2, _LiveApplication] = {}


def _assignment_basis(job: Any) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _plain(
            {
                name: getattr(job, name)
                for name in (
                    "job_id",
                    "run_id",
                    "backend",
                    "scenario_id",
                    "control_mode",
                    "seed",
                    "draft",
                    "timeout_seconds",
                    "max_attempts",
                    "manifest_id",
                    "reproducibility_hash",
                    "artifact_root",
                    "source_commit",
                    "source_tree_hash",
                )
            }
        ),
    )


def _live(application: Any) -> _LiveApplication:
    if type(application) is not NativeClockPrefixApplicationV2 or application not in _REGISTRY:
        raise RuntimeError("exact startup-owned live application required")
    record = _REGISTRY[application]
    if (
        application.repository is not record.repository
        or application.worker is not record.worker
        or record.worker.repository is not record.repository
        or application.output != record.output
    ):
        raise ValueError("configured live repository/worker identity changed")
    return record


class NativeClockPrefixApplicationV2:
    """Actual research app instance; public data/copies cannot substitute its registry."""

    repository: SQLiteSimulationJobRepository
    worker: SimulationWorker
    output: Path
    config_path: Path
    clock_source: ApplicationClockSourceV2

    def __init__(self, *, _token: object | None = None) -> None:
        if _token is not _TOKEN:
            raise TypeError("use the concrete startup application factory")
        self._execute_called = False

    @classmethod
    def from_startup(cls, config_path: Path, *, output: Path) -> NativeClockPrefixApplicationV2:
        inputs = validate_startup_inputs_v2(config_path)
        output = Path(output).absolute()
        if output.exists() or any(p.is_symlink() for p in (output, *output.parents)):
            raise ValueError("fresh excluded output without lexical aliases required")
        output.mkdir(parents=True)
        app = cls(_token=_TOKEN)
        app.output = output.resolve()
        app.config_path = Path(inputs["config_path"])
        app.repository = SQLiteSimulationJobRepository(app.output / "runtime.db")
        app.worker = SimulationWorker(
            worker_id="native-prefix-" + uuid4().hex,
            backend="MUJOCO",
            repository=app.repository,
            artifact_root=app.output,
            planner_factory=None,
        )
        _REGISTRY[app] = _LiveApplication(app.repository, app.worker, app.output, inputs)
        app.clock_source = ApplicationClockSourceV2.from_application(app)
        app.worker._native_clock_prefix_application = app
        return app

    @property
    def config(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(_live(self).inputs["config"])))

    @property
    def exchange_attempts(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], json.loads(json.dumps(_live(self).attempts)))

    def prepare_once(self) -> Any:
        record = _live(self)
        self._check_inputs()
        if record.job_id is not None:
            raise RuntimeError("prefix assignment cannot be retried or reallocated")
        config = self.config
        assignment: dict[str, object] = {
            "input_mode": "RGBD",
            "execution_scope": "VISION_CLOSED_LOOP",
            "backend": "MUJOCO",
            "scenarios": ["S01_NORMAL_STATIC"],
            "control_modes": ["PCSC"],
            "seeds": [config["seed"]],
            "user_instruction": "excluded native RESET clock prefix; no actions",
        }
        job = self.repository.create_job(
            run_id="native-prefix-" + uuid4().hex,
            batch_id="",
            backend="MUJOCO",
            scenario_id="S01_NORMAL_STATIC",
            control_mode="PCSC",
            seed=config["seed"],
            manifest_id="native-reset-prefix.v2",
            reproducibility_hash=hashlib.sha256(canonical_bytes(assignment)).hexdigest(),
            draft=assignment,
            timeout_seconds=config["task_timeout_s"],
            max_attempts=1,
            artifact_root="worker-attempt",
            source_commit="SOURCE_ONLY_CURRENT_BYTES",
            source_tree_hash=hashlib.sha256(
                canonical_bytes(record.inputs["source_hashes"])
            ).hexdigest(),
            provenance={
                "scope": "EXCLUDED_SOURCE_ONLY_PREFIX",
                "config_sha256": record.inputs["config_sha256"],
            },
        )
        record.job_id = job.job_id
        record.assignment_json = json.dumps(_assignment_basis(job), sort_keys=True)
        self.repository.update_status_cas(
            job.job_id,
            expected=RuntimeJobStatus.CREATED,
            next_status=RuntimeJobStatus.QUEUED,
            reason_code="native_prefix_startup",
            worker_id="",
            lease_id="",
        )
        return self.repository.get_job(job.job_id)

    def execute_once(self) -> dict[str, Any]:
        if self._execute_called:
            raise RuntimeError("prefix process cannot execute twice")
        self._execute_called = True
        self.prepare_once()
        if not self.worker.poll_once():
            raise RuntimeError("prefix application did not obtain its sole actual lease")
        return self.catalog_entry()

    def _check_inputs(self) -> None:
        record = _live(self)
        if (
            str(self.config_path) != record.inputs["config_path"]
            or _sha(_regular(self.config_path)) != record.inputs["config_sha256"]
        ):
            raise ValueError("original startup policy changed")
        pin_worker_source_inventory(
            _ROOT, record.inputs["source_hashes"], required_paths=REQUIRED_PREFIX_SOURCES
        )
        if _sha(_regular(_ROOT / _GO_METADATA)) != record.inputs["go_metadata_sha256"]:
            raise ValueError("original verifier build metadata changed")
        if (
            self.clock_source is not record.source
            or self.clock_source.application is not self
            or self.clock_source.verifier is not record.verifier
            or type(record.verifier) is not GoWireVerifierV2
        ):
            raise ValueError("original issued clock source/verifier changed")
        cast(GoWireVerifierV2, self.clock_source.verifier)._revalidate()

    def check_worker(self, worker: Any, job: Any, *, start_monotonic: float) -> None:
        record = _live(self)
        if (
            worker is not record.worker
            or job.job_id != record.job_id
            or worker.active_job_id != job.job_id
        ):
            raise ValueError("current configured prefix worker/assignment required")
        origin = worker._active_task_origin
        if origin is None or origin[:2] != (job.job_id, start_monotonic):
            raise ValueError("current actual worker task origin required")
        if record.origin is not None and record.origin != origin:
            raise ValueError("prefix origin changed")
        record.origin = origin
        self.check_active()

    def check_active(self) -> dict[str, Any]:
        record = _live(self)
        self._check_inputs()
        if record.job_id is None or record.origin is None:
            raise RuntimeError("actual running worker/lease/origin not established")
        job = self.repository.get_job(record.job_id)
        if json.dumps(_assignment_basis(job), sort_keys=True) != record.assignment_json:
            raise ValueError("original prefix assignment changed")
        if (
            self.worker._active_task_origin != record.origin
            or self.worker.active_job_id != record.job_id
        ):
            raise ValueError("original live task origin changed")
        lease = read_visual_worker_lease(
            self.repository,
            job_id=job.job_id,
            run_id=job.run_id,
            worker_id=self.worker.worker_id,
            lease_id=job.lease_id,
        )
        if (
            job.seed != self.config["seed"]
            or job.scenario_id != "S01_NORMAL_STATIC"
            or job.backend != "MUJOCO"
            or job.max_attempts != 1
        ):
            raise ValueError("current job differs from preassigned prefix")
        return {
            "job_id": job.job_id,
            "run_id": job.run_id,
            "attempt": lease.attempt,
            "lease_id": lease.lease_id,
            "worker_id": lease.worker_id,
            "lease": lease.to_payload(),
            "task_origin": _plain(record.origin),
        }

    def check_recorder(self, recorder: Any) -> dict[str, Any]:
        record = _live(self)
        state = self.check_active()
        if (
            type(recorder) is not VisualResetClockRecorderV2
            or recorder is not record.recorder
            or recorder.backend is not record.backend
            or recorder.capture_session is not record.capture
            or recorder.executor is not record.executor
        ):
            raise ValueError("exact issued live recorder/backend/capture/executor required")
        if (
            recorder.directory.absolute() != record.output / "prefix-originals"
            or recorder.source_root != _ROOT
            or dict(recorder.source_hashes) != record.inputs["source_hashes"]
        ):
            raise ValueError("issued recorder output/source inventory changed")
        if (
            record.capture._backend is not record.backend
            or record.capture._owns_backend
            or getattr(record.executor._robot, "_backend", None) is not record.backend
        ):
            raise ValueError("borrowed original backend identities changed")
        expected_config = SimulatorConfig(
            render_rgb=True, render_depth=True, seed=self.config["seed"]
        )
        if record.backend is None:
            raise ValueError("original backend missing")
        if record.backend._config.model_dump(mode="json") != expected_config.model_dump(
            mode="json"
        ):
            raise ValueError("formal camera/config domain changed")
        if (
            recorder._current_asset_hash()
            != record.inputs["source_hashes"]["assets/robots/franka_panda/scene.xml"]
        ):
            raise ValueError("actual native asset differs from original source inventory")
        return state

    def catalog_entry(self) -> dict[str, Any]:
        value = _live(self).catalog_json
        if value is None:
            raise RuntimeError("no live source-only publication")
        return cast(dict[str, Any], json.loads(value))


class ApplicationClockSourceV2:
    def __init__(self, application: Any, *, _token: object | None = None) -> None:
        if _token is not _TOKEN:
            raise TypeError("clock source requires the actual configured application")
        self.application = application
        inputs = _live(application).inputs
        metadata = json.loads((_ROOT / _GO_METADATA).read_bytes())
        self.verifier = GoWireVerifierV2(
            Path(inputs["go_binary_path"]),
            binary_sha256=inputs["go_binary_sha256"],
            source_root=_ROOT,
            source_hashes=metadata["source_hashes"],
        )

    @classmethod
    def from_application(
        cls, application: Any, *, role_binding: Any = None
    ) -> ApplicationClockSourceV2:
        record = _live(application)
        if role_binding is not None:
            raise ValueError("this source-only prefix has no accepted role/Max binding")
        if record.source is None:
            record.source = cls(application, _token=_TOKEN)
            record.verifier = record.source.verifier
        return record.source

    def exchange(
        self, *, domain: str, exchange_id: str, commitment: bytes, previous_reply: bytes
    ) -> ClockExchangeOriginalV2 | None:
        app = self.application
        app.check_active()
        record = _live(app)
        if record.backend is not None and record.backend._in_observer_callback:
            raise RuntimeError("clock exchange forbidden in the backend observer")
        if (
            record.source is not self
            or exchange_id not in {"A", "B"}
            or any(r["exchange_id"] == exchange_id for r in record.attempts)
        ):
            raise RuntimeError("unique live bounded exchange required")
        recorder = record.recorder
        if recorder is None or domain != recorder._clock_domain_id or len(commitment) != 32:
            raise RuntimeError("issued recorder clock domain/commitment required")
        if exchange_id == "A" and (
            record.attempts or recorder._frozen_prefix is not None or previous_reply
        ):
            raise RuntimeError("A must precede the original frozen slab")
        if exchange_id == "B":
            if (
                recorder._frozen_prefix is None
                or len(record.attempts) != 1
                or not record.attempts[0].get("original")
            ):
                raise RuntimeError("B requires frozen originals and verified A")
            frozen = recorder._frozen_prefix
            pairs = tuple(ClockTupleV2.from_payload(p) for p in frozen.to_payload()["clock_pairs"])
            if commitment != slab_commitment(
                pairs, acquisition_sha256=frozen.digest()
            ) or previous_reply != base64.b64decode(
                record.attempts[0]["original"]["response_b64"], validate=True
            ):
                raise RuntimeError("B must bind complete frozen originals and original A")
        row: dict[str, Any] = {
            "exchange_id": exchange_id,
            "clock_domain_id": domain,
            "status": "ALLOCATED",
            "error": None,
            "original": None,
        }
        record.attempts.append(row)
        try:
            blind = os.urandom(32)
            effective = hashlib.sha512(BLIND_CONTEXT + blind + commitment).digest()[:32]

            def b64(raw: bytes) -> str:
                return base64.b64encode(raw).decode()

            request = self.verifier._invoke(
                {
                    "op": "request",
                    "previous_reply_b64": b64(previous_reply),
                    "blind_b64": b64(effective),
                    "public_key_b64": app.config["public_key_b64"],
                }
            )
            if set(request) != {"nonce_b64", "request_b64"}:
                raise ValueError("exact request wrapper output required")
            request_bytes = base64.b64decode(request["request_b64"], validate=True)
            row.update(
                request_b64=b64(request_bytes),
                commitment_b64=b64(commitment),
                source_blind_b64=b64(blind),
                effective_blind_b64=b64(effective),
                previous_reply_b64=b64(previous_reply),
                public_key_b64=app.config["public_key_b64"],
                endpoint=[app.config["hostname"], app.config["port"]],
            )
            response, brackets = _udp_exchange_v2(request_bytes, app.config, attempt=row)
            row.update(brackets, response_b64=b64(response))
            verified_before = time.monotonic_ns()
            row["verified_before_ns"] = verified_before
            try:
                self.verifier.verify(
                    b64(request_bytes), b64(response), app.config["public_key_b64"]
                )
            finally:
                verified_after = time.monotonic_ns()
                row["verified_after_ns"] = verified_after
            original = ClockExchangeOriginalV2(
                domain,
                exchange_id,
                b64(request_bytes),
                b64(response),
                app.config["public_key_b64"],
                b64(commitment),
                b64(previous_reply),
                b64(blind),
                b64(effective),
                brackets["send_before_ns"],
                brackets["send_after_ns"],
                brackets["receive_before_ns"],
                brackets["receive_after_ns"],
                verified_before,
                verified_after,
            )
            row.update(status="SIGNATURE_VERIFIED_ONLY", original=original.to_payload())
            return original
        except Exception as error:
            row.update(status="UNAVAILABLE", error=f"{type(error).__name__}: {error}")
            return None


def _udp_exchange_v2(
    request: bytes, config: dict[str, Any], *, attempt: dict[str, Any]
) -> tuple[bytes, dict[str, int]]:
    # Only called by the owned coordinator outside the backend observer.
    attempt["resolution_before_ns"] = time.monotonic_ns()
    try:
        address = socket.getaddrinfo(
            config["hostname"], config["port"], socket.AF_INET, socket.SOCK_DGRAM
        )[0][4]
    finally:
        attempt["resolution_after_ns"] = time.monotonic_ns()
    attempt["resolved_endpoint"] = list(address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(config["exchange_timeout_s"])
        client.connect(address)
        start = time.monotonic_ns()
        attempt["send_before_ns"] = start
        try:
            client.send(request)
        finally:
            attempt["send_after_ns"] = time.monotonic_ns()
        sent = time.monotonic_ns()
        received_before = time.monotonic_ns()
        attempt["receive_before_ns"] = received_before
        try:
            reply = client.recv(65536)
        finally:
            received_after = time.monotonic_ns()
            attempt["receive_after_ns"] = received_after
    return reply, {
        "send_before_ns": start,
        "send_after_ns": sent,
        "receive_before_ns": received_before,
        "receive_after_ns": received_after,
    }


def _issue_recorder_v2(
    application: Any,
    backend: Any,
    capture: Any,
    executor: Any,
    *,
    clock_source: Any,
    directory: Path,
) -> VisualResetClockRecorderV2:
    record = _live(application)
    application.check_active()
    if (
        record.recorder is not None
        or clock_source is not record.source
        or Path(directory).absolute() != record.output / "prefix-originals"
    ):
        raise ValueError("one configured live prefix capture required")
    recorder = VisualResetClockRecorderV2(
        backend,
        capture,
        executor,
        directory=directory,
        source_root=_ROOT,
        source_hashes=record.inputs["source_hashes"],
    )
    record.recorder, record.backend, record.capture, record.executor = (
        recorder,
        backend,
        capture,
        executor,
    )
    return recorder


def _write_original(directory: Path, name: str, value: Any) -> str:
    content = json.dumps(_plain(value), sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    target = directory / name
    if target.exists():
        raise RuntimeError("immutable prefix original already exists")
    target.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def verify_reset_clock_originals_v2(
    root: Path, capture_catalog_entry: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "original_integrity": "INVALID",
        "prefix_complete": False,
        "reasons": [],
        "native_utc": "UNAVAILABLE",
        "current_time_utc": "UNAVAILABLE",
        "issuer_accuracy": "UNVERIFIED",
    }
    try:
        root = Path(root)
        entry = json.loads(json.dumps(capture_catalog_entry, allow_nan=False))
        for name, digest in entry["file_hashes"].items():
            relative = Path(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or _sha(_regular(root / name)) != digest
            ):
                raise ValueError("original inventory path/hash changed")
        frozen = json.loads((root / "frozen-originals.json").read_bytes())
        if hashlib.sha256(canonical_bytes(frozen)).hexdigest() != entry["snapshot_sha256"]:
            raise ValueError("complete frozen slab changed")
        journal = frozen["reset_journal"]
        success = (
            len(journal) == 2
            and journal[0]["event"]["phase"] == "BEGIN"
            and journal[1]["event"]["phase"] == "END"
        )
        success = (
            success
            and journal[0]["event"]["operation_id"] == journal[1]["event"]["operation_id"]
            and journal[1]["event"]["error_type"] is None
        )
        success = (
            success
            and bool(journal[1]["event"]["episode_id"])
            and journal[1]["event"]["episode_id"] == frozen["observed_episode_id"]
        )
        physics = frozen["physics"]
        success = (
            success
            and frozen["reset_count"] == 1
            and [p["physics_step"] for p in physics] == list(range(1, 121))
        )
        success = success and all(
            p["control_payload"]["physics_step"] == p["physics_step"] for p in physics
        )
        success = (
            success
            and frozen["observed_total_physics_steps"] == 120
            and not frozen["observer_failures"]
            and not frozen["actions"]
            and frozen["explicit_acquisitions"] == 0
        )
        success = (
            success
            and not json.loads((root / "late-events.json").read_bytes())
            and not entry["export_failures"]
        )
        success = success and all(row["disposition"] == "COMPLETE" for row in frozen["intervals"])
        success = success and all(
            row["observation_payload"] is not None for row in frozen["frames"]
        )
        settle = [row for row in frozen["intervals"] if row["kind"] == "SETTLE"]
        success = (
            success
            and len(settle) == 1
            and settle[0]["start_step"] == 0
            and settle[0]["end_step"] == 120
        )
        success = (
            success
            and len(settle) == 1
            and all(row["purpose_interval_id"] == settle[0]["interval_id"] for row in physics)
        )
        result.update(
            original_integrity="VERIFIED",
            prefix_complete=bool(success),
            cached_capture_allocations=len(frozen["frames"]),
        )
        if not success:
            result["reasons"].append("original reset/120 SETTLE prefix incomplete")
    except (ValueError, TypeError, KeyError, OSError) as error:
        result["reasons"].append(str(error))
    return result


def publish_reset_clock_capture_v2(
    recorder: VisualResetClockRecorderV2, *, application: NativeClockPrefixApplicationV2
) -> dict[str, Any]:
    record = _live(application)
    with record.repository.publication_guard():
        state = application.check_recorder(recorder)
        if record.published is not None:
            raise RuntimeError("live prefix source already published")
        exported = recorder.export_unbound_prefix()
        frozen = recorder._frozen_prefix
        assert frozen is not None
        hashes = dict(exported["file_hashes"])
        hashes["exchange-attempts.json"] = _write_original(
            recorder.directory, "exchange-attempts.json", application.exchange_attempts
        )
        hashes["job-attempt-source.json"] = _write_original(
            recorder.directory, "job-attempt-source.json", state
        )
        hashes["startup-policy.json"] = _write_original(
            recorder.directory, "startup-policy.json", record.inputs
        )
        failure_path = recorder.directory / "prefix-failures.json"
        if not failure_path.exists():
            _write_original(recorder.directory, "prefix-failures.json", [])
        hashes["prefix-failures.json"] = _sha(_regular(failure_path))
        receipt = {
            **exported,
            "file_hashes": hashes,
            "publication_scope": "LIVE_APPLICATION_SOURCE_ONLY",
            "role_validation": "UNAVAILABLE",
            "native_utc": "UNAVAILABLE",
            "current_time_utc": "UNAVAILABLE",
            "issuer_accuracy": "UNVERIFIED",
            "consumer_feasibility": "UNAVAILABLE",
            "independent_calibration_group": False,
            "historical_conditional_intervals": [],
            "historical_width_ns": None,
            "ttl_comparison_scope": "HISTORICAL_WIDTH_ONLY_NOT_ACTUAL_AGE_OR_CONSUMER_FEASIBILITY",
            "necessary_ttl_lower_bound_exceeds": None,
            "worker_source": state,
        }
        attempts = application.exchange_attempts
        if len(attempts) == 2 and all(row.get("original") for row in attempts):
            payload = frozen.to_payload()
            pairs = tuple(ClockTupleV2.from_payload(p) for p in payload["clock_pairs"])
            first, last = (
                ClockExchangeOriginalV2.from_payload(row["original"]) for row in attempts
            )
            diagnosis = verify_causal_slab(
                pairs,
                first,
                last,
                application.clock_source.verifier,
                acquisition_sha256=frozen.digest(),
            )
            event_covered = all(
                first.verified_after_ns
                <= row["mono_before_ns"]
                <= row["mono_after_ns"]
                <= last.send_before_ns
                for row in payload["reset_journal"]
            )
            if diagnosis.conditional_pair_utc_intervals and event_covered:
                intervals = diagnosis.conditional_pair_utc_intervals
                width = intervals[0][2] - intervals[0][1]
                receipt.update(
                    historical_conditional_intervals=intervals,
                    historical_width_ns=width,
                    necessary_ttl_lower_bound_exceeds=width
                    > application.config["ordinary_ttl_s"] * 10**9,
                )
            else:
                receipt["clock_reasons"] = [
                    *diagnosis.reasons,
                    *([] if event_covered else ["RESET event causal bracket unavailable"]),
                ]
        else:
            receipt["clock_reasons"] = [
                "two genuine signature-verified original exchanges unavailable"
            ]
        view = verify_reset_clock_originals_v2(recorder.directory, receipt)
        receipt["prefix_complete"] = view["prefix_complete"]
        receipt["prefix_reasons"] = view["reasons"]
        application.check_recorder(recorder)
        final_view = verify_reset_clock_originals_v2(recorder.directory, receipt)
        if (
            final_view["original_integrity"] != "VERIFIED"
            or final_view["prefix_complete"] != receipt["prefix_complete"]
        ):
            raise ValueError("original capture changed across publication")
        published = _write_original(recorder.directory, "prefix-receipt.json", receipt)
        _write_original(
            application.output,
            "capture-catalog.json",
            {
                "scope": "SOURCE_ONLY_NO_NATIVE_ADMISSION",
                "receipt_path": "prefix-originals/prefix-receipt.json",
                "receipt_sha256": published,
                "entry": receipt,
            },
        )
        record.published = published
        record.catalog_json = json.dumps(receipt, sort_keys=True, allow_nan=False)
        return cast(dict[str, Any], json.loads(record.catalog_json))


def _new_prefix_backend_v2() -> Any:
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    return MuJoCoPhysicsBackend()


def run_native_reset_clock_prefix_v2(
    application: NativeClockPrefixApplicationV2,
    worker: SimulationWorker,
    job: Any,
    *,
    start_monotonic: float,
) -> tuple[dict[str, Any], list[Any], list[Any]]:
    """One actual worker prefix; historical UTC only, no planner or explicit acquisition."""
    from contextlib import ExitStack

    from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
    from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    application.check_worker(worker, job, start_monotonic=start_monotonic)
    record = _live(application)
    config = SimulatorConfig(render_rgb=True, render_depth=True, seed=job.seed)
    backend = _new_prefix_backend_v2()
    failures: list[str] = []
    receipt: dict[str, Any] | None = None
    try:
        backend.initialize(config)
        application.check_active()
        with ExitStack() as resources:
            capture = resources.enter_context(MuJoCoCaptureSession(config, backend=backend))
            executor = SkillExecutor(
                robot=MuJoCoSkillRobot(backend), registry=SkillRegistry.default()
            )
            recorder = VisualResetClockRecorderV2.from_worker_owner(
                application,
                None,
                backend,
                capture,
                executor,
                clock_source=application.clock_source,
                directory=record.output / "prefix-originals",
            )
            resources.enter_context(recorder)
            intent = hashlib.sha256(
                canonical_bytes(
                    {
                        "schema_version": "native.reset.prefix.intent.v2",
                        "worker": application.check_active(),
                        "inputs": record.inputs,
                        "clock_domain_id": recorder._clock_domain_id,
                    }
                )
            ).digest()
            first = application.clock_source.exchange(
                domain=recorder._clock_domain_id,
                exchange_id="A",
                commitment=intent,
                previous_reply=b"",
            )
            try:
                application.check_recorder(recorder)
                backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=job.seed))
                application.check_recorder(recorder)
                with recorder.purpose("SETTLE"):
                    backend.step(steps=120)
                application.check_recorder(recorder)
            except Exception as error:
                failures.append(f"{type(error).__name__}: {error}")
            frozen = recorder.freeze_unbound_prefix()
            if first is not None:
                pairs = tuple(
                    ClockTupleV2.from_payload(row) for row in frozen.to_payload()["clock_pairs"]
                )
                application.clock_source.exchange(
                    domain=recorder._clock_domain_id,
                    exchange_id="B",
                    commitment=slab_commitment(pairs, acquisition_sha256=frozen.digest()),
                    previous_reply=base64.b64decode(first.response_b64, validate=True),
                )
            else:
                record.attempts.append(
                    {
                        "exchange_id": "B",
                        "status": "SKIPPED_A_UNAVAILABLE",
                        "original": None,
                        "error": "verified A unavailable; no fabricated causal enclosure",
                    }
                )
            recorder.directory.mkdir(parents=True, exist_ok=True)
            _write_original(recorder.directory, "prefix-failures.json", failures)
            try:
                receipt = publish_reset_clock_capture_v2(recorder, application=application)
            except Exception as error:
                recorder.export_unbound_prefix()
                _write_original(
                    recorder.directory,
                    "publication-failure.json",
                    {"error": f"{type(error).__name__}: {error}"},
                )
                raise
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
        if not (record.output / "startup-failure.json").exists():
            _write_original(
                record.output,
                "startup-failure.json",
                {"errors": failures, "scope": "PRIVATE_EXCLUDED_DIAGNOSTIC"},
            )
        raise
    finally:
        backend.shutdown()
    assert receipt is not None
    return (
        {
            "evaluation_scope": "NATIVE_RESET_PREFIX_EXCLUDED",
            "prefix_complete": receipt["prefix_complete"],
            "task_success": False,
            "task_execution": "NOT_RUN",
            "native_utc": "UNAVAILABLE",
            "receipt": receipt,
        },
        [],
        [],
    )
