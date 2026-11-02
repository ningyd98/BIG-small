"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cloud_edge_robot_arm.simulation.asset_registry import AssetRegistry


def test_phase9_asset_manifest_records_hash_and_license() -> None:
    registry = AssetRegistry.from_manifest(Path("assets/manifest.yaml"))
    asset = registry.require("franka_panda_mujoco_scene")

    assert asset.path.exists()
    assert asset.sha256 == registry.compute_sha256(asset.path)
    assert asset.license
    assert asset.units == "SI"
    assert asset.version == "phase9.reference.v3"
    assert asset.path == Path("assets/robots/franka_panda/scene.xml").resolve()


@pytest.mark.parametrize("mismatch", ["stale_manifest", "altered_asset"])
def test_phase9_asset_registry_rejects_stale_or_changed_asset(tmp_path, mismatch) -> None:
    payload = yaml.safe_load(Path("assets/manifest.yaml").read_text())
    asset = next(item for item in payload["assets"] if item["id"] == "franka_panda_mujoco_scene")
    temporary_assets = tmp_path / "assets"
    model = temporary_assets / asset["path"]
    model.parent.mkdir(parents=True)
    original = Path("assets/robots/franka_panda/scene.xml").read_bytes()
    if mismatch == "stale_manifest":
        asset["sha256"] = "6a7938709366801ed6e36c7c504da64a48b7b16bbc02adda2a31417c7ad5b1d1"
        model.write_bytes(original)
    else:
        model.write_bytes(original + b"\n<!-- deliberate isolated test alteration -->\n")
    manifest = temporary_assets / "manifest.yaml"
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False))
    registry = AssetRegistry.from_manifest(manifest)
    with pytest.raises(ValueError, match="asset hash mismatch"):
        registry.require("franka_panda_mujoco_scene")
