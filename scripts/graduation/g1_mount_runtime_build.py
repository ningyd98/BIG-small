"""Export the G1 development runtime from its exact Git base with one servo-family binding."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

BASE = "2ad38bc6214e9429b05488574b8b90e7b3184ad0"
VISION = "scripts/graduation/dynamic_vision.py"
ORIGINAL_VISION = "f706592a26b5d05f591c052d4d25104608110656e578b96759ad750f0b956064"
ADDITIONS = (
    "scripts/graduation/g1_mount_runtime_build.py",
    "scripts/graduation/g1_mount_trials.py",
)
EXPORT = (
    "src",
    "assets/robots/franka_panda",
    "configs",
    "pyproject.toml",
    "scripts/collect_native_calibration.py",
    "scripts/__init__.py",
    "scripts/phase7/frozen_vision.py",
    *(
        f"scripts/graduation/{name}.py"
        for name in (
            "dynamic_vision",
            "dynamic_physics",
            "dynamic_vision_score",
            "guarded_clock",
            "guarded_clock_score",
            "perception_capture",
            "perception_io",
            "perception_pixels",
            "proposal_camera",
            "proposal_closed_loop",
            "proposal_scoring",
            "proposal_translated",
            "proposal_translated_cases",
        )
    ),
)
LOCK = "runtime-build.json"


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def configure_vision(data):
    if sha_bytes(data) != ORIGINAL_VISION:
        raise ValueError("frozen dynamic_vision.py SHA256 changed")
    original = b"                marker_family_id=SIDE_PREPARE_ONLY_FAMILY,\n"
    if data.count(original) != 1:
        raise ValueError("single registered servo family binding required")
    return data.replace(
        original, b"                marker_family_id=self.registration.marker_family_id,\n"
    )


def build(repository, destination):
    """Check out original file bytes, leaving the source worktree untouched."""
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", BASE, *EXPORT], cwd=repository
    )
    destination.mkdir()
    original, effective = {}, {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for entry in tar:
            if entry.isdir():
                continue
            if (
                not entry.isfile()
                or Path(entry.name).is_absolute()
                or ".." in Path(entry.name).parts
            ):
                raise ValueError("unexpected non-regular Git archive entry")
            data = tar.extractfile(entry).read()
            original[entry.name] = sha_bytes(data)
            if entry.name == VISION:
                data = configure_vision(data)
            path = destination / entry.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            effective[entry.name] = sha_bytes(data)
    for name in ADDITIONS:
        data = (repository / name).read_bytes()
        if name in original:
            raise ValueError("development entry collides with the baseline")
        (destination / name).write_bytes(data)
        effective[name] = sha_bytes(data)
    changed = sorted(k for k, v in original.items() if v != effective[k])
    if changed != [VISION]:
        raise ValueError("one audited runtime binding change required")
    lock = dict(
        schema="g1.development.runtime-build.v1",
        baseline=BASE,
        source_changes=changed,
        additions=list(ADDITIONS),
        baseline_files_sha256=original,
        runtime_files_sha256=effective,
    )
    with (destination / LOCK).open("x") as stream:
        json.dump(lock, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return load_lock(destination)


def load_lock(root, expected=None):
    data = (root / LOCK).read_bytes()
    if expected is not None and sha_bytes(data) != expected:
        raise ValueError("runtime build SHA256 mismatch")
    lock = json.loads(data)
    if (
        lock["baseline"] != BASE
        or lock["source_changes"] != [VISION]
        or lock["baseline_files_sha256"].get(VISION) != ORIGINAL_VISION
        or set(lock["runtime_files_sha256"]) != set(lock["baseline_files_sha256"]) | set(ADDITIONS)
    ):
        raise ValueError("unexpected runtime baseline or file set")
    actual = {
        p.relative_to(root).as_posix(): sha_bytes(p.read_bytes())
        for p in root.rglob("*")
        if p.is_file() and p != root / LOCK and "__pycache__" not in p.parts
    }
    if actual != lock["runtime_files_sha256"]:
        raise ValueError("runtime file set or SHA256 mismatch")
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("public", type=Path)
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[2], args.runtime)
    with args.public.open("xb") as stream:
        stream.write((args.runtime / LOCK).read_bytes())


if __name__ == "__main__":
    main()
