"""真实数据独立验收；未显式提供部署路径时SKIP，不能计作真实PASS。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.external.deployment import prepare_plan, smoke_dataset
from cloud_edge_robot_arm.datasets.external.index import load_index

pytestmark = pytest.mark.real_rgbd_dataset


@pytest.mark.parametrize("dataset", ["robomind", "graspclutter6d"])
def test_actual_loader_and_offline_provider(dataset: str) -> None:
    value = os.environ.get("BIGSMALL_RGBD_INTEGRATION_ROOT")
    if not value:
        pytest.skip("explicit BIGSMALL_RGBD_INTEGRATION_ROOT is required; real data NOT_RUN")
    root = Path(value).expanduser().resolve()
    if not (root / "raw" / dataset / "COMPLETE.json").is_file():
        pytest.fail(f"requested real dataset has not finished deployment: {dataset}")
    rows = load_index(root / "manifests" / f"{dataset}-index.jsonl")
    assert len({row.get("episode_id") or row.get("scene_id") for row in rows}) >= 10
    if dataset == "robomind":
        assert len({row["task_id"] for row in rows}) >= 2
    plan = prepare_plan(dataset, "smoke", root)
    for workers in (0, 2):
        report = smoke_dataset(plan, num_workers=workers)
        assert report["source"] == "real_dataset"
        assert report["gt_channel_separate"] and report["hardware_disabled"]
        assert not report["execution_verified"]
