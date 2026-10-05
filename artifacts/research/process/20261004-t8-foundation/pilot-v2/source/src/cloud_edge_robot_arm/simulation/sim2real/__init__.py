"""Sim/real trace alignment, visualization, and gap reporting."""

from cloud_edge_robot_arm.simulation.sim2real.report import (
    GapReportRequest,
    GapReportResponse,
    Sim2RealTrace,
    TraceSample,
    generate_gap_report,
    render_gap_report_markdown,
)

__all__ = [
    "GapReportRequest",
    "GapReportResponse",
    "Sim2RealTrace",
    "TraceSample",
    "generate_gap_report",
    "render_gap_report_markdown",
]
