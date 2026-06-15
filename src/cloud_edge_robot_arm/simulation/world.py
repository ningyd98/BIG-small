from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimulatedWorld:
    scene_version: int = 1
    target_visible: bool = True
    target_moved: bool = False
    target_lost: bool = False
    obstacle_inserted: bool = False
    obstacle_count: int = 0
    obstacle_change_rate: float = 0.0
    scene_confidence: float = 0.95
    target_confidence: float = 0.95
    perception_degraded: bool = False
    cloud_available: bool = True
    emergency_stop: bool = False

    def move_target(self) -> None:
        self.target_moved = True
        self.scene_version += 1

    def insert_obstacle(self) -> None:
        self.obstacle_inserted = True
        self.obstacle_count += 1
        self.obstacle_change_rate = max(self.obstacle_change_rate, 0.8)
        self.scene_version += 1

    def lose_target(self) -> None:
        self.target_lost = True
        self.target_visible = False
        self.target_confidence = 0.0
        self.scene_confidence = min(self.scene_confidence, 0.45)
        self.scene_version += 1

    def degrade_perception(self) -> None:
        self.perception_degraded = True
        self.scene_confidence = 0.35
        self.target_confidence = 0.3
        self.scene_version += 1

    def set_cloud_available(self, value: bool) -> None:
        self.cloud_available = value

    def trigger_emergency_stop(self) -> None:
        self.emergency_stop = True
        self.scene_version += 1
