from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.simulation.asset_registry import AssetRegistry


def test_phase9_asset_manifest_records_hash_and_license() -> None:
    registry = AssetRegistry.from_manifest(Path("assets/manifest.yaml"))
    asset = registry.require("franka_panda_mujoco_scene")

    assert asset.path.exists()
    assert asset.sha256 == registry.compute_sha256(asset.path)
    assert asset.license
    assert asset.units == "SI"
