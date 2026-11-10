"""R550 observation-only runner; preserve original returns and enforce one paid start."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROUND = Path(__file__).resolve().parents[1]
WORKTREE = ROUND.parents[5]


def stamp() -> dict[str, Any]:
    return {"utc": datetime.now(UTC).isoformat(), "monotonic_s": time.monotonic()}


def write_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class Probe:
    def __init__(self, output: Path) -> None:
        output.mkdir(parents=True, exist_ok=False)
        self.output = output
        self.paid_starts = 0
        self.pipeline_calls = 0
        self.gaps: list[dict[str, str]] = []
        write_exclusive(
            output / "allocation.json",
            {"prior_native_loads": 2, "prior_generations": 4, "paid_start_cap": 1},
        )

    def save(self, name: str, value: Any) -> None:
        try:
            write_exclusive(self.output / name, value)
        except Exception as exc:
            self.gaps.append({"file": name, "error_type": type(exc).__name__})
            print(json.dumps({"probe_capture_gap": name, "error_type": type(exc).__name__}))

    def wrap_post(self, original: Any) -> Any:
        def observed(adapter: Any, path: str, body: Any, *args: Any, **kwargs: Any) -> Any:
            if self.paid_starts >= 1:
                raise RuntimeError("R550 paid start allocation exhausted")
            self.paid_starts += 1
            start = stamp()
            # A durable reservation is required before any original transport delegation.
            write_exclusive(
                self.output / "post-start-01.json",
                {"start": start, "path": path, "paid_starts": self.paid_starts},
            )
            try:
                result = original(adapter, path, body, *args, **kwargs)
            except BaseException as exc:
                end = stamp()
                self.save(
                    "post-end-01.json",
                    {"start": start, "end": end, "error_type": type(exc).__name__},
                )
                raise
            end = stamp()
            self.save(
                "post-end-01.json",
                {"start": start, "end": end, "status": "ORIGINAL_RETURNED"},
            )
            return result

        return observed

    def wrap_process(self, original: Any) -> Any:
        def observed(pipeline: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            self.pipeline_calls += 1
            index = self.pipeline_calls
            start = stamp()
            observation = request.observation
            self.save(
                f"pipeline-start-{index:02}.json",
                {
                    "start": start,
                    "request_id": request.request_id,
                    "captured_at": observation.captured_at.isoformat() if observation else None,
                    "observation_checksum": observation.checksum_sha256 if observation else None,
                },
            )
            try:
                result = original(pipeline, request, *args, **kwargs)
            except BaseException as exc:
                self.save(
                    f"pipeline-end-{index:02}.json",
                    {"start": start, "end": stamp(), "error_type": type(exc).__name__},
                )
                raise
            end = stamp()
            try:
                actual = result.model_dump(mode="json")
            except Exception as exc:
                self.gaps.append(
                    {"file": f"pipeline-return-{index:02}.json", "error_type": type(exc).__name__}
                )
            else:
                self.save(f"pipeline-return-{index:02}.json", actual)
            self.save(
                f"pipeline-end-{index:02}.json",
                {"start": start, "end": end, "status": "ORIGINAL_RETURNED"},
            )
            return result

        return observed

    def finalize(self) -> None:
        self.save(
            "probe-summary.json",
            {
                "paid_starts": self.paid_starts,
                "pipeline_calls": self.pipeline_calls,
                "capture_gaps": self.gaps,
                "timing_scope": "inclusive local call boundaries; not provider compute time",
                "http_numeric_status": "NOT_CAPTURED",
                "hardware_dispatch": False,
            },
        )
        rows = []
        for path in sorted(self.output.iterdir()):
            if path.is_file():
                rows.append(
                    {
                        "path": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        self.save("probe-manifest.local.json", {"files": rows})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-output", type=Path, required=True)
    args, cli_args = parser.parse_known_args()
    probe = Probe(args.probe_output)
    launcher_path = (
        ROUND.parent
        / "round545-molmo-opencv-runtime-overlay-20261110/implementation/launch_molmo_grounded.py"
    )
    spec = importlib.util.spec_from_file_location("r550_original_overlay", launcher_path)
    assert spec is not None and spec.loader is not None
    launcher = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(launcher)
        probe.save("runtime-preflight.json", launcher.configure_overlay())
        from scripts.probe_molmo_grounded_planner import main as cli_main

        from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
        from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

        original_process = PlanningPipeline.process
        original_post = RGBDPlannerAdapter._post
        PlanningPipeline.process = probe.wrap_process(original_process)
        RGBDPlannerAdapter._post = probe.wrap_post(original_post)
        try:
            exit_code = cli_main(cli_args)
        finally:
            PlanningPipeline.process = original_process
            RGBDPlannerAdapter._post = original_post
        probe.save("cli-return.json", {"exit_code": exit_code})
        return exit_code
    finally:
        probe.finalize()


if __name__ == "__main__":
    sys.exit(main())
