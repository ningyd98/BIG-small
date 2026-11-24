"""Exercise the expensive partial-print witness through the current-pixel observer."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from scripts.graduation import g1_visibility_grid, g1_visibility_vision

from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROOT = Path(__file__).resolve().parents[1]
WITNESS = (
    ROOT
    / "experiments/results/g1-visibility-pose-repair-20261124/batches/train-current-grid-01/d02"
)


def test_weak_print_keeps_registered_single_id_and_batches_failed_refinements(monkeypatch):
    path = WITNESS / "instance/frames/0073.json"
    if not path.is_file():
        pytest.skip("local immutable historical development RGB-D witness")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "a49ff01183d7f5e6cbd7446bc008eb5992cb556572817a9def8a00c8a82cbe91"
    )
    frame = RGBDObservation.model_validate_json(raw)
    geometry = json.loads((WITNESS / "allocation.json").read_bytes())["geometry"]
    calls = []
    check = g1_visibility_grid._verify

    def count(gray, code, center, basis):
        calls.append(code)
        return check(gray, code, center, basis)

    monkeypatch.setattr(g1_visibility_grid, "_verify", count)
    result = g1_visibility_vision.measure_frame(frame, geometry)
    assert (result["observed_ids"], result["usable_ids"], result["selected_id"]) == ([7], [7], 7)
    assert calls.count(8) < 10


def test_batch_retains_each_current_pose_and_only_proves_existing_scalar_negatives():
    grid = g1_visibility_grid
    gray = np.full((95, 130), 225, np.uint8)
    symbol = cv2.aruco.generateImageMarker(grid.DICTIONARY, 7, 30)
    gray[24:54, 15:45] = symbol
    gray[24:54, 80:110] = symbol
    gray[29:34, 85:90] = 127
    seeds = []
    for x in (29.5, 94.5):
        for dx in (-0.55, 0, 0.55):
            seeds.append((7, np.float32([x + dx, 38.5]), np.diag(np.float32([5.0, 5.0])), 1))
    rejected = set(grid._weak_grid_cells(gray, 7, seeds))
    scalar = [grid._verify(gray, code, center, basis) for code, center, basis, _ in seeds]
    assert all(item is not None for item in scalar[:3])
    assert rejected and all(scalar[i] is None for i in rejected)
    assert not rejected.intersection(range(3))

    points, axes, signs, *_ = grid._transitions(7)
    bases = np.asarray([s[2] for s in seeds], float)
    centers = np.asarray([s[1] for s in seeds], float)
    thresholds = np.full(len(seeds), 127.5)
    contrasts = np.full(len(seeds), 255.0)
    batch = grid._crossings(gray, points, bases, centers, thresholds, contrasts, axes, signs)
    for n in range(len(seeds)):
        one = grid._crossings(gray, points, bases[n], centers[n], 127.5, 255.0, axes, signs)
        assert all(
            np.array_equal(group[n], individual)
            for group, individual in zip(batch, one, strict=True)
        )
