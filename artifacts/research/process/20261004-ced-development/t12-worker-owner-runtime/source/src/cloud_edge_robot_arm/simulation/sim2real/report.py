"""Timestamp-align simulation and read-only real traces and quantify their gap."""

from __future__ import annotations

import math
import statistics
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GapGateStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class TraceSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elapsed_s: float = Field(ge=0)
    joint_positions_rad: list[float] = Field(default_factory=list, max_length=32)
    tcp_position_m: tuple[float, float, float] | None = None
    sensor_latency_ms: float | None = Field(default=None, ge=0)
    depth_mean_m: float | None = Field(default=None, ge=0)
    frame_id: str = Field(default="world", max_length=80)


class Sim2RealTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1, max_length=120)
    source: Literal["SIM", "REAL", "ISAAC_SIM"]
    clock: Literal["simulation_time", "monotonic_time", "ros_time"]
    frame: str = Field(default="world", max_length=80)
    samples: list[TraceSample] = Field(min_length=2, max_length=10_000)
    parameters: dict[str, float] = Field(default_factory=dict)
    provenance: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_monotonic_time(self) -> Sim2RealTrace:
        times = [sample.elapsed_s for sample in self.samples]
        if any(right <= left for left, right in zip(times, times[1:], strict=False)):
            raise ValueError("trace elapsed_s values must be strictly increasing")
        return self


class GapThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_alignment_ratio: float = Field(default=0.8, ge=0, le=1)
    tcp_rmse_m: float = Field(default=0.03, gt=0)
    joint_rmse_rad: float = Field(default=0.08, gt=0)
    sensor_latency_rmse_ms: float = Field(default=25.0, gt=0)
    timestamp_skew_p95_ms: float = Field(default=25.0, gt=0)


class GapReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation: Sim2RealTrace
    real: Sim2RealTrace
    alignment_tolerance_ms: float = Field(default=50.0, gt=0, le=5_000)
    thresholds: GapThresholds = Field(default_factory=GapThresholds)

    @model_validator(mode="after")
    def validate_sources_and_frames(self) -> GapReportRequest:
        if self.simulation.source == "REAL" or self.real.source != "REAL":
            raise ValueError("gap report requires simulation/Isaac trace and REAL trace")
        if self.simulation.frame != self.real.frame:
            raise ValueError("sim and real traces must use the same coordinate frame")
        return self


class GapMetric(BaseModel):
    name: str
    value: float
    unit: str
    threshold: float | None = None
    status: GapGateStatus


class ParameterGap(BaseModel):
    parameter: str
    simulation_value: float | None = None
    real_value: float | None = None
    absolute_delta: float | None = None
    status: Literal["ALIGNED", "MISSING_SIM", "MISSING_REAL"]


class GapReportResponse(BaseModel):
    schema_version: str = "sim2real.gap-report.v1"
    simulation_trace_id: str
    real_trace_id: str
    status: GapGateStatus
    aligned_sample_count: int = Field(ge=0)
    simulation_sample_count: int = Field(ge=0)
    real_sample_count: int = Field(ge=0)
    alignment_ratio: float = Field(ge=0, le=1)
    metrics: list[GapMetric]
    parameter_gaps: list[ParameterGap]
    warnings: list[str] = Field(default_factory=list)
    safety_boundary: dict[str, object] = Field(
        default_factory=lambda: {
            "real_trace_is_read_only_evidence": True,
            "real_controller_contacted_by_reporter": False,
            "hardware_write_operations": [],
            "real_motion_dispatch_enabled": False,
        }
    )
    markdown: str = ""


def generate_gap_report(request: GapReportRequest) -> GapReportResponse:
    pairs = align_trace_samples(request)
    alignment_ratio = len(pairs) / max(1, len(request.real.samples))
    metrics: list[GapMetric] = [
        _metric(
            "alignment_ratio",
            alignment_ratio,
            "ratio",
            request.thresholds.minimum_alignment_ratio,
            higher_is_better=True,
        )
    ]
    tcp_errors = [
        _euclidean(sim.tcp_position_m, real.tcp_position_m)
        for sim, real, _ in pairs
        if sim.tcp_position_m is not None and real.tcp_position_m is not None
    ]
    joint_errors = [
        error
        for sim, real, _ in pairs
        if (error := _joint_error(sim.joint_positions_rad, real.joint_positions_rad)) is not None
    ]
    latency_errors = [
        abs(sim.sensor_latency_ms - real.sensor_latency_ms)
        for sim, real, _ in pairs
        if sim.sensor_latency_ms is not None and real.sensor_latency_ms is not None
    ]
    depth_errors = [
        abs(sim.depth_mean_m - real.depth_mean_m)
        for sim, real, _ in pairs
        if sim.depth_mean_m is not None and real.depth_mean_m is not None
    ]
    skew_ms = [skew * 1_000.0 for _, _, skew in pairs]
    _append_rmse(metrics, "tcp_position_rmse", tcp_errors, "m", request.thresholds.tcp_rmse_m)
    _append_rmse(
        metrics,
        "joint_position_rmse",
        joint_errors,
        "rad",
        request.thresholds.joint_rmse_rad,
    )
    _append_rmse(
        metrics,
        "sensor_latency_rmse",
        latency_errors,
        "ms",
        request.thresholds.sensor_latency_rmse_ms,
    )
    if depth_errors:
        metrics.append(_metric("depth_mean_rmse", _rmse(depth_errors), "m", None))
    if skew_ms:
        metrics.append(
            _metric(
                "timestamp_skew_p95",
                _percentile(skew_ms, 0.95),
                "ms",
                request.thresholds.timestamp_skew_p95_ms,
            )
        )

    warnings: list[str] = []
    if not tcp_errors:
        warnings.append("TCP pose metric unavailable: aligned samples did not contain both poses")
    if not joint_errors:
        warnings.append("Joint metric unavailable: aligned samples did not share joint vectors")
    if not latency_errors:
        warnings.append("Sensor latency metric unavailable")
    parameter_gaps = _parameter_gaps(request.simulation, request.real)
    missing_parameters = [item.parameter for item in parameter_gaps if item.status != "ALIGNED"]
    if missing_parameters:
        warnings.append("Parameter evidence incomplete: " + ", ".join(missing_parameters))
    metric_statuses = {metric.status for metric in metrics}
    status = (
        GapGateStatus.FAIL
        if GapGateStatus.FAIL in metric_statuses
        else GapGateStatus.WARN
        if warnings or GapGateStatus.WARN in metric_statuses
        else GapGateStatus.PASS
    )
    report = GapReportResponse(
        simulation_trace_id=request.simulation.trace_id,
        real_trace_id=request.real.trace_id,
        status=status,
        aligned_sample_count=len(pairs),
        simulation_sample_count=len(request.simulation.samples),
        real_sample_count=len(request.real.samples),
        alignment_ratio=alignment_ratio,
        metrics=metrics,
        parameter_gaps=parameter_gaps,
        warnings=warnings,
    )
    return report.model_copy(update={"markdown": render_gap_report_markdown(report)})


