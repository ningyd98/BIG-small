"""复核已落地的真实精选 cohort、米制深度和独立 GT，不进行联网。"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from cloud_edge_robot_arm.datasets.external.deployment import discover, prepare_plan
from cloud_edge_robot_arm.datasets.external.loaders import read_sample

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "datasets/BIGsmall"
plan = prepare_plan("graspclutter6d_curated", "curated", root)
refs = discover(plan)
assert len(refs) == plan["smoke_selection"]["expected_rgbd_samples"] == 40
cohort: dict[str, list[str]] = defaultdict(list)
instance_count = 0
ratios = []
for ref in refs:
    sample = read_sample(ref)
    assert sample.depth_raw.dtype == np.float32
    assert sample.rgb.shape[:2] == sample.depth_raw.shape
    assert sample.depth_m is not None and sample.depth_scale_m == 0.001
    np.testing.assert_allclose(
        sample.depth_m[sample.depth_valid_mask],
        sample.depth_raw[sample.depth_valid_mask] * 0.001,
    )
    assert sample.K_rgb is None and sample.K_depth is None
    assert sample.rgb_depth_aligned is None
    assert sample.timestamp is None and sample.action is None and sample.robot_state is None
    assert sample.official_split is None and ref["protocol"] == "curated_export"
    assert not sample.capabilities["camera_geometry"]
    assert not sample.annotations["issues"]
    assert sample.annotations["instances"]
    assert all(item["visible_mask"]["available"] for item in sample.annotations["instances"])
    assert (
        not {"annotations", "instances", "detections", "grasp_lines"} & sample.model_input().keys()
    )
    cohort[sample.scene_id].append(sample.camera_id)
    instance_count += len(sample.annotations["instances"])
    ratios.append(float(sample.depth_valid_mask.mean()))
assert set(cohort) == set(plan["smoke_selection"]["scene_ids"])
assert all(
    sorted(cameras) == sorted(plan["smoke_selection"]["cameras"]) for cameras in cohort.values()
)
assert instance_count == 669
result = {
    "status": "PASS",
    "source": "real_dataset",
    "network_access": False,
    "samples": len(refs),
    "scenes": len(cohort),
    "scene_cameras": dict(sorted(cohort.items())),
    "visible_instances": instance_count,
    "valid_depth_ratio_range": [min(ratios), max(ratios)],
    "metric_conversion": "source float32 millimetres multiplied once by 0.001",
    "unknown_fields_preserved": True,
    "GT_separate": True,
    "pointcloud_disabled": True,
    "original_full_target_verified": False,
}
target = Path(__file__).with_name("actual-curated-audit.json")
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: value for key, value in result.items() if key != "scene_cameras"}))
