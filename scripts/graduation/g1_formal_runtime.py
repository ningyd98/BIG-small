"""Freeze the qualified G1 source generation with per-assignment runtime identities."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from scripts.graduation.perception_io import pinned, read, sha, write

PLAN_SHA = "8856a834e6191b74c323f89feb0e4a38c50b94e0a8850a4a88181bd53176e40a"
SCENE_PLAN_SHA = "9d893f99f756b91a674840afef381f86f17cf91224f5e1d8a7776af3a3377534"
SCENE_ROUND = "round-g1-formal-scene-binding-20261124"
_scene = ContextVar("g1_registered_scene", default=None)
RELEASE = "g1-formal-paired-20261124"
SCOPE = "FORMAL_G1_FIXED_PLACEMENT_PAIRED"
PREFIX = "scripts/graduation/"
RUNNER = PREFIX + "g1_formal_trials.py"
SCORER = PREFIX + "g1_dual_batch_score.py"
PIXELS = PREFIX + "g1_dual_pixel_readback.py"
OBSERVER = PREFIX + "g1_dual_observer.py"
ADDITIONS = (
    RUNNER,
    PREFIX + "g1_formal_runtime.py",
    PREFIX + "g1_formal_score.py",
    SCORER,
    PIXELS,
)
VISION = PREFIX + "dynamic_vision.py"
CAPTURE = PREFIX + "g1_mount_trials.py"
RESET = PREFIX + "proposal_closed_loop.py"
INPUT_SHA = {
    OBSERVER: "9a6339400d12fb5aa261e0a210c39a149b3e5cac015c99d5be002cdac1a2f790",
    VISION: "2d216e9e0a3e6de71abed5455accf5c6a03de719a9831da8d2d65b8a58fa2d67",
    CAPTURE: "dfea047deea76b57046cee133c761f592b027e70ed48a77bf81d9049c85ded9d",
    RESET: "bcaffc6c6349b8b9650dabd33e26c7145ada96794119baa506317f63796739d3",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def bind_scene(assigned_scene):
    """Bind one previously verified allocation for the lifetime of an online or blind reader."""
    require(
        isinstance(assigned_scene, str)
        and assigned_scene
        and assigned_scene.strip() == assigned_scene,
        "empty or invalid assigned scene",
    )
    token = _scene.set(assigned_scene)
    try:
        yield
    finally:
        _scene.reset(token)


def expected_scene(historical):
    return _scene.get() or historical


def checked_geometry(arm, historical, current, lock):
    if arm == "original":
        require(current == historical, "original marker geometry changed")
        return current
    old = historical["development_dual"]
    sources = old["development_sources_sha256"]
    require(
        all(lock["baseline_files_sha256"][k] == h for k, h in sources.items()),
        "foreign fourth-generation geometry source",
    )
    changed = {**sources, OBSERVER: lock["runtime_files_sha256"][OBSERVER]}
    require(
        all(lock["runtime_files_sha256"][k] == h for k, h in changed.items()),
        "unexpected qualified observer dependency change",
    )
    generation = digest(json.dumps(changed, sort_keys=True, separators=(",", ":")).encode())
    registered = {
        **historical,
        "development_dual": {
            **old,
            "development_sources_sha256": changed,
            "development_source_generation": generation,
        },
    }
    require(current == registered, "dual geometry differs outside its observer byte generation")
    return current


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo)


def adapt_source(name, data):
    """Only identity, claim chronology and corresponding readback are changed in the new tree."""
    require(digest(data) == INPUT_SHA[name], "unexpected identity-adapter input source")
    source = data.decode()
    if name == OBSERVER:
        edits = [
            (
                "from scripts.graduation import g1_dual_asset as asset\n",
                "from scripts.graduation import g1_dual_asset as asset\n"
                "from scripts.graduation.g1_formal_runtime import expected_scene\n",
            ),
            (
                "if frame.scene_id != asset.SCENE_ID or not frame.episode_id:",
                "if frame.scene_id != expected_scene(asset.SCENE_ID) or not frame.episode_id:",
            ),
        ]
    elif name == VISION:
        edits = [
            (
                'worker_id="graduation-r593-component",',
                'worker_id=allocation["case"]["release"] + "-worker",',
            ),
            ('batch_id="",', 'batch_id=case["release"],'),
            (
                'scenario_id="S01_NORMAL_STATIC",\n'
                '            control_mode="DEVELOPMENT_COMPONENTS",',
                'scenario_id=case["scene_id"],\n            control_mode="FORMAL_G1_PAIRED",',
            ),
            (
                'manifest_id="graduation-r593-dev",',
                'manifest_id=case["release"],\n'
                "            manifest={k: case[k] for k in "
                '("visual_id", "scene_id", "task_id", "plan_id")},',
            ),
            (
                'reason_code="development",\n            worker_id="",',
                'reason_code="g1_formal_paired",\n            worker_id="",',
            ),
            (
                'reason_code="development",\n            worker_id=self.worker.worker_id,',
                'reason_code="g1_formal_paired",\n            worker_id=self.worker.worker_id,',
            ),
            (
                '"control": "development worker, registered conditions and research Shield; "\n'
                '            "no native or formal execution authority",',
                '"control": "G1 paired MuJoCo worker with registered conditions and Shield",\n'
                '            "formal_identity": {k: self.case[k] for k in '
                '("visual_id", "scene_id", "task_id", "plan_id")},',
            ),
            ('"task_id": "graduation-r593-task",', '"task_id": self.case["task_id"],'),
            ('"plan_id": "graduation-r593-plan",', '"plan_id": self.case["plan_id"],'),
            (
                'scenario_id="S01_NORMAL_STATIC",\n                seed=self.case',
                'scenario_id=self.case["scene_id"],\n                seed=self.case',
            ),
            (
                '"samples": [dataclasses.asdict(s) for s in snapshots],',
                '"scene": first.scene_id,\n'
                '                "samples": [dataclasses.asdict(s) for s in snapshots],',
            ),
        ]
    elif name == RESET:
        edits = [
            (
                'request["scenario_id"] != "S01_NORMAL_STATIC"',
                'request["scenario_id"] != case["scene_id"]',
            )
        ]
    else:
        edits = [
            (
                "episode_factory=TranslatedEpisode):",
                "episode_factory=TranslatedEpisode, before_start=None):",
            ),
            (
                "    directory.mkdir()  # Atomic reservation",
                "    claim_sha256 = before_start()\n    directory.mkdir()  # Atomic reservation",
            ),
            (
                '            case=case_id,\n            slot=row["slot"],',
                "            case=case_id,\n            claim_sha256=claim_sha256,\n"
                '            slot=row["slot"],',
            ),
            (
                '        or (job["backend"], job["control_mode"]) != '
                '("MUJOCO", "DEVELOPMENT_COMPONENTS")',
                '        or (job["backend"], job["control_mode"]) != ("MUJOCO", '
                '"FORMAL_G1_PAIRED")\n'
                '        or job["scenario_id"] != row["scene_id"]\n'
                '        or (job["manifest_id"], job["batch_id"]) != '
                '(alloc["case"]["release"],) * 2\n'
                '        or json.loads(job["manifest_json"]) != {k: alloc["case"][k] for k in '
                '("visual_id", "scene_id", "task_id", "plan_id")}',
            ),
            (
                '        capture_sha256=sha(directory / "acquisition-seal.json"),',
                '        claim_sha256=read(directory / "started.json")["claim_sha256"],\n'
                '        capture_sha256=sha(directory / "acquisition-seal.json"),',
            ),
        ]
        if "import json\n" not in source:
            edits.append(("import argparse\n", "import argparse\nimport json\n"))
    for old, new in edits:
        require(source.count(old) == 1, f"non-unique identity binding in {name}: {old}")
        source = source.replace(old, new)
    return source.encode()


def layout(plan_file, out):
    plan = pinned(plan_file, PLAN_SHA)
    repo = next(p for p in plan_file.parents if (p / ".git").exists())
    require(
        plan_file.parent.name == plan["round"]
        and plan["release"] == RELEASE
        and sha(plan_file.with_suffix(".md")) == plan["plan_md_sha256"]
        and out == repo / plan["formal_output"] == out.resolve(),
        "foreign plan or private output root",
    )
    git(repo, "merge-base", "--is-ancestor", plan["baseline"], "HEAD")
    return repo, plan


def verify_inputs(repo, plan):
    rounds = repo / "artifacts/research/process/20261004-ced-development/astra-rounds"
    supplemental = pinned(rounds / SCENE_ROUND / "plan.json", SCENE_PLAN_SHA)
    require(
        supplemental["parent_plan_sha256"] == PLAN_SHA
        and sha(rounds / SCENE_ROUND / "plan.md") == supplemental["plan_md_sha256"],
        "foreign supplemental scene-binding plan",
    )
    for name, expected in plan["input_sha256"].items():
        actual = (
            digest(git(repo, "show", plan["baseline"] + ":" + name))
            if name in (SCORER, PIXELS)
            else sha(repo / name)
        )
        require(actual == expected, "changed Astra input: " + name)


def check_tree(tree, files, *, inherited=False):
    found = {}
    for path in tree.rglob("*"):
        if inherited and "__pycache__" in path.parts:
            continue
        require(not path.is_symlink(), "symlink in frozen source: " + str(path))
        if path.is_file() and path != tree / "runtime-build.json":
            found[path.relative_to(tree).as_posix()] = sha(path)
    require(found == files, "unexpected, missing or changed frozen source file")


def parent_inputs(repo, plan):
    private = (repo / plan["private_parent_source"]).resolve()
    tree = (repo / plan["runtime_root"]).resolve()
    lock = pinned(tree / "runtime-build.json", plan["runtime_build_sha256"])
    files = lock["runtime_files_sha256"]
    require(
        tree == private / "runtime-source"
        and lock["development_assembly"] == "v2"
        and len(files) == plan["runtime_files_verified_at_planning"] == 553,
        "wrong fourth generation",
    )
    check_tree(tree, files, inherited=True)
    for family, name in plan["source_inventory_paths"].items():
        original = pinned(repo / name, plan["native_catalogues"][family]["archived_json_sha256"])
        require(
            len(original) == plan["native_catalogues"][family]["count"]
            and all(files.get(k) == h for k, h in original.items()),
            "foreign arm inventory",
        )
    return tree, files


def verify_lock(out, expected=None):
    tree = out / "runtime-source"
    path = tree / "runtime-build.json"
    lock = pinned(path, expected) if expected else read(path)
    require(lock["plan_sha256"] == PLAN_SHA and lock["release"] == RELEASE, "foreign formal build")
    check_tree(tree, lock["runtime_files_sha256"])
    return lock


def derived_build(repo, plan, parent, prior):
    additions = {name: (repo / name).read_bytes() for name in ADDITIONS}
    require(set(additions).isdisjoint(prior), "formal entry shadows a fourth-generation source")
    changes = {name: adapt_source(name, (parent / name).read_bytes()) for name in INPUT_SHA}
    effective = {**prior, **{name: digest(data) for name, data in (additions | changes).items()}}
    lock = dict(
        schema="g1.formal-paired.runtime.v1",
        plan_sha256=PLAN_SHA,
        scene_binding_plan_sha256=SCENE_PLAN_SHA,
        release=RELEASE,
        parent_runtime_build_sha256=plan["runtime_build_sha256"],
        baseline_files_sha256=prior,
        runtime_files_sha256=effective,
        source_changes=sorted(changes),
        additions=sorted(additions),
        scoring_sources_sha256={
            name: effective[name] for name in effective if name.startswith(PREFIX)
        },
        external_entries_sha256={name: digest(data) for name, data in additions.items()},
    )
    return lock, changes | additions


def prepare(repo, plan, out):
    verify_inputs(repo, plan)
    parent, prior = parent_inputs(repo, plan)
    lock, replaced = derived_build(repo, plan, parent, prior)
    if out.exists():
        require(
            verify_lock(out) == lock and not any((out / "claims").iterdir()),
            "existing output is not the prepared generation",
        )
        return lock
    out.mkdir(mode=0o700)
    (out / "claims").mkdir(mode=0o700)
    tree = out / "runtime-source"
    tree.mkdir()
    for name in lock["runtime_files_sha256"]:
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            if name in replaced:
                stream.write(replaced[name])
            else:
                stream.write((parent / name).read_bytes())
    write(tree / "runtime-build.json", lock)
    return verify_lock(out)


def enter_runtime(out, args):
    tree = out / "runtime-source"
    if Path(__file__).resolve().parents[2] == tree and Path.cwd() == tree:
        return
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        PYTHONPATH=os.pathsep.join((str(tree), str(tree / "src"))),
    )
    os.chdir(tree)
    os.execve(
        sys.executable,
        [sys.executable, "-B", "-m", "scripts.graduation.g1_formal_trials", *args],
        env,
    )
