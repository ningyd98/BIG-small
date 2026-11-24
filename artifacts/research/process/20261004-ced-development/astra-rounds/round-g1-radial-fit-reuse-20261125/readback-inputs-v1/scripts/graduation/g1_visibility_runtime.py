"""Build and identify the isolated development observer in the original eight-skill runtime."""

from __future__ import annotations

import hashlib
import math
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
TIMING_PARENT = "36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf"
TIMING_PARENT_PREFLIGHT = "90a4c0ed2ab0370e426acefabfc8eb1f991139c7b9178e0c654cf31df6a7723a"
TIMING_ROUND = ROUNDS / "round-g1-radial-native-timing-20261125"
TIMING_PLAN_SHA = "567e992a68593aecb32e73a3c3cd5bd9dc4a73d2c8ef2adb5146b91abc944171"
TIMING_RELEASE = TIMING_ROUND / "replay-release.public.json"
TIMING_BUDGET = TIMING_ROUND / "paired-budget.public.json"
TIMING_FILES = (GRID, DETECTOR, BUILDER, RUNNER, PREFIX + "g1_visibility_mount_runtime.py")
TIMING_DETECTOR_FILES = {
    GRID: "c0e80c0b3b36ad397a4d26146e9dc8c6d2063669dd28244bb9beb29f6b211e69",
    DETECTOR: "2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169",
}
# Published offline, before generation construction. An unqualified pair cannot produce a build.
TIMING_RELEASE_SHA = "284c149700f70b050fe92ddfc1d222fd105f229993becf0b8af1a78bc6cd2120"
TIMING_BUDGET_SHA = "f0c4c6577de723af06c63a4b31d06423787a7f8241bea3576afcf9c7300d867c"
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


def prepare(repo, radial_mm=0, radial_timing=None):
    plan, private = context(repo)
    check_history(repo, plan)
    if radial_timing is not None:
        require(radial_mm == 0, "performance overlay requires its registered 115 mm assembly")
        return prepare_timing(repo, private, radial_timing)
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


def qualified_timing_budget(record, detector):
    limits = dict(estimated_p95=80, estimated_max=90, pixel_p95=35, pixel_max=45)
    return (
        record.get("schema") == "g1.visibility.radial-paired-window-budget.v1"
        and record.get("eligible") is True
        and record.get("baseline_generation") == TIMING_PARENT
        and record.get("original_native_windows") == 123
        and record.get("detector_files_sha256") == detector
        and record.get("limits_ms") == limits
        and all(
            type(value := record.get(key + "_ms")) in (float, int)
            and math.isfinite(value)
            and 0 <= value <= limit
            for key, limit in limits.items()
        )
        and record["estimated_p95_ms"] <= record["estimated_max_ms"]
        and record["pixel_p95_ms"] <= record["pixel_max_ms"]
    )


def timing_files_ok(prior, files, release):
    detectors = release["detector_files_sha256"]
    previous = prior["runtime_files_sha256"]
    return (
        files.keys() == previous.keys()
        and detectors.keys() == {GRID, DETECTOR}
        and all(files[k] == v for k, v in detectors.items())
        and all(files[k] == previous[k] for k in files.keys() - set(TIMING_FILES))
    )


