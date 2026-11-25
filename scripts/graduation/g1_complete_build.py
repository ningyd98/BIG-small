"""Freeze one byte-verified child of the native G1 controller, camera and scorer."""

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path

from scripts.graduation import g1_complete_trials as trials
from scripts.graduation.g1_clearance_mount import overlays
from scripts.graduation.g1_formal_runtime import check_tree
from scripts.graduation.perception_io import ROOT, pinned, sha, write

QUALIFICATION = trials.ROUNDS / "round-g1-cv-qualification-entry-20261125"
TARGET_PLAN = trials.ROUNDS / "round-g1-target-visibility-20261125" / "plan.json"
TARGET_SHA = "50eb1413e14876ce17de4f0b1c901af48f66c3ab745b47b76853541c99c8dbc8"


def replace_one(source, anchor, change):
    trials.require(source.count(anchor) == 1, "frozen native event anchor differs")
    return source.replace(anchor, change)


def color_archive_sources(repo, parent):
    """Record the actual color-reference evaluation instant for a later cold reader."""
    clock = "scripts/graduation/guarded_clock.py"
    scorer = "scripts/graduation/g1_dual_batch_score.py"
    anchor = (
        "        self.color, self.evidence = bootstrap_collection_tracker(handoff, self.geometry)"
    )
    record = """        self.report["color_init_event"] = {
            "frame_id": handoff.frame_id, "checksum_sha256": handoff.checksum_sha256,
            "role": "color.initial", "lease_id": self.original.identity.lease_id,
            "captured_at": handoff.captured_at.isoformat(),
            "evaluated_at": self.color.last_binding_evaluated_at.isoformat(),
            "call_start_utc": color_start.isoformat(),
            "call_end_utc": datetime.now(UTC).isoformat(),
        }"""
    clock_source = replace_one(
        (parent / clock).read_text(),
        anchor,
        "        color_start = datetime.now(UTC)\n" + anchor + "\n" + record,
    )
    before = 'tracker, _ = bootstrap_collection_tracker(fetch(roles["color_reference"]), geometry)'
    after = """from scripts.graduation.qualify_archive import archived_color
                first = next(r for r in audit
                             if r.get("schema_version") == "native.registered.grounding.v2")
                tracker = archived_color(
                    fetch(roles["color_reference"]), geometry, run["color_init_event"],
                    first["identity"]["lease_id"], first["lease_source"]["expires_at"])"""
    return {
        clock: clock_source.encode(),
        scorer: replace_one((parent / scorer).read_text(), before, after).encode(),
        "scripts/graduation/qualify_archive.py": (
            repo / QUALIFICATION / "qualify_archive.py"
        ).read_bytes(),
    }


def prepare(repo, *, target_vision=False):
    base = repo / trials.OLD / "builds" / trials.PARENT / "runtime-source"
    original = pinned(base / "runtime-build.json", trials.PARENT)
    check_tree(base, original["runtime_files_sha256"], inherited=True)
    additions = overlays(base)
    additions.update(color_archive_sources(repo, base))
    target_files = {}
    if target_vision:
        from scripts.graduation import g1_target_cv

        pinned(repo / TARGET_PLAN, TARGET_SHA)
        target_files = g1_target_cv.overlays(base)
        trials.require(
            not (set(target_files) & set(additions)), "overlapping target CV and mount sources"
        )
        additions.update(target_files)
    scripts = repo / "scripts/graduation"
    required = [
        "g1_complete_worker.py",
        "g1_complete_trials.py",
        "g1_complete_cv_clearance.py",
        "g1_complete_cv_calibrate.py",
        "g1_clearance_score.py",
    ]
    for name in required:
        trials.require((scripts / name).is_file(), "missing integration input " + name)
    for pattern in ("g1_complete_*.py", "g1_clearance_score*.py"):
        for source in sorted(scripts.glob(pattern)):
            additions[source.relative_to(repo).as_posix()] = source.read_bytes()
    motion = scripts / "g1_complete_cv_motion_profile.json"
    if (scripts / "g1_complete_cv_motion.py").exists():
        trials.require(motion.is_file(), "missing physical braking profile")
    for profile in sorted(scripts.glob("g1_complete_cv_*_profile.json")):
        additions[profile.relative_to(repo).as_posix()] = profile.read_bytes()
    effective = dict(original["runtime_files_sha256"])
    effective.update({k: hashlib.sha256(v).hexdigest() for k, v in additions.items()})
    detector = set(original["detector_files_sha256"])
    detector.update(target_files)
    detector.update(k for k in additions if "/g1_complete_cv_" in k or "/g1_clearance_mount" in k)
    scorers = set(original["scorer_files_sha256"])
    scorers.update(target_files)
    scorers.update(
        k for k in additions if "/g1_clearance_score" in k or k.endswith("/qualify_archive.py")
    )
    lock = dict(
        schema="g1.development.native-complete-build.v1",
        baseline=pinned(repo / trials.ROUND / "plan.json", trials.PLAN_SHA)["baseline_commit"],
        plan_sha256=trials.PLAN_SHA,
        parent_runtime_build_sha256=trials.PARENT,
        runtime_files_sha256=effective,
        detector_files_sha256={k: effective[k] for k in sorted(detector)},
        scorer_files_sha256={k: effective[k] for k in sorted(scorers)},
        overrides_sha256={k: effective[k] for k in sorted(additions)},
        target_plan_sha256=TARGET_SHA if target_vision else None,
    )
    builds = repo / trials.PRIVATE / "builds"
    builds.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=builds, prefix=".prepare-") as tmp:
        tree = Path(tmp) / "assembled" / "runtime-source"
        tree.mkdir(parents=True)
        write(tree / "runtime-build.json", lock)
        generation = sha(tree / "runtime-build.json")
        dest = builds / generation
        if not dest.exists():
            for name in effective:
                target = tree / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if name in additions:
                    target.write_bytes(additions[name])
                else:
                    shutil.copyfile(base / name, target)
            check_tree(tree, effective)
            tree.parent.rename(dest)
    pinned(dest / "runtime-source/runtime-build.json", generation)
    check_tree(dest / "runtime-source", effective, inherited=True)
    return generation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--target-vision", action="store_true")
    args = parser.parse_args()
    print(prepare(args.repo.resolve(), target_vision=args.target_vision))
