"""单场景配置、标记、真实规划与显式MuJoCo组件诊断入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Direct invocation must select this checkout even with a shared editable venv.
ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    """默认零运行；退出0只表示所选诊断完成，不是抓放成功。"""
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import run_single_episode
    from cloud_edge_robot_arm.vision.marker_families import LEGACY_FAMILY

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42001)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marker-family", default=LEGACY_FAMILY)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-marker", action="store_true")
    modes.add_argument("--plan-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--profile-id")
    parser.add_argument("--model-control-db", type=Path)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--gpu-lock", type=Path)
    parser.add_argument(
        "--application-site-packages",
        type=Path,
        help="追加已有应用环境依赖；保留 Molmo 运行时依赖的优先级，不安装软件包",
    )
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--component-diagnostic", action="store_true",
                        help="与--execute共同启用已授权的MuJoCo组件诊断；不代表T10/G1验收")
    parser.add_argument("--scene-split", choices=("development", "held-out"),
                        help="显式组件诊断的独立位姿采样命名空间；默认保留固定场景")
    parser.add_argument("--cloud-vision-fallback", action="store_true",
                        help="本地失败时将一次云请求改为RGB识别复核；仅限显式付费组件诊断")
    args = parser.parse_args(argv)
    if args.application_site_packages is not None:
        dependency_path = args.application_site_packages.resolve()
        if not dependency_path.is_dir():
            parser.error("application site-packages directory unavailable")
        sys.path.append(str(dependency_path))
    mode = (
        "execute"
        if args.execute
        else "plan-only"
        if args.plan_only
        else "check-marker"
        if args.check_marker
        else "dry-run"
    )
    os.environ.setdefault("MUJOCO_GL", "egl")
    try:
        result = run_single_episode(
            output=args.output,
            seed=args.seed,
            marker_family_id=args.marker_family,
            mode=mode,
            profile_id=args.profile_id,
            model_control_db=args.model_control_db,
            model_directory=args.model_directory,
            asset_manifest=args.asset_manifest,
            gpu_lock=args.gpu_lock,
            allow_paid=args.allow_paid,
            component_diagnostic=args.component_diagnostic,
            scene_split=args.scene_split,
            cloud_vision_fallback=args.cloud_vision_fallback,
        )
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "NOT_STARTED", "error_type": type(error).__name__}))
        return 2
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "mode",
                    "execution_scope",
                    "success",
                    "component_success",
                    "physical_success",
                    "planning_passed",
                    "marker_endpoints_observed",
                    "model_calls",
                    "executed_actions",
                    "blocking_reasons",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return (
        3
        if result["status"] == "BLOCKED"
        else 0
        if result["status"] in {"PREPARED", "MARKER_CHECKED", "PLANNED"}
        or (result["status"] == "COMPONENTS_COMPLETED" and result["component_success"])
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
