"""仿真资产注册表，解析场景资源并保持路径受控。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    path: Path
    sha256: str
    source: str
    version: str
    license: str
    units: str


class AssetRegistry:
    def __init__(self, assets: dict[str, AssetRecord]) -> None:
        self._assets = dict(assets)

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> AssetRegistry:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        base = manifest_path.parent
        assets: dict[str, AssetRecord] = {}
        for item in manifest.get("assets", []):
            typed: dict[str, Any] = dict(item)
            path = (base / str(typed["path"])).resolve()
            record = AssetRecord(
                asset_id=str(typed["id"]),
                path=path,
                sha256=str(typed["sha256"]),
                source=str(typed["source"]),
                version=str(typed["version"]),
                license=str(typed["license"]),
                units=str(typed.get("units", "SI")),
            )
            assets[record.asset_id] = record
        return cls(assets)

    def require(self, asset_id: str) -> AssetRecord:
        try:
            asset = self._assets[asset_id]
        except KeyError as exc:
            raise KeyError(f"unknown asset {asset_id!r}") from exc
        if not asset.path.exists():
            raise FileNotFoundError(asset.path)
        actual = self.compute_sha256(asset.path)
        if actual != asset.sha256:
            raise ValueError(f"asset hash mismatch for {asset_id}: {actual} != {asset.sha256}")
        return asset

    @staticmethod
    def compute_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
