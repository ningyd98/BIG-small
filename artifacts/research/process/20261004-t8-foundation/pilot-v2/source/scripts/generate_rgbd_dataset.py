"""Generate or resume bounded, model-free MuJoCo RGB-D evidence."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

import yaml


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from cloud_edge_robot_arm.datasets.rgbd.generator import generate_dataset
    from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig

    cancelled = False

    def request_cancel(_signal: int, _frame: object) -> None:
        nonlocal cancelled
        cancelled = True

    previous = {number: signal.signal(number, request_cancel)
                for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        config = DatasetConfig.model_validate(yaml.safe_load(args.config.read_text()))
        result = generate_dataset(config, args.output, lambda: cancelled)
        print(json.dumps({"output": str(args.output.resolve()),
                          "manifest": result.model_dump(mode="json")}, ensure_ascii=False))
        return {"COMPLETE": 0, "BLOCKED": 3, "CANCELLED": 130}.get(result.status, 4)
    except (ValueError, yaml.YAMLError, FileNotFoundError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    except (ImportError, RuntimeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 3
    except OSError as exc:
        print(json.dumps({"status": "INCOMPLETE", "reason": str(exc)}, ensure_ascii=False))
        return 4
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
