"""复验已选来源的重复部署、批读取和离线回放；所有操作均为本地。"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from cloud_edge_robot_arm.datasets.external.deployment import (
    index_path,
    prepare_plan,
    run_operation,
)
from cloud_edge_robot_arm.datasets.external.index import load_index
from cloud_edge_robot_arm.datasets.external.loaders import DatasetLoader, read_sample, time_windows
from cloud_edge_robot_arm.datasets.external.prepared import DATASETS
from cloud_edge_robot_arm.datasets.external.provider import DatasetObservationProvider


def verify(root: Path) -> dict:
    results = {}
    for dataset in DATASETS:
        started = time.monotonic()
        plan = prepare_plan(dataset, "curated", root)
        reused = run_operation("extract", plan)
        assert reused["status"] == "REUSED"
        deployed = run_operation("deploy", plan, num_workers=2)
        assert deployed["verified_scope"] == "SELECTED_RGBD_VERIFIED"
        rows = load_index(index_path(root, dataset))
        sampled = [rows[i] for i in sorted({0, len(rows) // 2, len(rows) - 1})]
        direct = next(iter(DatasetLoader(sampled, batch_size=len(sampled), num_workers=0)))
        workers = next(iter(DatasetLoader(sampled, batch_size=len(sampled), num_workers=2)))
        for key in ("rgb", "depth_raw", "depth_valid_mask"):
            assert np.array_equal(direct[key], workers[key]), (dataset, key)
        replay = DatasetObservationProvider(rows)
        first = replay.next_observation()
        replay.pause()
        try:
            replay.next_observation()
        except RuntimeError:
            pass
        else:
            raise AssertionError("pause was not enforced")
        replay.seek(len(rows) - 1)
        replay.resume()
        last = replay.next_observation()
        assert first["timestamp"] == read_sample(rows[0]).timestamp
        assert last["timestamp"] == read_sample(rows[-1]).timestamp
        for observation in (first, last):
            assert observation["source"] == "dataset_replay"
            assert observation["execution_verified"] is False
            assert "annotations" not in observation and "action" not in observation
        if dataset == "microagi01_small":
            assert first["acquisition_time_unknown"] is True
        if dataset == "industryshapes_real":
            assert {row["split"] for row in rows} == {"test"}
            assert replay.oracle_annotations()["channel"] == "oracle_evaluation"
        else:
            assert {row["split"] for row in rows} == {"unknown"}
        conversion = json.loads((root / "raw" / dataset / "conversion.json").read_text())
        download = json.loads((root / "reports" / dataset / "download.json").read_text())
        assert download["network_bytes"] == 0
        results[dataset] = {
            "verified_scope": deployed["verified_scope"],
            "samples": len(rows),
            "groups": deployed["groups"],
            "split_counts": dict(Counter(row["split"] for row in rows)),
            "split_audit": deployed["split_audit"],
            "capability_counts": deployed["capability_counts"],
            "preview_frames": deployed["preview_report"]["frames"],
            "preview_groups": deployed["preview_report"]["groups"],
            "conversion": conversion,
            "repeated_extraction": reused["status"],
            "repeated_deployment": deployed["deployment_status"],
            "worker_0_2_exact_equal_first_middle_last": True,
            "pause_seek_resume_and_timestamp_preserved": True,
            "ordinary_observation_gt_action_absent": True,
            "time_windows_length_3": len(time_windows(rows, length=3))
            if rows[0].get("episode_id")
            else None,
            "network_bytes": download["network_bytes"],
            "elapsed_seconds": time.monotonic() - started,
            "index": str(index_path(root, dataset)),
            "preview_html": deployed["preview_report"]["html"],
        }
        print(json.dumps({"dataset": dataset, "samples": len(rows), "verified": True}), flush=True)
    return {
        "status": "SELECTED_RGBD_READERS_VERIFIED",
        "datasets": results,
        "total_rgbd_samples": sum(r["samples"] for r in results.values()),
        "data_root": str(root),
        "additional_network_bytes": 0,
        "full_upstream_datasets_verified": False,
        "training_run": False,
        "real_vlm_verified": False,
        "robot_execution_verified": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path.home() / "datasets/BIGsmall")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("acceptance.json"))
    args = parser.parse_args()
    result = verify(args.data_root.resolve())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