def align_trace_samples(
    request: GapReportRequest,
) -> list[tuple[TraceSample, TraceSample, float]]:
    """Nearest-neighbor alignment on elapsed time with a hard skew gate."""

    simulation = request.simulation.samples
    tolerance_s = request.alignment_tolerance_ms / 1_000.0
    pairs: list[tuple[TraceSample, TraceSample, float]] = []
    cursor = 0
    for real in request.real.samples:
        while cursor + 1 < len(simulation) and abs(
            simulation[cursor + 1].elapsed_s - real.elapsed_s
        ) <= abs(simulation[cursor].elapsed_s - real.elapsed_s):
            cursor += 1
        skew = abs(simulation[cursor].elapsed_s - real.elapsed_s)
        if skew <= tolerance_s:
            pairs.append((simulation[cursor], real, skew))
    return pairs


def render_gap_report_markdown(report: GapReportResponse) -> str:
    lines = [
        "# Sim/Real Gap Report",
        "",
        f"- status: **{report.status.value}**",
        f"- simulation trace: `{report.simulation_trace_id}`",
        f"- real trace: `{report.real_trace_id}`",
        f"- aligned samples: {report.aligned_sample_count}/{report.real_sample_count} "
        f"({report.alignment_ratio:.1%})",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Threshold | Status |",
        "|---|---:|---:|---|",
    ]
    for metric in report.metrics:
        threshold = "—" if metric.threshold is None else f"{metric.threshold:g} {metric.unit}"
        lines.append(
            f"| {metric.name} | {metric.value:.6g} {metric.unit} | {threshold} | "
            f"{metric.status.value} |"
        )
    lines.extend(
        [
            "",
            "## Parameter Gap",
            "",
            "| Parameter | Sim | Real | Absolute delta | Status |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for item in report.parameter_gaps:
        lines.append(
            f"| {item.parameter} | {_display(item.simulation_value)} | "
            f"{_display(item.real_value)} | {_display(item.absolute_delta)} | {item.status} |"
        )
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(
        [
            "",
            "## Safety Boundary",
            "",
            "This report consumes read-only evidence and does not contact a real controller or "
            "enable real motion.",
            "",
            "```text",
            "real_controller_contacted_by_reporter=false",
            "hardware_write_operations=[]",
            "real_motion_dispatch_enabled=false",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _append_rmse(
    metrics: list[GapMetric], name: str, errors: list[float], unit: str, threshold: float
) -> None:
    if errors:
        metrics.append(_metric(name, _rmse(errors), unit, threshold))


def _metric(
    name: str,
    value: float,
    unit: str,
    threshold: float | None,
    *,
    higher_is_better: bool = False,
) -> GapMetric:
    if threshold is None:
        status = GapGateStatus.PASS
    else:
        passed = value >= threshold if higher_is_better else value <= threshold
        status = GapGateStatus.PASS if passed else GapGateStatus.FAIL
    return GapMetric(
        name=name,
        value=round(value, 9),
        unit=unit,
        threshold=threshold,
        status=status,
    )


def _parameter_gaps(simulation: Sim2RealTrace, real: Sim2RealTrace) -> list[ParameterGap]:
    result: list[ParameterGap] = []
    for name in sorted(set(simulation.parameters) | set(real.parameters)):
        sim = simulation.parameters.get(name)
        measured = real.parameters.get(name)
        if sim is None:
            status: Literal["ALIGNED", "MISSING_SIM", "MISSING_REAL"] = "MISSING_SIM"
        elif measured is None:
            status = "MISSING_REAL"
        else:
            status = "ALIGNED"
        result.append(
            ParameterGap(
                parameter=name,
                simulation_value=sim,
                real_value=measured,
                absolute_delta=(
                    abs(sim - measured) if sim is not None and measured is not None else None
                ),
                status=status,
            )
        )
    return result


def _joint_error(left: list[float], right: list[float]) -> float | None:
    if not left or len(left) != len(right):
        return None
    return math.sqrt(statistics.fmean((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _euclidean(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _rmse(errors: list[float]) -> float:
    return math.sqrt(statistics.fmean(error**2 for error in errors))


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * quantile) - 1))
    return ordered[index]


def _display(value: float | None) -> str:
    return "—" if value is None else f"{value:.6g}"
