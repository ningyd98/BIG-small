"""Read-only validation of the grid-04 supported-pin registration and frozen sources."""

import argparse
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / ".git").is_file())
ORIGINALS_SHA = "642b48f85b742cbc76994c069bfeaf8f02a6caa219c9802bd93ca2895b347490"
AMENDMENT_SHA = {
    "plan-amendment.md": "1369d77cad75166e28fb99fd6002b92f1e768cdc11f107cb744eda84ae3a12ef",
    "plan-amendment.json": "3895c885ff6ae5339bf7700db8b407ed7c5f60b93c6d3485a56e83e1564c1c4c",
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def canonical(value):
    return (
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n"
    ).encode()


def write(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside(base, member):
    path = (base / member).resolve(strict=True)
    require(path.is_relative_to(base.resolve()) and path.is_file(), f"foreign file: {member}")
    return path


def git(*args):
    return subprocess.check_output(("git", *args), cwd=ROOT)


def inputs(plan_path):
    require(plan_path.resolve() == HERE / "plan.json", "unregistered plan file")
    require(ROOT == Path.cwd().resolve(), "run from the registered worktree")
    for name, expected in AMENDMENT_SHA.items():
        require(sha(HERE / name) == expected, f"unregistered Astra amendment: {name}")
    amendment = read(HERE / "plan-amendment.json")
    for name, expected in amendment["parent_sha256"].items():
        require(sha(HERE / name) == expected, f"original plan bytes changed: {name}")
    raw = plan_path.read_bytes()
    correction = amendment["plan_value_override"]
    old = correction["require_old"].encode()
    new = correction["replace_with"].encode()
    require(
        len(old) == correction["old_length"]
        and raw.count(old) == correction["required_raw_occurrences_in_parent_json"],
        "wrong parent plan override",
    )
    effective = raw.replace(old, new)
    require(
        hashlib.sha256(effective).hexdigest()
        == correction["sha256_after_single_literal_replacement_in_memory"],
        "wrong effective plan",
    )
    plan = json.loads(raw)
    values = plan[correction["object"]]
    require(values[correction["key"]] == correction["require_old"], "wrong original manifest key")
    values[correction["key"]] = correction["replace_with"]
    require(
        plan == json.loads(effective) and plan["evidence_commit"] == amendment["evidence_commit"],
        "unregistered plan change",
    )
    require(
        git("rev-parse", f"{plan['evidence_commit']}:{plan['round_root']}/{correction['key']}")
        .decode()
        .strip()
        == correction["baseline_git_blob_oid"],
        "wrong corrected Git blob",
    )
    require(ROOT == Path(plan["worktree"]), "worktree differs from the registration")
    return plan, amendment


def runtime_root(plan, kind="native"):
    generation = plan["runtime"][f"{kind}_generation_and_manifest_sha256"]
    return ROOT / plan["roots"]["builds"] / generation / "runtime-source"


def source_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archived_frame(path):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    with gzip.open(path, "rb") as stream:
        return RGBDObservation.model_validate_json(stream.read())


def frozen_formal():
    directory = ROOT / "experiments/results/g1-formal-paired-20261124"
    manifest = inside(directory, "originals-manifest.json")
    require(sha(manifest) == ORIGINALS_SHA, "formal originals manifest changed")
    files = read(manifest)["files"]
    size = 0
    for member, entry in files.items():
        path = inside(directory, member)
        require(sha(path) == entry["sha256"], f"changed formal original: {member}")
        size += path.stat().st_size
    require((len(files), size) == (919, 487_931_885), "wrong formal inventory")
    return {"files": len(files), "bytes": size, "manifest_sha256": ORIGINALS_SHA}


def verify_sources(plan, amendment):
    base = plan["evidence_commit"]
    git("merge-base", "--is-ancestor", base, "HEAD")
    roots = {key: ROOT / value for key, value in plan["roots"].items()}
    old_case = roots["old"] / plan["roots"]["case_under_old"]
    verified = {}

    def pin(directory, member, expected):
        path = inside(directory, member)
        relative = path.relative_to(ROOT).as_posix()
        require(sha(path) == expected, f"SHA256 mismatch: {relative}")
        verified[relative] = expected
        return path

    def listed(directory, digests, size=None):
        if size is not None:
            require(len(digests) == size, f"source inventory count: {directory}")
        for member, expected in digests.items():
            pin(directory, member, expected)

    def from_git(member, expected=None):
        registered = hashlib.sha256(git("show", f"{base}:{member}")).hexdigest()
        require(expected in (None, registered), f"Git object differs from plan: {member}")
        return pin(ROOT, member, registered)

    def round_file(topic, name):
        return read(HERE.parent / f"round-g1-{topic}-20261126" / name)

    for member, expected in plan["round_files_sha256_relative_to_round_root"].items():
        from_git(f"{plan['round_root']}/{member}", expected)
    for member, expected in plan["runtime"]["git_optical_inputs"].items():
        from_git(member, expected)
    for key, digests in plan["raw_hashes_by_root"].items():
        listed(roots[key], digests)

    stop = round_file("grid04-2384-stop-space-separation", "plan.json")
    listed(ROOT, stop["source_sha256"], 18)
    registry = round_file("grid04-2384-stop-space-separation", "stop-space.public.json")
    native = read(roots["native"] / "result.json")
    normal = {row["tick"]: row for row in read(roots["native"] / "normal.json")}
    require(
        set(registry["pinned_stop_registry"]) == set(map(str, range(2376, 2385))),
        "missing registered stopping phase",
    )
    for tick, entry in registry["pinned_stop_registry"].items():
        require(
            entry == native["archives"][tick]
            and entry["phase_sha256"] == normal[int(tick)]["phase_sha256"],
            f"wrong stop phase {tick}",
        )
        pin(roots["native"], f"stop-{tick}.npz", entry["state_sha256"])
        pin(roots["native"], f"stop-{tick}.json", entry["contacts_sha256"])

    approach = round_file("grid04-approach-offset-transmission", "plan.json")
    require(ROOT / approach["original_raw"] == old_case, "approach names a foreign case")
    listed(old_case, approach["original_raw_sha256"], 5)
    listed(HERE.parent, approach["round_input_sha256"], 5)
    approach_record = round_file(
        "grid04-approach-offset-transmission", "approach-transmission.public.json"
    )
    require(ROOT / approach_record["private_output"] == roots["approach"], "wrong approach corpus")
    listed(roots["approach"], approach_record["raw_sha256"], 12)

    prebuild = round_file("grid04-live-carried-reference-prebuild", "plan.json")
    listed(ROOT, prebuild["inputs"], 7)
    prebuild_record = round_file(
        "grid04-live-carried-reference-prebuild", "live-prebuild.public.json"
    )
    require(ROOT / prebuild_record["private_output"] == roots["prebuilt"], "wrong prebuild corpus")
    listed(roots["prebuilt"], prebuild_record["raw_sha256"], 10)
    sessions = amendment["reader_correction"]["sessions"]
    require(
        [ROOT / row["directory"] for row in sessions]
        == [roots["old"], roots["prebuilt"] / "isolated-rgbd-01"],
        "wrong sealed sessions",
    )
    for row in sessions:
        directory = ROOT / row["directory"]
        seal = read(pin(directory, "seal.json", row["seal_sha256"]))
        members = seal["sealed_sha256"]
        receipt = read(directory / plan["roots"]["case_under_old"] / "sensor-receipt.json")
        expected = row["registration_sha256"]
        require(
            members["registration.json"] == expected == receipt["registration_sha256"],
            "misbound same-session registration",
        )
        listed(directory, members, row["sealed_members"])

    surface = round_file("grid04-2384-surface-attribution", "plan.json")
    listed(ROOT, surface["blind_inputs_sha256"], 16)
    listed(ROOT, surface["truth_after_optical_seal_sha256"], 2)
    home = roots["surface"] / "reference-projections"
    reference = read(home / "seal.json")
    listed(home, reference["members_sha256"], 2)
    receipts = round_file("grid04-2384-surface-attribution", "surface-attribution.public.json")
    for name, pair in receipts["independent_receipts_sha256"].items():
        require(len(pair) == 2 and pair[0] == pair[1], f"historical cold readers differ: {name}")
        for number, expected in enumerate(pair, start=1):
            pin(roots["surface"], f"{name}-reader-{number}.json", expected)
    require(
        reference["blind_reader_sha256"] == receipts["independent_receipts_sha256"]["blind"][0],
        "reference projection has wrong blind input",
    )

    midcourse = round_file("grid04-refit-midcourse-qualification", "plan.json")
    require(len(midcourse["hashes"]) == 21, "midcourse input set differs")
    for name, expected in midcourse["hashes"].items():
        group, member = name.split("/", 1)
        pin(ROOT / midcourse["roots"][group], member, expected)

    runtime = plan["runtime"]
    for kind, counts in (("native", (591, 20, 11)), ("optical", (608, 37, 11))):
        directory = runtime_root(plan, kind)
        manifest = read(
            pin(directory, "runtime-build.json", runtime[f"{kind}_generation_and_manifest_sha256"])
        )
        for name, count in zip(("runtime", "detector", "scorer"), counts, strict=True):
            listed(directory, manifest[f"{name}_files_sha256"], count)
    for member, expected in runtime["native_files_sha256"].items():
        pin(runtime_root(plan) / "src/cloud_edge_robot_arm/simulation/mujoco", member, expected)
    pin(
        runtime_root(plan),
        runtime["asset_relative"].removeprefix("runtime-source/"),
        runtime["asset_sha256"],
    )
    pin(
        runtime_root(plan, "optical"),
        runtime["optical_detector_relative"].removeprefix("runtime-source/"),
        runtime["optical_detector_sha256"],
    )

    calibration = read(roots["calibration"] / "manifest.json")
    require(
        len(calibration["frames"]) == 17 and len(calibration["maps"]) == 3,
        "calibration inventory differs",
    )
    for entry in calibration["frames"]:
        path = pin(roots["calibration"], entry["file"], entry["sha256"])
        frame = read(path)
        require(
            (frame["frame_id"], frame["checksum_sha256"]) == (entry["frame_id"], entry["checksum"]),
            f"calibration frame misbound: {path.name}",
        )
    for entry in calibration["maps"].values():
        pin(roots["calibration"], entry["depth_file"], entry["depth_sha256"])
    camera = plan["camera"]
    gl = {
        "renderer": camera["renderer"],
        "vendor": camera["vendor"],
        "version": camera["gl_version"],
    }
    require(
        calibration["renderer"] == read(old_case / "sensor-receipt.json")["renderer"] == gl,
        "archived camera renderer differs",
    )
    require(calibration["asset_sha256"] == runtime["asset_sha256"], "calibration asset differs")
    return {"sha256": verified, "formal": frozen_formal()}


def verify_imports(plan, verified):
    """Pin all loaded application modules before the first native operation."""
    runtime = runtime_root(plan)
    sources = {}
    for name, module in sorted(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if not file:
            continue
        path = Path(file).resolve()
        if name == "cloud_edge_robot_arm" or name.startswith("cloud_edge_robot_arm."):
            require(path.is_relative_to(runtime), f"wrong native import: {name} at {path}")
        elif name.startswith("scripts.") or (
            path.is_relative_to(HERE.parent) and path.suffix == ".py"
        ):
            require(path.is_relative_to(ROOT), f"foreign research import: {name}")
        else:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if path.parent == HERE:
            expected = sha(path)
        else:
            expected = verified.get(relative)
            if expected is None:
                expected = hashlib.sha256(
                    git("show", f"{plan['evidence_commit']}:{relative}")
                ).hexdigest()
        require(sha(path) == expected, f"unregistered imported bytes: {name}")
        sources[name] = {"file": relative, "sha256": expected}
    return sources


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    arguments = parser.parse_args()
    sources = verify_sources(*inputs(arguments.plan))
    print(
        canonical({"sources": len(sources["sha256"]), "formal": sources["formal"]}).decode(), end=""
    )
