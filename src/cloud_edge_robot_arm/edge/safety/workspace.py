from __future__ import annotations

from cloud_edge_robot_arm.edge.safety.models import WorkspaceDefinition


def check_workspace_bounds(x: float, y: float, z: float, workspace: WorkspaceDefinition) -> bool:
    return (
        workspace.x_min <= x <= workspace.x_max
        and workspace.y_min <= y <= workspace.y_max
        and workspace.z_min <= z <= workspace.z_max
    )


def check_forbidden_zone(
    x: float, y: float, z: float, zones: list[WorkspaceDefinition]
) -> WorkspaceDefinition | None:
    for zone in zones:
        if check_workspace_bounds(x, y, z, zone):
            return zone
    return None
