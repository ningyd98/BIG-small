"""Freeze one separately registered development-only active-checks retest."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from cloud_edge_robot_arm.research.native_calibration_collection import (
    _REGISTERED_TEACHER_CONFIG,
    ROOT,
    canonical,
    load_json,
    regular,
    save_exclusive,
)
from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import (
    _WHOLE_ACTION_ACTIVE_CHECKS,
    DIAGNOSTIC_SEED,
    WHOLE_ACTION_SCOPE,
    WHOLE_ACTION_SOURCE_SUFFIX,
    _diagnostic_recipe,
)

HERE = Path(__file__).resolve().parent
RETEST_PLAN_SHA = "e78c7066807e3bbc3fdbf969c4904b916a822f58d15245dbfbd7320fbef3da0f"
REPAIR_PLAN_SHA = "94f40ebc35bac2e148c418919235eab2eeb9c303066d5057b03e4c146d4ebc56"
PLAN_PINS = {
    HERE.name: RETEST_PLAN_SHA,
    "round-p0-teacher-active-check-repair-20261121": REPAIR_PLAN_SHA,
}
PARENT_PROTOCOL_SHA = "cd35a3bcee16751f48c041da79831ea06ef947f4f7719788cc12285f69783cd5"


def file_sha(path: Path) -> str:
    with regular(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value: bool, error: str) -> None:
    if not value:
        raise ValueError(error)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    entry = _WHOLE_ACTION_ACTIVE_CHECKS
    source = ROOT / entry.source_suffix
    owner = source.parent
    prior = (ROOT / WHOLE_ACTION_SOURCE_SUFFIX).parent
    parent_freeze = prior / "source-freeze.json"
    parent_protocol = prior / "release/protocol.json"
    require(file_sha(parent_freeze) == entry.parent_freeze_sha256, "parent freeze SHA changed")
    require(file_sha(parent_protocol) == PARENT_PROTOCOL_SHA, "parent registration SHA changed")
    parent = load_json(parent_freeze)
    protected = dict(parent["protected_inputs_sha256"])
    parent_paths = (
        "source-freeze.json",
        "process-begin.json",
        "process-end.json",
        "worker-begin.json",
        "release/protocol.json",
        "release/diagnostic-claim.json",
        "release/run/runtime.db",
        "release/run/collection-result.json",
        "release/run/originals/inventory.json",
        "release/run/imported-source-manifest.json",
        "collect.exit",
        "collect.stdout",
        "collect.stderr",
        "run_frozen_whole_action.py",
        "launch_whole_action_once.sh",
    )
    for relative in parent_paths:
        path = prior / relative
        protected[str(path.relative_to(ROOT))] = file_sha(path)
    for name, expected in PLAN_PINS.items():
        path = HERE.parent / name / "plan.json"
        require(file_sha(path) == expected, f"plan changed: {path.name}")
        protected[str(path.relative_to(ROOT))] = expected
    for relative, expected in protected.items():
        require(file_sha(ROOT / relative) == expected, f"protected history changed: {relative}")
    for script, key in (
        ("run_frozen_whole_action.py", "runner_sha256"),
        ("launch_whole_action_once.sh", "launcher_sha256"),
    ):
        require(
            file_sha(prior / script) == parent[key],
            f"original launcher component changed: {script}",
        )

    previous = load_json(parent_protocol)["recipe"]
    recipe = _diagnostic_recipe(whole_action=True, whole_action_release=entry)
    for key in recipe.keys() | previous.keys():
        if key not in {
            "assignments",
            "settings",
            "source_generation",
            "source_hashes",
            "region_policy",
            "release_reference",
        }:
            require(canonical(recipe[key]) == canonical(previous[key]), f"recipe changed: {key}")
    (old_assignment,) = previous["assignments"]
    (new_assignment,) = recipe["assignments"]
    require(
        {k: v for k, v in new_assignment.items() if k not in {"assignment_id", "ancestors"}}
        == {k: v for k, v in old_assignment.items() if k not in {"assignment_id", "ancestors"}}
        and new_assignment["seed"] == DIAGNOSTIC_SEED,
        "fixed assignment seed, pool or status changed",
    )
    require(
        {k: v for k, v in recipe["settings"].items() if k != "released_assignment"}
        == {k: v for k, v in previous["settings"].items() if k != "released_assignment"},
        "physical or capture settings changed",
    )
    files = dict(recipe["source_hashes"])
    files[_REGISTERED_TEACHER_CONFIG] = file_sha(ROOT / _REGISTERED_TEACHER_CONFIG)
    for name in ("region_policy", "release_reference"):
        new, old = recipe[name], previous[name]
        require(
            {k: v for k, v in new.items() if k != "source_generation"}
            == {k: v for k, v in old.items() if k != "source_generation"}
            and new["source_generation"] == recipe["source_generation"]
            and old["source_generation"] == previous["source_generation"],
            f"non-source fields or generation binding changed: {name}",
        )
    parent_files = parent["source_files_sha256"]
    require(set(files) == set(parent_files), "source membership changed")
    changed_sources = {name for name in files if files[name] != parent_files[name]}
    expected_changes = {
        "src/cloud_edge_robot_arm/research/native_checkpoint_diagnostic.py",
        "src/cloud_edge_robot_arm/research/native_collection_application.py",
        "src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py",
    }
    require(changed_sources == expected_changes, f"unexpected source delta: {changed_sources}")
    if args.check_only:
        print(f"Verified {len(files)} source paths and {len(protected)} protected inputs")
        return
    owner.mkdir(mode=0o700)
    source.mkdir()
    for relative, expected in sorted(files.items()):
        raw = regular(ROOT / relative).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, f"source changed: {relative}")
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as out:
            out.write(raw)
        require(file_sha(target) == expected, f"copy changed: {relative}")
        target.chmod(0o444)
    for directory in sorted(source.rglob("*"), reverse=True):
        if directory.is_dir():
            directory.chmod(0o555)
    source.chmod(0o555)
    for name in ("run_frozen_whole_action.py", "launch_whole_action_once.sh"):
        with (owner / name).open("xb") as out:
            out.write(regular(prior / name).read_bytes())
        require(file_sha(owner / name) == file_sha(prior / name), f"runner copy changed: {name}")
    save_exclusive(
        owner / "source-freeze.json",
        dict(
            scope=WHOLE_ACTION_SCOPE,
            actual_source_frozen_without_worktree_mutation=True,
            operational_worktree=str(ROOT),
            working_tree_base_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            astra_plan_sha256=REPAIR_PLAN_SHA,
            retest_plan_sha256=RETEST_PLAN_SHA,
            source_path=str(source),
            source_files_sha256=files,
            source_generation=recipe["source_generation"],
            protected_inputs_sha256=protected,
            parent_source_freeze_sha256=entry.parent_freeze_sha256,
            parent_protocol_file_sha256=PARENT_PROTOCOL_SHA,
            diagnostic_seed=DIAGNOSTIC_SEED,
            diagnostic_seed_aligned_to_whole_action_reference=True,
            preserved_reference_recipe_settings=True,
            runner_sha256=file_sha(owner / "run_frozen_whole_action.py"),
            launcher_sha256=file_sha(owner / "launch_whole_action_once.sh"),
        ),
    )


if __name__ == "__main__":
    main()