def timing_qualification(repo, requested_sha):
    """Require the independently sealed semantics, pixel timing and matched full-window budget."""
    require(
        isinstance(requested_sha, str) and re.fullmatch(r"[0-9a-f]{64}", requested_sha),
        "a radial semantic-release SHA256 is required",
    )
    budget = pinned(repo / TIMING_BUDGET, TIMING_BUDGET_SHA)
    require(
        qualified_timing_budget(budget, TIMING_DETECTOR_FILES),
        "unreleased radial timing candidate: same-frame window budget has not qualified",
    )
    require(requested_sha == TIMING_RELEASE_SHA, "unreleased radial detector or semantic evidence")
    plan = pinned(repo / TIMING_ROUND / "plan.json", TIMING_PLAN_SHA)
    require(
        plan["failed_generation"] == TIMING_PARENT
        and sha(repo / TIMING_ROUND / "plan.md") == plan["plan_md_sha256"],
        "foreign timing plan or mechanical parent",
    )
    for name, digest in plan["inputs_sha256"].items():
        require(sha(repo / name) == digest, "changed timing plan input: " + name)
    release = pinned(repo / TIMING_RELEASE, requested_sha)
    tests = dict(
        schema="g1.visibility.offline-release.v1",
        plan_sha256=PLAN_SHA,
        timing_plan_sha256=TIMING_PLAN_SHA,
        baseline_runtime_build_sha256=TIMING_PARENT,
        radial_offset_mm=15,
        eligible=True,
        historical_frames=778,
        first_refusals_recovered=8,
        positive_controls=4,
        negative_controls=16,
        false_positive_controls=0,
        control_witnesses=True,
        same_all_fields=True,
        d02_frames=[75, 130, 130],
        d02_all_fields_equal=True,
        static_anchors=22,
        static_pixel_inputs=44,
        static_all_fields_equal=True,
        static_geometry_qualified=True,
        new_formal_trials=0,
        real_hardware_trials=0,
    )
    require(
        all(release.get(k) == v for k, v in tests.items())
        and release["historical_gates"]
        and all(release["historical_gates"].values()),
        "offline timing candidate has not qualified",
    )
    detectors = release["detector_files_sha256"]
    require(
        detectors == TIMING_DETECTOR_FILES and qualified_timing_budget(budget, detectors),
        "timing software or same-frame window budget has not qualified",
    )
    for report in (release, budget):
        sources = report["input_artifacts_sha256"]
        require(sources, "radial timing release lacks underlying evidence")
        for name, digest in sources.items():
            path = repo / name
            require(
                not Path(name).is_absolute()
                and path.resolve().is_relative_to(repo)
                and sha(path) == digest,
                "changed or foreign timing evidence: " + name,
            )
    sample_file = (TIMING_ROUND / "pixel-timing-samples.public.json.gz").as_posix()
    require(
        budget["input_artifacts_sha256"].get(sample_file) == budget["samples_sha256"],
        "paired window budget does not bind the per-frame samples",
    )
    return dict(
        timing_plan_sha256=TIMING_PLAN_SHA,
        baseline_runtime_build_sha256=TIMING_PARENT,
        baseline_preflight_sha256=TIMING_PARENT_PREFLIGHT,
        replay_release_sha256=requested_sha,
        paired_budget_sha256=TIMING_BUDGET_SHA,
        detector_files_sha256=detectors,
    )


def prepare_timing(repo, private, requested_sha):
    from scripts.graduation import g1_visibility_mount_runtime as mount

    qualification = timing_qualification(repo, requested_sha)
    parent, prior = verify_build(private, TIMING_PARENT)
    pinned(parent.parent / "preflight.json", TIMING_PARENT_PREFLIGHT)
    mechanical, _ = verify_build(private, mount.PARENT_GENERATION)
    mount.checked_plan(repo, mechanical, frozen_detectors=True)
    require(prior["radial_assembly"] == mount.spec_for(15), "wrong mechanical parent assembly")
    overlays = {name: (repo / name).read_bytes() for name in TIMING_FILES}
    files = {
        **prior["runtime_files_sha256"],
        **{k: hashlib.sha256(v).hexdigest() for k, v in overlays.items()},
    }
    lock = timing_manifest(prior, files, qualification)
    return install_build(private, parent, overlays, lock)


def timing_manifest(prior, files, qualification):
    require(
        timing_files_ok(prior, files, qualification), "unexpected radial timing source or detector"
    )
    return {
        **prior,
        "parent_runtime_build_sha256": TIMING_PARENT,
        "radial_timing": qualification,
        "runtime_files_sha256": files,
        "detector_files_sha256": qualification["detector_files_sha256"],
        "source_changes": {
            k: {"before": prior["runtime_files_sha256"][k], "after": files[k]} for k in TIMING_FILES
        },
        "additional_files_sha256": {k: files[k] for k in prior["additional_files_sha256"]},
        "scorer_files_sha256": {k: files[k] for k in prior["scorer_files_sha256"]},
    }


def verify_timing_build(repo, private, lock):
    from scripts.graduation import g1_visibility_mount_runtime as mount

    qualification = timing_qualification(repo, lock["radial_timing"]["replay_release_sha256"])
    parent, prior = verify_build(private, TIMING_PARENT)
    require(
        prior["radial_plan_sha256"] == mount.PLAN_SHA
        and prior["radial_assembly"] == mount.spec_for(15)
        and lock == timing_manifest(prior, lock["runtime_files_sha256"], qualification),
        "wrong released radial time, geometry, source inventory or parent",
    )
    return parent, pinned(parent.parent / "preflight.json", TIMING_PARENT_PREFLIGHT)


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
