"""真实第三方RGB-D部署CLI；不会训练模型或进入硬件执行链路。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(argv: list[str] | None = None) -> int:
    from cloud_edge_robot_arm.datasets.external.deployment import (
        DATASETS,
        data_root,
        doctor,
        prepare_plan,
        run_operation,
        update_status,
        write_json,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "doctor",
            "plan",
            "download",
            "extract",
            "validate",
            "index",
            "preview",
            "smoke",
            "status",
            "deploy",
        ],
    )
    parser.add_argument("--dataset", choices=["all", *DATASETS], default="all")
    parser.add_argument("--profile", choices=["smoke", "pilot", "full", "curated"], default="smoke")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="默认读取YAML decode_workers=2；设0为单进程CPU读取",
    )
    parser.add_argument(
        "--offline", action="store_true", help="doctor不联网；其他命令不得借此替代真实数据"
    )
    args = parser.parse_args(argv)
    root = data_root(args.data_root)
    if args.command == "doctor":
        result = doctor(root, check_sources=not args.offline, config=args.config)
        write_json(root / "reports/doctor.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["write_permission"] else 3
    results, exit_code = {}, 0
    for dataset in DATASETS if args.dataset == "all" else (args.dataset,):
        try:
            plan = prepare_plan(dataset, args.profile, root, args.config)
            workers = plan["decode_workers"] if args.num_workers is None else args.num_workers
            result = run_operation(args.command, plan, num_workers=workers)
            results[dataset] = result
            if str(result.get("download_status", "")).startswith("BLOCKED"):
                exit_code = 3
        except KeyboardInterrupt:
            update_status(
                root,
                dataset,
                download_status="INTERRUPTED",
                verified_scope="NOT_VERIFIED",
                reason="User cancellation; persistent partial files retained",
            )
            print(json.dumps({"dataset_id": dataset, "status": "INTERRUPTED"}))
            return 130
        except (ValueError, OSError, RuntimeError, KeyError, IndexError) as exc:
            detail = str(exc)
            blocked = next(
                (
                    code
                    for code in (
                        "BLOCKED_AUTH",
                        "BLOCKED_STORAGE",
                        "BLOCKED_BUDGET",
                        "BLOCKED_NETWORK",
                    )
                    if code in detail
                ),
                None,
            )
            if "NETWORK:" in detail and blocked is None:
                blocked = "BLOCKED_NETWORK"
            failed = blocked or "FAILED"
            results[dataset] = {
                "status": failed,
                "error_type": type(exc).__name__,
                "reason": detail,
            }
            update_status(
                root,
                dataset,
                deployment_status=failed,
                reason=detail,
                **({"download_status": failed} if args.command in {"download", "deploy"} else {}),
            )
            exit_code = max(exit_code, 3 if blocked else 2)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
