"""Full callback recorder with local V3 injection and one exclusive attempt."""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import resource
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("round57_prepare_full", HERE / "prepare_full.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
ROOT, DEV = P.ROOT, P.DEV
BASE = DEV / "t7b-continuous-visibility-v3/run_once.py"
BASE_SHA = "0f7c5d31f21bd35a5d7085e57376436b6bf33f043c47fe227542d6d94d654340"


class FullRGBDRecorder:
    """Actual callback prefix retained; expected denominator never follows actual range."""

    def __init__(
        self,
        directory,
        capture,
        *,
        episode_id,
        max_sample_gap_s,
        expected_physics_steps=4806,
        final_guard=None,
    ):
        P.require(
            type(expected_physics_steps) is int and expected_physics_steps >= 0,
            "exact horizon integer required",
        )
        P.require(
            P.finite(max_sample_gap_s) and max_sample_gap_s == 0.005,
            "fixed SimulationS gap required",
        )
        self.expected_physics_steps = expected_physics_steps
        self.directory = Path(directory)
        self.directory.mkdir()
        (self.directory / "frames").mkdir()
        self.stream = (self.directory / "index.jsonl").open("x", encoding="utf-8")
        self.capture, self.episode, self.final_guard = capture, episode_id, final_guard
        self.requirement, self.last_step, self.last_time = max_sample_gap_s, -1, None
        self.physical_attempts = self.physical_callbacks = 0
        self.attempts, self.saved, self.failures, self.publication_errors = [], [], [], []
        self.max_gap, self.gap_violations, self.raw_bytes = None, [], 0
        self.stopped = self.finished = False
        self.started = time.monotonic()

    def emit(self, event, **payload):
        self.stream.write(json.dumps({"event": event, **payload}, allow_nan=False) + "\n")
        self.stream.flush()

    def resources(self):
        P.require(
            time.monotonic() - self.started <= P.RESOURCE["capture_wall_limit_s"],
            "RESOURCE_ABORT capture wall",
        )
        P.require(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            <= P.RESOURCE["peak_rss_limit_bytes"],
            "RESOURCE_ABORT capture RSS",
        )
        other = sum(p.stat().st_size for p in self.directory.parent.iterdir() if p.is_file())
        P.require(
            self.raw_bytes + other <= P.RESOURCE["output_budget_bytes"],
            "RESOURCE_ABORT output budget",
        )
        P.require(
            shutil.disk_usage(self.directory).free >= P.RESOURCE["failure_free_disk_reserve_bytes"],
            "RESOURCE_ABORT failure reserve",
        )

    def observe_step(self, *, episode_id, physics_step, sim_time_s):
        self.physical_attempts += 1
        valid = (
            not self.stopped
            and not self.finished
            and episode_id == self.episode
            and type(physics_step) is int
            and physics_step == self.last_step + 1
            and P.finite(sim_time_s)
            and sim_time_s >= 0
            and (sim_time_s == 0 if physics_step == 0 else sim_time_s > self.last_time)
        )
        if not valid:
            self.stopped = True
            # Preserve malformed bool/NaN/Inf declarations as repr strings.
            # This avoids emitting invalid JSON numbers.
            self.emit(
                "REJECTED",
                declared_episode=repr(episode_id),
                declared_step=repr(physics_step),
                declared_sim_time_s=repr(sim_time_s),
                reason="callback identity/sequence/time differs",
            )
            raise ValueError("physical callback identity/sequence/time differs")
        self.emit(
            "PHYSICAL_CALLBACK",
            episode_id=episode_id,
            physics_step=physics_step,
            sim_time_s=sim_time_s,
        )
        if self.last_time is not None:
            gap = sim_time_s - self.last_time
            self.max_gap = max(self.max_gap or 0, gap)
            if not 0 < gap <= self.requirement:
                self.gap_violations.append(physics_step)
        self.last_step, self.last_time = physics_step, sim_time_s
        self.physical_callbacks += 1

    def record_step(self, *, episode_id, physics_step, sim_time_s):
        P.require(
            not self.stopped
            and not self.finished
            and episode_id == self.episode
            and type(physics_step) is int
            and physics_step == self.last_step
            and P.finite(sim_time_s)
            and sim_time_s == self.last_time
            and (not self.attempts or physics_step != self.attempts[-1]),
            "one allocation per actual current callback required",
        )
        identity = dict(episode_id=episode_id, physics_step=physics_step, sim_time_s=sim_time_s)
        self.attempts.append(physics_step)
        path = self.directory / f"frames/{physics_step:07d}.json.gz"
        try:
            self.emit("BEGIN", **identity, capture_monotonic_begin_ns=time.monotonic_ns())
            self.resources()
            observation, hashes = self.capture()
            P.require(
                observation.episode_id == episode_id
                and P.finite(observation.sim_time_s)
                and observation.sim_time_s == sim_time_s
                and len(hashes) == 2
                and hashes[0] == hashes[1],
                "full observation identity/registered passes differ",
            )
            raw = observation.model_dump_json().encode()
            P.require(
                len(raw) <= P.RESOURCE["max_frame_json_bytes"], "RESOURCE_ABORT frame JSON limit"
            )
            zipped = gzip.compress(raw, compresslevel=1, mtime=0)
            with path.open("xb") as stream:
                stream.write(zipped)
            self.raw_bytes += len(zipped)
            row = {
                **identity,
                "schema": "research.full-marker-v4-index.v1",
                "file": f"frames/{physics_step:07d}.json.gz",
                "observation_id": observation.observation_id,
                "checksum": observation.checksum_sha256,
                "original_sha256": P.digest(raw),
                "compressed_sha256": P.digest(zipped),
                "original_bytes": len(raw),
                "compressed_bytes": len(zipped),
                "pass_state_hashes": hashes,
                "capture_monotonic_end_ns": time.monotonic_ns(),
            }
            self.emit("END", **row)
            self.saved.append(physics_step)
            return {"event": "END", **row}
        except BaseException as error:
            self.stopped = True
            self.failures.append(physics_step)
            try:
                self.emit(
                    "FAILED",
                    **identity,
                    file=str(path.relative_to(self.directory)),
                    retained_file_exists=path.exists(),
                    retained_file_bytes=path.stat().st_size if path.exists() else 0,
                    camera_evidence=getattr(self.capture, "last_capture", None),
                    error_type=type(error).__name__,
                    error=str(error),
                )
            except BaseException as publication_error:
                note = "FAILED index publication failed: " + repr(publication_error)
                self.publication_errors.append(note)
                error.add_note(note)
            raise

    def finish(self, *, final_step, final_sim_time_s):
        if self.finished:
            raise RuntimeError("one finish only")
        self.finished = True
        planned = set(range(self.expected_physics_steps + 1))
        missing, extra = sorted(planned - set(self.saved)), sorted(set(self.saved) - planned)
        reasons = []
        if type(final_step) is not int or final_step != self.expected_physics_steps:
            reasons.append("exact original physics horizon differs; actual callbacks retained")
        if (
            not P.finite(final_sim_time_s)
            or self.last_time != final_sim_time_s
            or self.last_step != final_step
        ):
            reasons.append("terminal/callback step or SimulationS differs")
        if (
            missing
            or extra
            or self.physical_attempts != self.physical_callbacks
            or self.physical_callbacks != len(planned)
        ):
            reasons.append("exact callback/allocation/raw range incomplete")
        if self.stopped or self.failures or self.publication_errors:
            reasons.append("retained acquisition or publication failure")
        if self.gap_violations:
            reasons.append("actual SimulationS gap exceeds strict admission bound")
        guard = None
        try:
            P.require(callable(self.final_guard), "missing FINAL_GUARD provider")
            guard = self.final_guard()
            camera = getattr(self.capture, "last_capture", None)
            P.require(
                camera is not None
                and P.same(guard["guard"], camera["after_guard"])
                and P.same(guard["state"], camera["after_state"]),
                "FINAL_GUARD differs from last camera after snapshot",
            )
            self.emit(
                "FINAL_GUARD",
                episode_id=self.episode,
                physics_step=self.last_step,
                sim_time_s=self.last_time,
                snapshot=guard,
            )
        except BaseException as error:
            reasons.append("FINAL_GUARD unavailable or mismatched: " + repr(error))
            try:
                self.emit(
                    "FINAL_GUARD_FAILED",
                    error_type=type(error).__name__,
                    error=str(error),
                    snapshot=guard,
                )
            except BaseException as publication_error:
                self.publication_errors.append(
                    "FINAL_GUARD failure publication: " + repr(publication_error)
                )
        summary = dict(
            status="COMPLETE" if not reasons else "INCOMPLETE",
            scope=P.SCOPE,
            episode_id=self.episode,
            expected_frame_count=self.expected_physics_steps + 1,
            expected_physics_steps=self.expected_physics_steps,
            physical_callback_attempts=self.physical_attempts,
            physical_callbacks=self.physical_callbacks,
            allocated_steps=self.attempts,
            saved_steps=self.saved,
            failed_steps=self.failures,
            missing_steps=missing,
            extra_steps=extra,
            final_step=final_step,
            final_sim_time_s=final_sim_time_s,
            recipe_range_status="MATCH"
            if type(final_step) is int and final_step == self.expected_physics_steps
            else "RECIPE_DEVIATION",
            reasons=reasons,
            publication_errors=self.publication_errors,
            max_sample_gap_s=self.max_gap,
            sampling_gap_violation_steps=self.gap_violations,
            raw_compressed_bytes=self.raw_bytes,
            continuous_visibility="NOT_ESTABLISHED",
            native_admission="NOT_PROMOTED",
        )
        try:
            self.emit("FINISH", summary=summary)
            P.write_new(self.directory / "summary.json", summary)
        finally:
            self.stream.close()
        return summary


def load_runner():
    return P.load_pinned(BASE, BASE_SHA, "round57_isolated_v3_runner")


def configured_runner(header):
    P.validate_full_header(header)
    base = load_runner()
    original_adapter, original_coordinator = base.CaptureAdapter, base.AcquisitionCoordinator
    prepared = P.load_pinned(
        P.SPARSE / "prepare.py",
        "57ec9a6e1cb5dee420387f242b0e05fdd668766c264cbbc4b22040e6a3144a47",
        "round57_pure_v4_asset",
    )

    def specification():
        previous = load_runner()
        scene, config = previous.specification()
        asset = P.SPARSE / "scene_pose_marker_outboard_v4.xml"
        prepared.validate_candidate(prepared.OLD.read_bytes(), asset.read_bytes())
        scene = base.SceneSpec.from_parameters(scene.scene_parameters, P.ASSET_SHA, seed=scene.seed)
        scene = base.SceneSpec.model_validate(
            {**scene.model_dump(), "group_id": "dev-marker-v4-full-" + scene.scene_hash[:24]}
        )
        config = type(config).model_validate(
            {**config.model_dump(), "model_path": str(asset.relative_to(ROOT))}
        )
        return scene, config

    class FullStateAdapter(original_adapter):
        def __call__(self):
            backend = self.backend
            pose = dict(
                episode_id=backend._episode_id,
                physics_step=backend.total_physics_steps,
                sim_time_s=backend.get_sim_time(),
                camera_state=backend._operation_camera_state(),
            )
            prepared.preview_readiness(
                [pose["physics_step"]], {pose["physics_step"]: pose}, pose["episode_id"]
            )
            try:
                result = super().__call__()
                return result
            finally:
                if self.last_capture is not None:
                    self.last_capture["full_capture_state"] = base.plain(pose)
                    self.last_capture["operation_ledger_prefix_count"] = len(
                        backend._operation_ledger
                    )
                    self.last_capture["truth_scope"] = (
                        "OFFLINE_CAPTURE_STATE_ONLY_NEVER_DECODER_INPUT"
                    )

    class FullCoordinator(original_coordinator):
        def __init__(self, backend, journal, series, tracker, adapter):
            super().__init__(backend, journal, series, tracker, adapter)

            def final_guard():
                journal.ensure(backend)
                snapshot = base.capture_state(backend, adapter.contract)
                prefix = adapter.last_capture["operation_ledger_prefix_count"]
                suffix = backend._operation_ledger[prefix:]
                P.require(
                    not any(
                        r.kind in {"PHYSICS", "CONTROL", "COMMAND"}
                        if hasattr(r, "kind")
                        else r["kind"] in {"PHYSICS", "CONTROL", "COMMAND"}
                        for r in suffix
                    ),
                    "new physical/control/command after last capture",
                )
                snapshot.update(
                    episode_id=backend._episode_id,
                    physics_step=backend.total_physics_steps,
                    sim_time_s=backend.get_sim_time(),
                    command_count=len(backend.command_records),
                    operation_ledger_count=len(backend._operation_ledger),
                    operation_ledger_sha256=P.digest(base.json_bytes(backend._operation_ledger)),
                    last_capture_operation_ledger_prefix_count=prefix,
                )
                journal.emit("FINAL_GUARD", **snapshot)
                return snapshot

            series.final_guard = final_guard

        def record(self, snapshot):
            self.series.observe_step(
                episode_id=snapshot.episode_id,
                physics_step=snapshot.physics_step,
                sim_time_s=snapshot.sim_time_s,
            )
            try:
                return super().record(snapshot)
            except BaseException:
                self.series.stopped = True
                raise

    def recorder(directory, capture, *, episode_id, max_sample_gap_s):
        return FullRGBDRecorder(
            directory,
            capture,
            episode_id=episode_id,
            max_sample_gap_s=max_sample_gap_s,
            expected_physics_steps=header["expected_physics_steps"],
        )

    base.PROTOCOL, base.specification = P.PROTOCOL, specification
    base.source_preflight = lambda h, d: P.source_preflight(base, h, d)
    base.CaptureAdapter, base.AcquisitionCoordinator = FullStateAdapter, FullCoordinator
    base.StepRGBDRecorder = recorder
    return base


def execute_once(directory):
    directory = Path(directory)
    header = json.loads((directory / "header.json").read_text())
    P.validate_full_header(header)
    if (directory / "attempt-1").exists():
        raise FileExistsError("one actual attempt only; existing attempt retained")
    P.source_preflight(None, header, directory)
    P.require_resources(directory)
    base = configured_runner(header)
    base.execute_once(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute-once", action="store_true")
    parser.add_argument("--protocol-directory", required=True, type=Path)
    args = parser.parse_args()
    allowed = (HERE / "full-protocol").resolve()
    if args.protocol_directory.resolve() != allowed:
        raise ValueError("only the new full protocol CLI destination permitted")
    if args.prepare:
        print(json.dumps(P.freeze_full(args.protocol_directory)))
    else:
        execute_once(args.protocol_directory)
