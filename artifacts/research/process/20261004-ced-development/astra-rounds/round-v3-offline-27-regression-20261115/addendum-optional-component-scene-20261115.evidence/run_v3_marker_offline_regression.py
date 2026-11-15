#!/usr/bin/env python3
"""离线标记回归入口；固定源码导入，逐例新进程，不启动远程模型。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """运行严格输入验证、历史帧配对审计或原27例的新worker闭环。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify", "audit", "audit-child", "case", "batch"))
    parser.add_argument("--v3-root", type=Path, required=True)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT
        / "artifacts/research/process/20261115-v4-marker-ambiguity/v3-baseline/snapshot.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case")
    parser.add_argument("--audit-source", type=Path)
    args = parser.parse_args()
    source = args.audit_source.resolve() if args.mode == "audit-child" else ROOT
    if source is None:
        parser.error("audit source required")
    sys.path[:0] = [str(source / "src"), str(source)]
    os.environ["MUJOCO_GL"] = "egl"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # 审计归档V3时只让其核心模块导入归档路径；本驱动文件单独显式加载。
    spec = importlib.util.spec_from_file_location(
        "_offline_regression_driver",
        ROOT / "src/cloud_edge_robot_arm/research/sol_molmo_offline_regression.py",
    )
    regression = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = regression
    spec.loader.exec_module(regression)
    manifest = regression.load_v3_manifest(args.v3_root, args.baseline)
    if args.mode == "audit-child":
        regression.audit_child(manifest, args.output, source)
        return 0
    if args.mode == "verify":
        regression.new_output(args.output, [manifest.root])
        regression._write(
            args.output / "inputs.json",
            {
                "cases": len(manifest.cases),
                "frames": len(manifest.frames),
                "original_successes": list(regression.SUCCESS_CASES),
                "verified_files": manifest.verified_files,
            },
        )
        return 0
    if args.mode == "audit":
        report = regression.audit_frozen_frames(manifest, args.output)
        print(json.dumps({k: v for k, v in report.items() if k != "pairs"}))
        return int(report["new_grounding_rejections"] != 0)
    if args.mode == "case":
        if args.case is None:
            parser.error("case id required")
        report = regression.run_frozen_component_case(args.case, manifest, args.output)
        print(
            json.dumps(
                {
                    k: report.get(k)
                    for k in (
                        "case",
                        "component_success",
                        "worker_status",
                        "terminal_reason",
                        "error",
                        "point_replays",
                        "cloud_replays",
                    )
                }
            )
        )
        return int(not report["component_success"])
    regression.new_output(args.output, [manifest.root])
    results = []
    environment = os.environ | {
        "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT),
        "MUJOCO_GL": "egl",
    }
    for case in regression.SUCCESS_CASES:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "case",
            "--case",
            case,
            "--v3-root",
            str(manifest.root),
            "--baseline",
            str(manifest.baseline),
            "--output",
            str(args.output / case),
        ]
        with (args.output / (case + ".log")).open("xb") as log:
            process = subprocess.run(
                command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False
            )
        result_path = args.output / case / "result.json"
        row = (
            json.loads(result_path.read_bytes())
            if result_path.is_file()
            else {"component_success": False, "error": "CHILD_RESULT_MISSING"}
        )
        results.append(
            {
                "case": case,
                "exit_code": process.returncode,
                "component_success": row["component_success"],
                "error": row.get("error"),
                "terminal_reason": row.get("terminal_reason"),
            }
        )
        print(json.dumps(results[-1]), flush=True)
        if process.returncode or not row["component_success"]:
            break  # 保留首次计划外失败，禁止自动调整后重复或缩减分母。
    report = {
        "scope": regression.SCOPE,
        "original_denominator": 27,
        "results": results,
        "successes": sum(r["component_success"] for r in results),
        "not_run": 27 - len(results),
        "complete": len(results) == 27,
        "new_inference_requests": 0,
    }
    regression._write(args.output / "batch-result.json", report)
    return int(report["successes"] != 27)


if __name__ == "__main__":
    raise SystemExit(main())
