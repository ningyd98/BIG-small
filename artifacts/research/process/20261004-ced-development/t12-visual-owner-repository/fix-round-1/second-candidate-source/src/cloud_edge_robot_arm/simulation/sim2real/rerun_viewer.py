"""Rerun trajectory/sensor alignment viewer for Sim2Real evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.simulation.sim2real.report import (
    GapReportRequest,
    align_trace_samples,
    generate_gap_report,
)


def write_rerun_recording(
    request: GapReportRequest,
    *,
    output_path: Path,
    recording_id: str = "sim2real-alignment",
) -> Path:
    try:
        import rerun as rr  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Rerun is not installed; install BIG-small[sim-observability]") from exc

    report = generate_gap_report(request)
    pairs = align_trace_samples(request)
    simulation_path = [
        sample.tcp_position_m for sample in request.simulation.samples if sample.tcp_position_m
    ]
    real_path = [sample.tcp_position_m for sample in request.real.samples if sample.tcp_position_m]
    with rr.RecordingStream(
        "bigsmall_sim2real_alignment", recording_id=recording_id, send_properties=False
    ) as recording:
        recording.save(str(output_path))
        if simulation_path:
            recording.log(
                "world/sim/trajectory",
                rr.LineStrips3D([simulation_path]),
                static=True,
            )
        if real_path:
            recording.log(
                "world/real/trajectory",
                rr.LineStrips3D([real_path]),
                static=True,
            )
        for index, (simulation, real, skew_s) in enumerate(pairs):
            recording.set_time("aligned_sample", sequence=index)
            recording.set_time("elapsed", duration=real.elapsed_s)
            if simulation.tcp_position_m is not None:
                recording.log(
                    "world/sim/tcp",
                    rr.Points3D(
                        [simulation.tcp_position_m],
                        colors=[[0, 160, 255]],
                        radii=0.012,
                    ),
                )
            if real.tcp_position_m is not None:
                recording.log(
                    "world/real/tcp",
                    rr.Points3D([real.tcp_position_m], colors=[[255, 120, 0]], radii=0.012),
                )
            recording.log(
                "alignment/timestamp_skew_ms",
                rr.Scalars(skew_s * 1_000.0),
            )
            _log_optional_scalar(
                recording, rr, "sensors/sim/latency_ms", simulation.sensor_latency_ms
            )
            _log_optional_scalar(
                recording,
                rr,
                "sensors/real/latency_ms",
                real.sensor_latency_ms,
            )
            _log_optional_scalar(
                recording,
                rr,
                "sensors/sim/depth_mean_m",
                simulation.depth_mean_m,
            )
            _log_optional_scalar(
                recording,
                rr,
                "sensors/real/depth_mean_m",
                real.depth_mean_m,
            )
            for joint_index, (sim_joint, real_joint) in enumerate(
                zip(simulation.joint_positions_rad, real.joint_positions_rad, strict=False)
            ):
                recording.log(f"joints/{joint_index + 1}/sim_rad", rr.Scalars(sim_joint))
                recording.log(f"joints/{joint_index + 1}/real_rad", rr.Scalars(real_joint))
        recording.log("report/markdown", rr.TextDocument(report.markdown), static=True)
    return output_path


def _log_optional_scalar(recording: Any, rr: Any, path: str, value: float | None) -> None:
    if value is not None:
        recording.log(path, rr.Scalars(value))
