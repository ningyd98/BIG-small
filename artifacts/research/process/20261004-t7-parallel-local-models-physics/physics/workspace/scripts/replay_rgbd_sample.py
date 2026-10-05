"""Reconstruct a saved observation without refreshing its timestamp or dispatching actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from cloud_edge_robot_arm.datasets.rgbd.writer import load_records
    from cloud_edge_robot_arm.vision.capture import save_observation
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    try:
        if args.output.resolve().is_relative_to(args.dataset.resolve()):
            raise ValueError("replay output must be outside the source dataset")
        records = load_records(args.dataset)
        record = next((item for item in records if item.sample_id == args.sample_id), None)
        if record is None:
            raise ValueError("sample ID does not belong to this dataset")
        observation = load_offline_observation(record)
        paths = save_observation(observation, args.output)
        (args.output / "valid_mask.u8").write_bytes(observation.valid_mask_bytes())
        print(json.dumps({"status": "COMPLETE", "sample_id": record.sample_id,
                          "observation_id": observation.observation_id,
                          "captured_at": observation.captured_at.isoformat(),
                          "execution_verified": False, "offline_replay": True,
                          "files": {key: str(path) for key, path in paths.items()}},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
