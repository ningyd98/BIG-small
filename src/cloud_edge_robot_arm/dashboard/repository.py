"""Dashboard artifact repository。

当前 repository 只保存 artifact 根目录引用，后续扩展时仍应保持路径脱敏和只读查询边界。
"""

from __future__ import annotations

from pathlib import Path


class DashboardRepository:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root
