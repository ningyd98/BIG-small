"""Fresh excluded sparse teacher pilot. Preparation/tests never construct a model.

Execution is a separately reviewed root-owned one-attempt command. The frozen
V3 teacher/control/guard machinery is reused in an isolated module namespace;
its files and old raw are never edited. StepRGBDRecorder is not used for sparse
storage or stability acceptance. No decoder/provider/hardware is called here.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
DEV = ROOT / "artifacts/research/process/20261004-ced-development"
BASE = DEV / "t7b-continuous-visibility-v3/run_once.py"
BASE_SHA = "0f7c5d31f21bd35a5d7085e57376436b6bf33f043c47fe227542d6d94d654340"
PROTOCOL = "research.custom-sparse-guarded-marker-v4.v1"


def load_prepare():
    spec = importlib.util.spec_from_file_location("ced_v4_preparation", HERE / "prepare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load_prepare()


def load_frozen_runner(path=BASE):
    if not path.is_file() or P.digest(path.read_bytes()) != BASE_SHA:
        raise RuntimeError("frozen runner bytes unavailable or changed")
    spec = importlib.util.spec_from_file_location("ced_v4_frozen_teacher_runner", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def specification(base):
    prior_scene, prior_config = base.specification()
    asset = HERE / "scene_pose_marker_outboard_v4.xml"
    P.validate_candidate(P.OLD.read_bytes(), asset.read_bytes())
    scene = base.SceneSpec.from_parameters(
        prior_scene.scene_parameters, P.digest(asset.read_bytes()), seed=prior_scene.seed
    )
    scene = base.SceneSpec.model_validate(
        {**scene.model_dump(), "group_id": "dev-marker-v4-sparse-" + scene.scene_hash[:24]}
    )
    config = type(prior_config).model_validate(
        {**prior_config.model_dump(), "model_path": str(asset.relative_to(ROOT))}
    )
    return scene, config


class SparseRGBDRecorder:
    """Preserve every callback and selected attempt, with an explicit sparse contract."""

    def __init__(self, directory, capture, *, episode_id, selected_steps, max_sample_gap_s):
        self.directory = Path(directory)
        self.directory.mkdir()
        (self.directory / "frames").mkdir()
        self.stream = (self.directory / "index.jsonl").open("x")
        self.capture, self.episode = capture, episode_id
        self.selected = tuple(selected_steps)
        if list(self.selected) != sorted(set(self.selected)) or not self.selected:
            raise ValueError("unique ordered predeclared steps required")
        self.requirement = max_sample_gap_s
        self.physical_attempts = self.physical_callbacks = 0
        self.last_step, self.last_time = -1, None
        self.attempts, self.saved = [], []
        self.saved_times, self.failures, self.publication_errors = [], [], []
        self.stopped = False

    def emit(self, event, **payload):
        self.stream.write(json.dumps({"event": event, **payload}, allow_nan=False) + "\n")
        self.stream.flush()

    def observe_step(self, *, episode_id, physics_step, sim_time_s):
        self.physical_attempts += 1
        if (
            episode_id != self.episode
            or type(physics_step) is not int
            or physics_step != self.last_step + 1
            or not math.isfinite(sim_time_s)
            or sim_time_s < 0
            or (self.last_time is not None and sim_time_s <= self.last_time)
        ):
            self.stopped = True
            raise ValueError("physical callback identity/sequence/time differs")
        self.emit(
            "PHYSICAL_CALLBACK",
            episode_id=episode_id,
            physics_step=physics_step,
            sim_time_s=sim_time_s,
            selected=physics_step in self.selected,
        )
        self.last_step, self.last_time = physics_step, sim_time_s
        self.physical_callbacks += 1

    def record_step(self, *, episode_id, physics_step, sim_time_s):
        if (
            self.stopped
            or physics_step not in self.selected
            or physics_step in self.attempts
            or episode_id != self.episode
            or physics_step != self.last_step
            or sim_time_s != self.last_time
        ):
            raise ValueError("one attempt at the predeclared current step required")
        identity = dict(episode_id=episode_id, physics_step=physics_step, sim_time_s=sim_time_s)
        self.attempts.append(physics_step)
        try:
            self.emit("BEGIN", **identity, capture_monotonic_begin_ns=time.monotonic_ns())
            observation, hashes = self.capture()
            if (
                observation.episode_id != episode_id
                or observation.sim_time_s != sim_time_s
                or len(hashes) != 2
                or hashes[0] != hashes[1]
            ):
                raise ValueError("sparse observation identity/registered passes differ")
            raw = observation.model_dump_json().encode()
            zipped = gzip.compress(raw, compresslevel=1, mtime=0)
            filename = f"frames/{physics_step:07d}.json.gz"
            with (self.directory / filename).open("xb") as stream:
                stream.write(zipped)
            row = {
                **identity,
                "file": filename,
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
            self.saved_times.append(sim_time_s)
            return row
        except BaseException as error:
            self.stopped = True
            self.failures.append(physics_step)
            try:
                self.emit("FAILED", **identity, error_type=type(error).__name__, error=str(error))
            except BaseException as publication_error:
                note = "sparse FAILED publication failed: " + repr(publication_error)
                self.publication_errors.append(note)
                error.add_note(note)
            raise

    def finish(self, *, final_step, final_sim_time_s):
        missing = sorted(set(self.selected) - set(self.saved))
        complete = (
            not self.stopped
            and not missing
            and self.last_step == final_step
            and self.last_time == final_sim_time_s
            and self.physical_callbacks == self.physical_attempts == final_step + 1
        )
        summary = {
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "scope": "SPARSE_PREDECLARED_STEPS_ONLY",
            "episode_id": self.episode,
            "physical_callback_attempts": self.physical_attempts,
            "physical_callbacks": self.physical_callbacks,
            "planned_selected_steps": list(self.selected),
            "allocated_steps": self.attempts,
            "saved_steps": self.saved,
            "failed_steps": self.failures,
            "missing_selected_steps": missing,
            "final_step": final_step,
            "final_sim_time_s": final_sim_time_s,
            "publication_errors": self.publication_errors,
            "original_stability_gap_requirement_s": self.requirement,
            "sparse_max_gap_s": max(
                (b - a for a, b in zip(self.saved_times[:-1], self.saved_times[1:], strict=True)),
                default=None,
            ),
            "continuous_visibility": "NOT_ESTABLISHED",
            "native_admission": "NOT_PROMOTED",
        }
        try:
            self.emit("FINISH", summary=summary)
            P.write_new(self.directory / "summary.json", summary)
        finally:
            self.stream.close()
        return summary


def original_pins(selection):
    for member in [*selection["input_pins"], *selection["original_frames"]]:
        data = (ROOT / member["path"]).read_bytes()
        if len(data) != member["bytes"] or P.digest(data) != member["sha256"]:
            raise RuntimeError("original immutable input changed: " + member["path"])


def source_preflight(base, header, directory):
    for filename, key in (
        ("execution-source-hashes.json", "source_manifest_sha256"),
        ("execution-archive-index.json", "source_archive_index_sha256"),
    ):
        if P.digest((directory / filename).read_bytes()) != header[key]:
            raise RuntimeError("prepared source metadata changed")
    sources = json.loads((directory / "execution-source-hashes.json").read_text())
    index = json.loads((directory / "execution-archive-index.json").read_text())
    if set(sources) != set(index) or len(sources) != header["source_count"]:
        raise RuntimeError("necessary source inventory changed")
    for name, expected in sources.items():
        live = (ROOT / name).read_bytes()
        archived = (ROOT / index[name]["archive"]).read_bytes()
        if (
            P.digest(live) != expected
            or P.digest(archived) != expected
            or index[name]["sha256"] != expected
            or len(live) != index[name]["bytes"]
        ):
            raise RuntimeError("frozen necessary source changed: " + name)
    guard_name = "src/cloud_edge_robot_arm/research/mujoco_state_guard.py"
    if (
        sources.get(guard_name) != header["guard_core_sha256"]
        or P.digest(Path(base.state_guard.__file__).read_bytes()) != header["guard_core_sha256"]
    ):
        raise RuntimeError("loaded guard/source differs")
    for member in header["environment"]["files"].values():
        if P.digest(Path(member["path"]).read_bytes()) != member["sha256"]:
            raise RuntimeError("frozen environment changed")
    if (
        header["protocol"] != PROTOCOL
        or header["capture_policy"] != "PREDECLARED_SPARSE_STEPS_ONLY"
    ):
        raise RuntimeError("sparse protocol differs")
    selection_path = HERE / "selection-manifest.json"
    if P.digest(selection_path.read_bytes()) != header["selection_manifest_sha256"]:
        raise RuntimeError("original selection manifest changed")
    selection = json.loads(selection_path.read_text())
    if (
        selection["selected_steps"] != header["selected_steps"]
        or len(header["selected_steps"]) != 201
    ):
        raise RuntimeError("fixed selected denominator changed")
    original_pins(selection)
    return base.state_guard.MujocoStateContract(
        Path(header["guard_headers"]["mjxmacro.h"]).read_bytes(),
        Path(header["guard_headers"]["mjdata.h"]).read_bytes(),
        header["guard_binding_sha256"],
        header["environment"]["mujoco_version"],
    )


def configured_runner(header):
    base = load_frozen_runner()
    selected = tuple(header["selected_steps"])
    original_adapter, original_coordinator = base.CaptureAdapter, base.AcquisitionCoordinator

    class FullStateAdapter(original_adapter):
        def __call__(self):
            backend = self.backend
            pose = {
                "episode_id": backend._episode_id,
                "physics_step": backend.total_physics_steps,
                "sim_time_s": backend.get_sim_time(),
                "camera_state": backend._operation_camera_state(),
            }
            P.preview_readiness(
                [pose["physics_step"]], {pose["physics_step"]: pose}, pose["episode_id"]
            )
            try:
                return super().__call__()
            finally:
                if self.last_capture is not None:
                    self.last_capture["full_capture_state"] = base.plain(pose)
                    self.last_capture["truth_scope"] = (
                        "OFFLINE_CAPTURE_STATE_ONLY_NEVER_DECODER_INPUT"
                    )

    class SparseCoordinator(original_coordinator):
        def record(self, snapshot):
            self.series.observe_step(
                episode_id=snapshot.episode_id,
                physics_step=snapshot.physics_step,
                sim_time_s=snapshot.sim_time_s,
            )
            if snapshot.physics_step in selected:
                return super().record(snapshot)
            return None

    def recorder(directory, capture, *, episode_id, max_sample_gap_s):
        return SparseRGBDRecorder(
            directory,
            capture,
            episode_id=episode_id,
            selected_steps=selected,
            max_sample_gap_s=max_sample_gap_s,
        )

    base.PROTOCOL = PROTOCOL
    base.specification = lambda: specification(load_frozen_runner())
    base.source_preflight = lambda h, d: source_preflight(base, h, d)
    base.CaptureAdapter, base.AcquisitionCoordinator = FullStateAdapter, SparseCoordinator
    base.StepRGBDRecorder = recorder  # Compatibility injection; this is not StepRGBDRecorder.
    return base


def protocol_directory(directory):
    directory = Path(directory).resolve()
    if directory != (HERE / "pilot-protocol").resolve():
        raise RuntimeError("only independently reviewed fresh pilot protocol directory permitted")
    return directory


def prepare(directory):
    directory = protocol_directory(directory)
    directory.mkdir()
    base = load_frozen_runner()
    scene, config = specification(base)
    old = DEV / "t7b-continuous-visibility-v3/fix-round-1"
    sources = json.loads((old / "execution-source-hashes.json").read_text())
    old_index = json.loads((old / "execution-archive-index.json").read_text())
    excluded = str((BASE.parent / "verify_offline.py").relative_to(ROOT))
    del sources[excluded]
    index = {
        name: {
            **old_index[name],
            "archive": str((DEV / old_index[name]["archive"]).relative_to(ROOT)),
        }
        for name in sources
    }
    own = [
        HERE / name
        for name in ("prepare.py", "run_sparse_once.py", "scene_pose_marker_outboard_v4.xml")
    ]
    archive = directory / "source-final"
    archive.mkdir()
    for path in own:
        name, data = str(path.relative_to(ROOT)), path.read_bytes()
        target = archive / path.name
        target.write_bytes(data)
        sources[name] = P.digest(data)
        index[name] = {
            "archive": str(target.relative_to(ROOT)),
            "sha256": P.digest(data),
            "bytes": len(data),
        }
    P.write_new(directory / "execution-source-hashes.json", sources)
    P.write_new(directory / "execution-archive-index.json", index)
    selection = json.loads((HERE / "selection-manifest.json").read_text())
    header = json.loads((old / "header.json").read_text())
    header.update(
        protocol=PROTOCOL,
        scope="EXCLUDED_SAME_COMPONENT_SPARSE_MARKER_V4_PILOT",
        scene=scene.model_dump(mode="json"),
        config=config.model_dump(mode="json"),
        scene_hash=scene.scene_hash,
        asset_sha256=scene.asset_family_hash,
        source_manifest_sha256=P.digest((directory / "execution-source-hashes.json").read_bytes()),
        source_archive_index_sha256=P.digest(
            (directory / "execution-archive-index.json").read_bytes()
        ),
        source_count=len(sources),
        source_bytes=sum((ROOT / n).stat().st_size for n in sources),
        archive_root=str(ROOT),
        capture_policy="PREDECLARED_SPARSE_STEPS_ONLY",
        selection_manifest_sha256=P.digest((HERE / "selection-manifest.json").read_bytes()),
        selected_steps=selection["selected_steps"],
        selected_frame_budget=201,
        expected_physics_steps=4806,
        expected_physics_steps_is_admission_gate=False,
        sparse_capture_render_pass_budget=402,
        existing_boundary_render_pass_estimate=33,
        setup_render_pass_estimate=2,
        total_render_pass_estimate=437,
        marker_registration={
            "marker_id": 7,
            "marker_size_m": 0.075,
            "marked_asset_sha256": scene.asset_family_hash,
        },
        marker_local_attachment_m=[0.16, 0, 0.03505],
        old_pose_reconstructed=False,
        old_attempt_retried=False,
        sparse_stability_requirement_satisfied="NOT_CLAIMED",
        continuous_motion="NOT_CERTIFIED",
        native_admission="NOT_PROMOTED",
    )
    P.write_new(directory / "header.json", header)
    source_preflight(base, header, directory)
    print(
        json.dumps(
            {
                "status": "PREPARED_NO_ACTUAL_CALLS",
                "source_count": len(sources),
                "selected_frames": 201,
                "expected_physics_steps": 4806,
                "actual_calls": 0,
            }
        )
    )


def execute_once(directory):
    directory = protocol_directory(directory)
    header = json.loads((directory / "header.json").read_text())
    base = configured_runner(header)
    base.execute_once(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute-once", action="store_true")
    parser.add_argument("--protocol-directory", required=True, type=Path)
    args = parser.parse_args()
    prepare(args.protocol_directory) if args.prepare else execute_once(args.protocol_directory)
