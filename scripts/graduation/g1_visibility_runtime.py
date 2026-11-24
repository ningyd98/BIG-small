"""Build and identify the isolated development observer in the original eight-skill runtime."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from scripts.graduation import g1_formal_runtime as parent_build
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

BASE = "742296625a618b216bbb4d9c1279ea3e22ee9f0d"
PLAN_SHA = "9fe2d5f7a514a62ebdac454107360f9077a71feb9809b6e93e02a4c8e15c3ef7"
ROUNDS = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
PLAN = ROUNDS / "round-g1-visibility-pose-repair-20261124/plan.json"
PREVIOUS = ROUNDS / "round-g1-formal-paired-20261124"
DEVELOPMENT = ROUNDS / "round-g1-first-refusal-dual-marker-20261124/trial-allocation.public.json"
PRIVATE = Path("experiments/results/g1-visibility-pose-repair-20261124")
PARENT = Path("experiments/results/g1-formal-paired-20261124")
PREFIX = "scripts/graduation/"
DETECTOR = PREFIX + "g1_visibility_vision.py"
GRID = PREFIX + "g1_visibility_grid.py"
RUNNER = PREFIX + "g1_visibility_trials.py"
BUILDER = PREFIX + "g1_visibility_runtime.py"
OBSERVER = PREFIX + "g1_dual_observer.py"
ASSET = PREFIX + "g1_dual_asset.py"
CAPTURE = PREFIX + "g1_mount_trials.py"
VISION = PREFIX + "dynamic_vision.py"
SCORERS = tuple(
    PREFIX + name + ".py"
    for name in (
        "g1_dual_batch_score",
        "g1_dual_pixel_readback",
        "g1_mount_score",
        "dynamic_vision_score",
        "proposal_scoring",
    )
)
CONTROL_MODE = "G1_VISIBILITY_DEVELOPMENT"
_active_measurements = ContextVar("g1_development_actual_measurements", default=None)
require = parent_build.require


@contextmanager
def log_measurements():
    """Trace actual observer calls for evidence, independently of control and frame selection."""
    frames = {}
    token = _active_measurements.set(frames)
    try:
        yield frames
    finally:
        _active_measurements.reset(token)


def record_measurement(result, consumer):
    frames = _active_measurements.get()
    if frames is None:
        return
    frame_id = result["frame_id"]
    row = frames.setdefault(frame_id, {"measurement": result, "callers": {}})
    require(row["measurement"] == result, "same frame produced different online measurements")
    counts = row["callers"]
    counts[consumer] = counts.get(consumer, 0) + 1


def replace_once(source, before, after):
    require(source.count(before) == 1, "unexpected source anchor: " + before)
    return source.replace(before, after)


def adapted_sources(parent, detectors):
    """Retain the pinned physics, camera, controller, stage gates and rigid transforms."""
    code = {name: (parent / name).read_text() for name in (OBSERVER, ASSET, CAPTURE, VISION)}
    observer = code[OBSERVER]
    # Preserve the original dual registration, camera and scene checks, and its public adapters.
    start = observer.index("def measure_frame(")
    gate_end = observer.index("    with Image.open(", start)
    consumer_start = observer.index("def derive(", gate_end)
    validate = observer[start:gate_end].replace(
        "def measure_frame(observation, geometry):",
        'def measure_frame(observation, geometry, *, consumer="blind_readback"):',
    )
    consumers = observer[consumer_start:]
    for name, following, argument in (
        ("derive", "servo_measure", "geometry"),
        ("servo_measure", "selected_id", "geometry"),
        ("matches_current_owner", None, "payload"),
    ):
        begin = consumers.index("def " + name + "(")
        end = consumers.index("def " + following + "(", begin) if following else len(consumers)
        section = replace_once(
            consumers[begin:end],
            "result = measure_frame(frame, " + argument + ")",
            f'result = measure_frame(frame, {argument}, consumer="{name}")',
        )
        consumers = consumers[:begin] + section + consumers[end:]
    imports = (
        "from scripts.graduation import g1_visibility_vision as visibility\n"
        "from scripts.graduation.g1_visibility_runtime import record_measurement\n"
    )
    # Older quad/plane estimators have no active call site in this generation.
    code[OBSERVER] = (
        observer[: observer.index("def physical_candidates(")]
        + imports
        + "\n\n"
        + observer[observer.index("def _empty_side(") : observer.index("def _measure_side(")]
        + validate
        + "    result = visibility.measure_frame(frame, geometry)\n"
        + "    record_measurement(result, consumer)\n    return result\n\n\n"
        + "_pose_estimate = visibility.pose_estimate\n\n\n"
        + consumers
    )
    extra = ", ".join(repr(name) for name in (*detectors, BUILDER))
    code[ASSET] = replace_once(code[ASSET], "POSES = (", f"SOURCE_FILES += ({extra},)\nPOSES = (")
    code[CAPTURE] = replace_once(
        code[CAPTURE],
        'egl_lock=str(raw.parent / "egl.lock")',
        'egl_lock=str(raw.parent.parent / "egl.lock")',
    )
    for name in (VISION, CAPTURE):
        code[name] = replace_once(code[name], "FORMAL_G1_PAIRED", CONTROL_MODE)
    require(code[VISION].count("g1_formal_paired") == 2, "foreign worker reason codes")
    code[VISION] = code[VISION].replace("g1_formal_paired", "g1_visibility_development")
    code[VISION] = replace_once(code[VISION], '"formal_identity":', '"development_identity":')
    code[VISION] = replace_once(
        code[VISION], "G1 paired MuJoCo worker", "G1 visibility development MuJoCo worker"
    )
    return {name: source.encode() for name, source in code.items()}


def context(repo):
    require(repo.resolve() == repo and (repo / ".git").exists(), "repo must be the worktree root")
    plan = pinned(repo / PLAN, PLAN_SHA)
    require(
        plan["baseline"] == BASE
        and Path(plan["new_private"]) == PRIVATE
        and sha(repo / PLAN.with_suffix(".md")) == plan["plan_md_sha256"],
        "foreign Astra plan",
    )
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=repo, check=True)
    private = repo / PRIVATE
    require(private.resolve() == private, "development output traverses a symbolic link")
    return plan, private


def check_history(repo, plan):
    """Read every plan input and verify the exact frozen data and formal ledger inventory."""
    for name, expected in plan["inputs_sha256"].items():
        require(sha(repo / name) == expected, "changed Astra input: " + name)
    source = repo / PARENT
    manifest = read(source / "originals-manifest.json")["files"]
    require(len(manifest) == 919, "incomplete formal originals manifest")
    found = {
        p.relative_to(source).as_posix()
        for root in ("trials", "claims")
        for p in (source / root).rglob("*")
        if p.is_file()
    }
    require(found == set(manifest), "formal ledger or originals inventory changed")
    for name, row in manifest.items():
        path = source / name
        require(
            not path.is_symlink()
            and path.stat().st_size == row["bytes"]
            and sha(path) == row["sha256"],
            "changed formal original: " + name,
        )
    return {
        "plan_inputs": len(plan["inputs_sha256"]),
        "formal_originals": len(found),
        "formal_manifest_sha256": sha(source / "originals-manifest.json"),
        "formal_claims": {
            name: row["sha256"] for name, row in manifest.items() if name.startswith("claims/")
        },
    }


def source_root(private, generation):
    require(
        isinstance(generation, str) and re.fullmatch(r"[0-9a-f]{64}", generation),
        "expected frozen build SHA256",
    )
    tree = private / "builds" / generation / "runtime-source"
    require(tree.resolve() == tree, "runtime tree traverses a symbolic link")
    return tree


def verify_build(private, generation):
    tree = source_root(private, generation)
    lock = pinned(tree / "runtime-build.json", generation)
    require(
        lock["schema"] == "g1.visibility.development-build.v1" and lock["plan_sha256"] == PLAN_SHA,
        "foreign development generation",
    )
    parent_build.check_tree(tree, lock["runtime_files_sha256"])
    return tree, lock


def prepare(repo, radial_mm=0):
    plan, private = context(repo)
    check_history(repo, plan)
    if radial_mm:
        return prepare_radial(repo, private, radial_mm)
    parent = repo / PARENT / "runtime-source"
    old = pinned(
        parent / "runtime-build.json",
        plan["inputs_sha256"][(PARENT / "runtime-source/runtime-build.json").as_posix()],
    )
    files = old["runtime_files_sha256"]
    parent_build.check_tree(parent, files, inherited=True)
    detector_files = (DETECTOR, GRID) if (repo / GRID).is_file() else (DETECTOR,)
    changes = adapted_sources(parent, detector_files)
    additions = {name: (repo / name).read_bytes() for name in (*detector_files, BUILDER, RUNNER)}
    require(not (set(additions) & set(files)), "development entry would shadow an inherited module")
    effective = {
        **files,
        **{k: hashlib.sha256(v).hexdigest() for k, v in (changes | additions).items()},
    }
    lock = dict(
        schema="g1.visibility.development-build.v1",
        plan_sha256=PLAN_SHA,
        baseline=BASE,
        parent_runtime_build_sha256=sha(parent / "runtime-build.json"),
        runtime_files_sha256=effective,
        detector_files_sha256={k: effective[k] for k in detector_files},
        source_changes={k: {"before": files[k], "after": effective[k]} for k in changes},
        scorer_files_sha256={k: effective[k] for k in (*SCORERS, RUNNER)},
        additional_files_sha256={k: effective[k] for k in additions},
    )
    return install_build(private, parent, changes | additions, lock)


def prepare_radial(repo, private, offset):
    from scripts.graduation import (
        g1_visibility_mount_runtime as mount,
    )
    from scripts.graduation import (
        g1_visibility_radial as fixture,
    )

    parent, prior = verify_build(private, mount.PARENT_GENERATION)
    mount.checked_plan(repo, parent)
    spec = mount.spec_for(offset)
    name = spec["asset_path"]
    source = fixture.build_xml((parent / mount.V2_XML).read_bytes(), offset)
    require(
        source == (repo / name).read_bytes()
        and hashlib.sha256(source).hexdigest() == spec["asset_sha256"],
        "registered radial asset bytes disagree",
    )
    require(
        all(sha(repo / file) == h for file, h in prior["detector_files_sha256"].items()),
        "radial-only build requires the released detector source",
    )
    changes = {
        ASSET: mount.provider_bytes((parent / ASSET).read_bytes(), offset),
        mount.READER: mount.reader_bytes((parent / mount.READER).read_bytes()),
        BUILDER: (repo / BUILDER).read_bytes(),
        RUNNER: (repo / RUNNER).read_bytes(),
    }
    additions = {
        name: source,
        mount.HELPER: (repo / mount.HELPER).read_bytes(),
        mount.ADAPTER: (repo / mount.ADAPTER).read_bytes(),
    }
    files = prior["runtime_files_sha256"]
    require(not (set(additions) & set(files)), "radial sources shadow their mechanical parent")
    effective = {
        **files,
        **{k: hashlib.sha256(v).hexdigest() for k, v in (changes | additions).items()},
    }
    lock = {
        **prior,
        "parent_runtime_build_sha256": mount.PARENT_GENERATION,
        "radial_assembly": spec,
        "radial_plan_sha256": mount.PLAN_SHA,
        "runtime_files_sha256": effective,
        "source_changes": {k: {"before": files[k], "after": effective[k]} for k in changes},
        "additional_files_sha256": {
            k: effective[k] for k in set(prior["additional_files_sha256"]) | set(additions)
        },
        "scorer_files_sha256": {k: effective[k] for k in prior["scorer_files_sha256"]},
    }
    return install_build(private, parent, changes | additions, lock)


def install_build(private, parent, updated, lock):
    effective = lock["runtime_files_sha256"]
    builds = private / "builds"
    builds.mkdir(parents=True, exist_ok=True)
    require(builds.resolve() == builds, "invalid build storage")
    with tempfile.TemporaryDirectory(dir=builds, prefix=".prepare-") as tmp:
        assembled = Path(tmp) / "generation"
        tree = assembled / "runtime-source"
        tree.mkdir(parents=True)
        write(tree / "runtime-build.json", lock)
        generation = sha(tree / "runtime-build.json")
        final = source_root(private, generation).parent
        if not final.exists():
            for name in effective:
                destination = tree / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if name in updated:
                    destination.write_bytes(updated[name])
                else:
                    shutil.copyfile(parent / name, destination)
            parent_build.check_tree(tree, effective)
            try:
                assembled.rename(final)
            except OSError:
                if not final.exists():
                    raise
    verify_build(private, generation)
    return generation


def isolated(repo, private, generation, arguments):
    tree, _ = verify_build(private, generation)
    if ROOT == tree == Path.cwd():
        return
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        PYTHONPATH=os.pathsep.join([str(tree), str(tree / "src")]),
    )
    os.chdir(tree)
    os.execve(
        sys.executable,
        [
            sys.executable,
            "-B",
            "-m",
            "scripts.graduation.g1_visibility_trials",
            "--repo",
            str(repo),
            *arguments,
        ],
        env,
    )
