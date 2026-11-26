"""Run the single registered CPU prefix for grid-04 and seal its attempt."""

import argparse
import os
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import distribution
from pathlib import Path

from pin_evidence import (
    HERE,
    ROOT,
    git,
    inputs,
    read,
    require,
    runtime_root,
    sha,
    verify_imports,
    verify_sources,
    write,
)

PREFIX_LOGS = ("endpoints", "phases", "commands", "actuator")
COUNTERS = (
    "resets",
    "physics_steps",
    "endpoints",
    "command_reissues",
    "render_or_capture_attempts",
    "suppressed_sensor_updates",
    "archived_approach_endpoints_checked",
    "archived_applied_controls_checked",
)


def cpu_environment(plan):
    require(
        os.environ.get("MUJOCO_GL") not in ("egl", "glfw", "osmesa")
        and not os.environ.get("PYOPENGL_PLATFORM"),
        "renderer configured in CPU-only process",
    )
    paths = os.environ.get("PYTHONPATH", "").split(os.pathsep)
    require(
        [Path(path).resolve() for path in paths] == [ROOT, runtime_root(plan) / "src"],
        "PYTHONPATH must contain only the worktree and the sealed native src",
    )


def stamp():
    return datetime.now(UTC).isoformat()


def package_sources():
    startup_json_sha = "da0f6fb38f2a79bdf6481900b2a01a0c0aae1d144a58e77e0111fa8e7dacf9c2"
    amendment_sha = {
        "startup-amendment.md": "13d387f8b5e369b2b9da1ff4808d86c0faccae2e684974de63f3e72757194ac3",
        "startup-amendment.json": startup_json_sha,
    }
    for name, expected in amendment_sha.items():
        require(sha(HERE / name) == expected, f"unknown startup amendment: {name}")
    startup = read(HERE / "startup-amendment.json")
    for name, expected in startup["parent_files_sha256"].items():
        require(sha(HERE / name) == expected, f"changed startup parent: {name}")
    packages = {}
    for entry in startup["distributions"]:
        package = distribution(entry["name"])
        metadata = package.locate_file(entry["metadata"]).resolve()
        require(
            package.version == entry["version"] and sha(metadata) == entry["sha256"],
            f"distribution metadata changed: {entry['name']}",
        )
        module = import_module(entry["module"])
        origin = Path(module.__file__).resolve()
        require(
            origin.is_relative_to(metadata.parent.parent)
            and module.__version__ == entry.get("reported_module_version", package.version),
            f"wrong loaded package origin or version: {entry['module']}",
        )
        record = {
            "distribution": entry["name"],
            "distribution_version": package.version,
            "metadata": str(metadata),
            "metadata_sha256": entry["sha256"],
            "module": str(origin),
            "module_sha256": sha(origin),
            "module_version": module.__version__,
        }
        if "native_extension" in entry:
            extension = package.locate_file(entry["native_extension"]).resolve()
            require(extension.parent == origin.parent, "wrong OpenCV native extension")
            record["native_extension"] = str(extension)
            record["native_extension_sha256"] = sha(extension)
        packages[entry["module"]] = record
    return packages, amendment_sha


def prepare_prefix(plan, amendment):
    cpu_environment(plan)
    provenance = verify_sources(plan, amendment)

    import mujoco
    import numpy
    import pin_prefix

    tools = pin_prefix.prepare(plan)
    expected = pin_prefix.validate_prefix(plan, tools)
    require(
        mujoco.__version__ == plan["camera"]["mujoco"] and numpy.__version__ == "2.5.3",
        "registered Python numeric environment changed",
    )
    packages, startup = package_sources()
    imports = verify_imports(plan, provenance["sha256"])
    driver_file = Path("/proc/driver/nvidia/version")
    registry = {
        "plan_sha256": sha(HERE / "plan.json"),
        "amendment_sha256": sha(HERE / "plan-amendment.json"),
        "startup_amendment_sha256": startup,
        "evidence_commit": plan["evidence_commit"],
        "development_head": git("rev-parse", "HEAD").decode().strip(),
        "python": {
            "path": sys.executable,
            "version": sys.version,
            "binary_sha256": sha(Path(sys.executable)),
        },
        "packages": packages,
        "driver_release": driver_file.read_text().splitlines()[0] if driver_file.exists() else None,
        "loaded_repository_modules": imports,
        "round_programs_sha256": {path.name: sha(path) for path in sorted(HERE.glob("*.py"))},
        "checked_sources": provenance,
        "capture_gate": amendment["rng_first_failure"]["capture_gate"],
        "counts_at_registration": dict.fromkeys(COUNTERS, 0),
    }
    return pin_prefix, tools, expected, registry


def prefix(plan, amendment):
    pin_prefix, tools, expected, registry = prepare_prefix(plan, amendment)
    output = ROOT / plan["private_output"]
    output.mkdir(exist_ok=False)
    write(output / "registration.json", registry)
    attempt = output / "prefix"
    attempt.mkdir()
    write(
        attempt / "attempt.json",
        {
            "started_at_utc": stamp(),
            "registration_sha256": sha(output / "registration.json"),
            "limit_resets": plan["budgets_max_including_failed_attempts"]["prefix_resets"],
            "limit_mj_steps": plan["budgets_max_including_failed_attempts"]["prefix_mj_steps"],
            "source_episode": plan["prefix"]["old_episode"],
        },
    )
    counts = dict.fromkeys(COUNTERS, 0)
    failure = None
    result = {}
    try:
        with ExitStack() as stack:
            journals = {
                name: stack.enter_context((attempt / f"{name}.jsonl").open("xb"))
                for name in PREFIX_LOGS
            }
            result = pin_prefix.replay(plan, tools, expected, attempt, counts, journals)
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "detail": str(exc), "counts": counts}
        write(attempt / "first-failure.json", failure)
        raise
    finally:
        result.update(
            {
                "finished_at_utc": stamp(),
                "counts": counts,
                "status": "FAILED" if failure else "ARCHIVED_PREFIX_EXACT",
                "sha256": {
                    path.name: sha(path) for path in sorted(attempt.iterdir()) if path.is_file()
                },
            }
        )
        write(attempt / "receipt.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "prefix"))
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan, amendment = inputs(args.plan)
    if args.mode == "preflight":
        _, _, _, provenance = prepare_prefix(plan, amendment)
        result = {
            "packages": provenance["packages"],
            "counts": provenance["counts_at_registration"],
        }
    else:
        result = prefix(plan, amendment)
    print(result)
