"""Locate and identify the original single-episode entry and its checkout assets."""

from __future__ import annotations

import hashlib
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from cloud_edge_robot_arm import __version__
from cloud_edge_robot_arm.harness.config import HarnessConfig
from cloud_edge_robot_arm.vision.marker_families import marker_family

ENTRY = "scripts/run_sol_molmo_single_episode.py"
SOURCE_FILES = (
    "pyproject.toml",
    ENTRY,
    "configs/research/ced_roles.yaml",
    "src/cloud_edge_robot_arm/__init__.py",
    "src/cloud_edge_robot_arm/research/sol_molmo_single_episode.py",
    "src/cloud_edge_robot_arm/vision/marker_families.py",
    "src/cloud_edge_robot_arm/vision/model_resources.py",
)


def sha256_file(path: Path) -> str:
    """Return the SHA256 of the local file."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class SourceCheckout:
    """Validated source assets and a selected-file provenance summary."""

    root: Path
    revision: str | None
    files: dict[str, str]

    def provenance(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "git_revision": self.revision,
            "scope": "HARNESS_CHECKOUT_SELECTED_FILES",
            "files": self.files,
        }


def verify_checkout(path: Path, config: HarnessConfig) -> SourceCheckout:
    """Verify a source tree and the chosen registered asset before launching it."""
    root = path.resolve(strict=True)
    family = marker_family(config.marker_family)
    source_paths = (*SOURCE_FILES, family.asset_path)
    paths = {}
    for relative in source_paths:
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise ValueError(f"checkout file unavailable or outside source root: {relative}")
        paths[relative] = candidate
    with paths["pyproject.toml"].open("rb") as stream:
        project = tomllib.load(stream).get("project", {})
    if (
        not isinstance(project, dict)
        or project.get("name") != "BIG-small"
        or project.get("version") != __version__
    ):
        raise ValueError("source checkout project or version differs from the installed package")
    hashes = {relative: sha256_file(candidate) for relative, candidate in paths.items()}
    if hashes[family.asset_path] != family.asset_sha256:
        raise ValueError("registered checkout marker asset bytes changed")
    revision = None
    if (root / ".git").exists():
        try:
            git = subprocess.run(
                ["git", "rev-parse", "--show-toplevel", "HEAD"], cwd=root,
                capture_output=True, text=True, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        else:
            lines = git.stdout.splitlines()
            if git.returncode == 0 and len(lines) == 2 and Path(lines[0]).resolve() == root:
                revision = lines[1]
    return SourceCheckout(root, revision, hashes)


# The original approved overlay remains a checkout artifact rather than wheel data.
_R545 = (
    "artifacts/research/process/20261004-ced-development/astra-rounds/"
    "round545-molmo-opencv-runtime-overlay-20261110"
)
OVERLAY = _R545 + "/implementation/launch_molmo_grounded.py"
_OVERLAY_SHA256 = "7e9918bea93a641182e47c69a5741a7895a323064ad6276e252bfa7499995b59"
_NATIVE_MODULES = {
    "cloud_edge_robot_arm": "src/cloud_edge_robot_arm/__init__.py",
    "cloud_edge_robot_arm.vision.molmo_pointing":
        "src/cloud_edge_robot_arm/vision/molmo_pointing.py",
    "cloud_edge_robot_arm.vision.grounded_planner":
        "src/cloud_edge_robot_arm/vision/grounded_planner.py",
    "cloud_edge_robot_arm.vision.model_resources":
        "src/cloud_edge_robot_arm/vision/model_resources.py",
    "cloud_edge_robot_arm.research.sol_molmo_single_episode":
        "src/cloud_edge_robot_arm/research/sol_molmo_single_episode.py",
    "scripts.probe_molmo_grounded_planner": "scripts/probe_molmo_grounded_planner.py",
}


def native_source_bindings(source: SourceCheckout) -> dict[str, object]:
    """Bind the registered overlay and expected project imports for the native child."""
    overlay = source.root / OVERLAY
    if overlay.resolve() != overlay or sha256_file(overlay) != _OVERLAY_SHA256:
        raise ValueError("registered R545 native overlay bytes or location changed")
    modules = {}
    for name, relative in _NATIVE_MODULES.items():
        path = source.root / relative
        if path.resolve() != path or not path.is_file():
            raise ValueError("native project module missing from the selected checkout")
        digest = sha256_file(path)
        if relative in source.files and digest != source.files[relative]:
            raise ValueError("selected checkout source changed before native launch")
        modules[name] = {"path": str(path), "sha256": digest}
    return {
        "overlay": {"path": str(overlay), "sha256": _OVERLAY_SHA256},
        "entry": {"path": str(source.root / ENTRY), "sha256": source.files[ENTRY]},
        "modules": modules,
    }
