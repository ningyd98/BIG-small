"""Freeze this module and its complete local Python/read-only fixture dependencies."""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
MOTION = Path("artifacts/research/process/20261004-ced-development/t7b-pose-marker-motion-development")
OWNED = ("src/cloud_edge_robot_arm/research/risk_sources.py", "tests/test_research_risk_sources.py")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def main() -> None:
    if (HERE / "source-hashes.json").exists():
        raise RuntimeError("released snapshot already exists; never overwrite")
    python_sources = {str(path.relative_to(ROOT)) for path in
                      (ROOT / "src/cloud_edge_robot_arm").rglob("*.py")}
    names = set(python_sources) | set(OWNED) | {
        "pyproject.toml", "scripts/run_rgbd_pilot.py", "configs/research/risk.yaml",
        "configs/research/ced_roles.yaml", "configs/research/ced_exclusions.yaml",
        "tests/test_rgbd_risk_calibration.py", "tests/test_pose_marker_evidence.py",
        "tests/test_pose_marker_assets.py", str(MOTION / "header.json"),
        str(MOTION / "source-hashes.json"), str(MOTION / "report.md"),
        str(MOTION / "root-independent-review.md"), str(MOTION / "root-review-setup.json"),
        str(MOTION / "development-exclusion.json"),
        "artifacts/research/process/20261004-ced-development/"
        "t9-actual-risk-source-design/artifact-hashes.json",
        "artifacts/research/process/20261004-ced-development/"
        "t8b-module/fix-round-3-release-source-hashes.json",
        "artifacts/research/process/20261004-ced-development/"
        "t8-billing-source-design/artifact-hashes.json",
    }
    names |= set(json.loads((ROOT / MOTION / "source-hashes.json").read_bytes()))
    names |= {str(path.relative_to(ROOT)) for path in (ROOT / MOTION / "attempt-1").rglob("*")
              if path.is_file()}
    names |= {str(path.relative_to(ROOT)) for path in ROOT.rglob("conftest.py")
              if not any(part in {".venv", "node_modules", ".git", "source", "source/"}
                         for part in path.parts)}
    originals = {}
    for name in sorted(names):
        path = ROOT / name
        if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)
                                    if part.is_relative_to(ROOT)):
            raise ValueError(f"required dependency absent/symlinked: {name}")
        payload = path.read_bytes()
        if name.endswith(".py"):
            ast.parse(payload, filename=name)
        originals[name] = payload
    for name, payload in originals.items():
        target = HERE / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        assert target.read_bytes() == payload
    assert python_sources == {str(path.relative_to(ROOT)) for path in
                              (ROOT / "src/cloud_edge_robot_arm").rglob("*.py")}
    for name, payload in originals.items():
        assert (ROOT / name).read_bytes() == payload, name
    manifest = {name: sha(payload) for name, payload in originals.items()}
    write("source-hashes.json", manifest)
    write("ownership.json", {
        "owned_files": list(OWNED), "read_only_references": sorted(names - set(OWNED)),
        "source_snapshot": "source", "source_count": len(names),
        "python_namespace_snapshot_count": len(python_sources),
        "fixture_scope": "Original excluded development motion and pure SOFTWARE_ONLY builders",
        "production_files_changed_elsewhere": [], "prior_releases_modified": [],
    })
    versions = {}
    for name in ("numpy", "pydantic", "mujoco", "pytest", "opencv-python-headless"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "NOT_INSTALLED_UNDER_THIS_DISTRIBUTION_NAME"
    write("environment.json", {"versions": versions, "source_ast_parse": "PASS",
                               "physics_or_capture_executed": False})
    for name, expected in manifest.items():
        assert sha((HERE / "source" / name).read_bytes()) == expected
    print(json.dumps({"snapshot_files": len(names), "owned": len(OWNED),
                      "source_manifest_sha256": sha((HERE / "source-hashes.json").read_bytes()),
                      "bytes": sum(map(len, originals.values()))}, sort_keys=True))


if __name__ == "__main__":
    main()
