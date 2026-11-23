"""Build and exercise an offline Harness wheel in a fresh Python environment."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="a new private directory")
    args = parser.parse_args()
    checkout = args.source_checkout.resolve()
    wheelhouse = args.wheelhouse.resolve(strict=True)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("home", "logs", "source", "dist"):
        (root / directory).mkdir()
    env = {
        "PATH": os.defpath,
        "HOME": str(root / "home"),
        "LANG": "C.UTF-8",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_FIND_LINKS": wheelhouse.as_uri(),
        "SOURCE_DATE_EPOCH": "315532800",
    }
    receipts = []

    def run(name, command, *, expected=0):
        start = time.monotonic()
        proc = subprocess.run(command, cwd=root, env=env, capture_output=True, check=False)
        (root / "logs" / f"{name}.out").write_bytes(proc.stdout)
        (root / "logs" / f"{name}.err").write_bytes(proc.stderr)
        receipts.append(
            {
                "command": name,
                "exit_code": proc.returncode,
                "expected": expected,
                "wall_seconds": round(time.monotonic() - start, 3),
                "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
            }
        )
        if proc.returncode != expected:
            raise RuntimeError(
                f"{name}: exit {proc.returncode}, expected {expected}; see {root}/logs"
            )
        return proc.stdout.decode()

    revision = run(
        "revision", ["git", "-C", checkout, "rev-parse", "--verify", f"{args.revision}^{{commit}}"]
    ).strip()
    archive = root / "package-sources.tar"
    run(
        "archive",
        [
            "git",
            "-C",
            checkout,
            "archive",
            "-o",
            archive,
            revision,
            "--",
            "README.md",
            "src",
            "pyproject.toml",
        ],
    )
    with tarfile.open(archive) as snapshot:
        snapshot.extractall(root / "source", filter="data")
    python = root / "venv" / "bin" / "python"
    cli = python.with_name("bigsmall-harness")
    run("venv", [sys.executable, "-m", "venv", python.parents[1]])
    run("wheel", [python, "-m", "pip", "wheel", "--no-deps", "-w", root / "dist", root / "source"])
    (wheel,) = (root / "dist").glob("*.whl")
    run("install", [python, "-m", "pip", "install", "--report", root / "install.json", wheel])
    run("pip-check", [python, "-m", "pip", "check"])
    location = run(
        "package-location",
        [python, "-I", "-c", "import cloud_edge_robot_arm as app;print(app.__file__)"],
    ).strip()
    if not Path(location).is_relative_to(python.parents[1]):
        raise ValueError("package was imported outside the fresh environment")

    run("cli-help", [cli, "--help"])
    version = run("cli-version", [cli, "--version"]).strip()
    validation = json.loads(run("validate", [cli, "validate"]))
    doctor = json.loads(run("doctor", [cli, "doctor"]))
    source = json.loads(run("doctor-source", [cli, "doctor", "--source-checkout", checkout]))
    selected_files = source["source"]["files"]
    for relative, digest in selected_files.items():
        blob = subprocess.check_output(
            ["git", "-C", checkout, "show", f"{revision}:{relative}"], cwd=root, env=env
        )
        if hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError(f"checkout input differs from wheel source revision: {relative}")
    episode = root / "episode"
    prepare_cmd = [cli, "prepare", "--source-checkout", checkout, "--output", episode]
    prepare = json.loads(run("prepare", prepare_cmd))
    evidence = json.loads(run("evidence", [cli, "evidence", episode]))
    duplicate = json.loads(run("duplicate", prepare_cmd, expected=2))
    cold = root / "tampered-episode-copy"
    shutil.copytree(episode, cold)
    with (cold / "scene-assignment.json").open("ab") as stream:
        stream.write(b" ")
    tamper = json.loads(run("tamper", [cli, "evidence", cold], expected=2))
    reread = json.loads(run("reread-original", [cli, "evidence", episode]))
    result = json.loads((episode / "result.json").read_text())
    if not (
        validation["status"] == "VALIDATED"
        and doctor["status"] == "OFFLINE_READY"
        and source["status"] == "OFFLINE_READY"
        and prepare["status"] == "PREPARED"
        and evidence == reread
        and reread["episode"]["status"] == result["status"] == "PREPARED"
        and result["model_calls"] == result["executed_actions"] == result["physics_steps"] == 0
        and result["physical_success"] is None
        and "already exists" in duplicate["error"]
        and "differs from manifest" in tamper["error"]
    ):
        raise ValueError("unexpected Harness result; inspect preserved logs")

    installed = json.loads((root / "install.json").read_text())["install"]
    packages = [
        {
            "name": row["metadata"]["name"],
            "version": row["metadata"]["version"],
            "sha256": row["download_info"]["archive_info"]["hashes"]["sha256"],
        }
        for row in installed
    ]
    summary = {
        "schema": "graduation.offline-install.v1",
        "source_revision": revision,
        "wheel": {
            "name": wheel.name,
            "bytes": wheel.stat().st_size,
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        },
        "clean_venv": True,
        "system_site_packages": False,
        "network_index": False,
        "package_path_in_venv": str(Path(location).relative_to(python.parents[1])),
        "python": sys.version.split()[0],
        "version": version,
        "installed_packages": packages,
        "checkout_revision": source["source"]["git_revision"],
        "selected_inputs_at_wheel_revision": selected_files,
        "evidence_manifest_sha256": evidence["manifest_sha256"],
        "evidence_files": evidence["file_count"],
        "stage": result["status"],
        "model_calls": result["model_calls"],
        "executed_actions": result["executed_actions"],
        "physical_success": result["physical_success"],
        "duplicate": duplicate["error"],
        "physics_steps": result["physics_steps"],
        "tampered_copy": tamper["error"],
        "original_verified_after_controls": reread == evidence,
        "checks": receipts,
    }
    (root / "installation.public.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("wheel", "stage", "evidence_files")}))


if __name__ == "__main__":
    main()
