"""小模型目录加载器。

目录来自仓库内 YAML，React 页面只通过后端 API 获取，避免把模型清单写死在
前端。安装状态来自 Ollama `/api/tags` 的实时结果。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cloud_edge_robot_arm.model_control.models import SmallModelCatalogItem

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "configs/models/small_model_catalog.yaml"
)


def load_small_model_catalog(
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    installed_models: set[str] | None = None,
) -> list[SmallModelCatalogItem]:
    """读取小模型目录并标记 Ollama 已安装状态。"""

    installed = installed_models or set()
    if not catalog_path.exists():
        return []
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    rows = raw.get("models", [])
    if not isinstance(rows, list):
        raise ValueError("invalid_small_model_catalog")
    return [
        SmallModelCatalogItem.model_validate(_with_installed(row, installed))
        for row in rows
        if isinstance(row, dict)
    ]


def _with_installed(row: dict[str, Any], installed: set[str]) -> dict[str, Any]:
    payload = dict(row)
    payload["installed"] = str(payload.get("ollama_model", "")) in installed
    return payload
