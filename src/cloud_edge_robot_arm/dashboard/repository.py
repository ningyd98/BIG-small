from __future__ import annotations

from pathlib import Path


class DashboardRepository:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root
