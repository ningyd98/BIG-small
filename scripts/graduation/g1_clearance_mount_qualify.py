"""Build a hash-verified copy of the new assembly for independent diagnostic fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.graduation import g1_clearance_mount as mount

PLAN = (
    "artifacts/research/process/20261004-ced-development/astra-rounds/"
    "round-g1-complete-cv-repair-20261125/plan.json"
)
PLAN_SHA = "4f84f847bc86f68d474d4f81feb0083f6f9e2e9ee93d49e4d5c5509600cc824b"
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/results/g1-visibility-pose-repair-20261124"
PARENT = BASE / "builds" / mount.PARENT_GENERATION / "runtime-source"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(output):
    plan_path = ROOT / PLAN
    plan = json.loads(plan_path.read_bytes())
    if (
        sha(plan_path.read_bytes()) != PLAN_SHA
        or sha(plan_path.with_suffix(".md").read_bytes()) != plan["plan_md_sha256"]
        or any(sha((ROOT / f).read_bytes()) != h for f, h in plan["input_sha256"].items())
    ):
        raise ValueError("changed diagnostic plan input")
    changes = mount.overlays(PARENT)
    for name in sorted((ROOT / "scripts/graduation").glob("g1_clearance_mount_*.py")):
        changes[name.relative_to(ROOT).as_posix()] = name.read_bytes()
    files = json.loads((PARENT / "runtime-build.json").read_bytes())["runtime_files_sha256"]
    output.mkdir(parents=True, exist_ok=False)
    new = {}
    for name in sorted(files.keys() | changes.keys()):
        if name in files:
            data = (PARENT / name).read_bytes()
            if sha(data) != files[name]:
                raise ValueError("changed native input: " + name)
        if name in changes:
            data = changes[name]
        dst = output / name
        dst.parent.mkdir(exist_ok=True, parents=True)
        dst.write_bytes(data)
        new[name] = sha(dst.read_bytes())
    lock = dict(
        schema="g1.physical-end-wing-diagnostic.v1",
        plan_sha256=PLAN_SHA,
        native_parent=mount.PARENT_GENERATION,
        role="independent diagnostic fixtures",
        runtime_files_sha256=new,
    )
    manifest = output / "mount-diagnostic-generation.json"
    manifest.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return sha(manifest.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(prepare(parser.parse_args().output))


if __name__ == "__main__":
    main()
