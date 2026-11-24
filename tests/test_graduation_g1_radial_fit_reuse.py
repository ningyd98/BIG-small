"""Check same-frame operation reuse against the original scalar calculations."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from scripts.graduation import g1_visibility_grid as grid
from scripts.graduation import g1_visibility_vision as vision

from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROOT = Path(__file__).resolve().parents[1]
TRIAL = (
    ROOT / "experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/d02"
)


@pytest.mark.parametrize(
    "mode", ["normal", "rank_deficient", "near_cutoff", "fallback", "float32", "other_width"]
)
def test_grouped_pose_least_squares_preserves_independent_original_results(monkeypatch, mode):
    rng = np.random.default_rng(41)
    mats = rng.normal(size=(12, 13, 5 if mode == "other_width" else 6))
    mats[2] = mats[3]
    rhs = rng.normal(size=(12, 13))
    if mode == "rank_deficient":
        mats[6, :, -1] = mats[6, :, -2]
    if mode == "near_cutoff":
        mats[0, :, -1] *= np.finfo(float).eps * 4
    if mode == "fallback":
        monkeypatch.setattr(grid, "_LSTSQ_KERNEL", None)
    if mode == "float32":
        mats, rhs = mats.astype(np.float32), rhs.astype(np.float32)
    originals = [np.linalg.lstsq(a, b, rcond=None) for a, b in zip(mats, rhs, strict=True)]
    x, rank, singular = grid._pose_lstsq(mats, rhs)
    for n, (y, _, r, s) in enumerate(originals):
        assert (
            x[n].tobytes() == y.tobytes() and rank[n] == r and singular[n].tobytes() == s.tobytes()
        )
    assert x[2].tobytes() != x[3].tobytes()


def test_nearby_queries_are_scoped_to_one_ordered_current_image_and_keep_borderline(monkeypatch):
    norm = np.linalg.norm
    checked = []

    def count(values, *args, **kwargs):
        if values.shape == (6, 4):
            checked.append(None)
        return norm(values, *args, **kwargs)

    monkeypatch.setattr(grid.np.linalg, "norm", count)
    groups = []

    def weak(gray, code, seeds):
        groups.append([tuple(s[1]) for s in seeds])
        return np.arange(len(seeds))

    monkeypatch.setattr(grid, "_weak_grid_cells", weak)
    for offset in (0, 12):
        seeds = [
            (8, np.float32([24 + x + offset, 30]), np.eye(2, dtype=np.float32) * 3, 10 - i)
            for i, x in enumerate([0, 0.25, 1.0, 1.249, 2.5, 4.0])
        ]
        grid._accept(np.zeros((90, 90), np.uint8), seeds, "test", [], {8})
    assert len(groups) == 2 and all(len(g) == 5 for g in groups)
    assert len(checked) == 10


def test_unregistered_or_failed_kernel_returns_to_public_lstsq(monkeypatch):
    monkeypatch.setattr(grid.np, "__version__", "other")
    assert grid._registered_lstsq_kernel() is None

    def unavailable(*args, **kwargs):
        raise FloatingPointError("native fit unavailable")

    monkeypatch.setattr(grid, "_LSTSQ_KERNEL", unavailable)
    mats = np.stack([np.eye(6), 2.0 * np.eye(6)])
    rhs = np.arange(12, dtype=float).reshape(2, 6)
    x, rank, s = grid._pose_lstsq(mats, rhs)
    for i in range(2):
        original = np.linalg.lstsq(mats[i], rhs[i], rcond=None)
        assert x[i].tobytes() == original[0].tobytes() and rank[i] == original[2]
        assert s[i].tobytes() == original[3].tobytes()


def test_seed_prefilter_retains_native_order_strength_and_every_bit_pattern():
    rng = np.random.default_rng(221)
    gray = rng.integers(0, 256, (200, 240), dtype=np.uint8)
    coords, bases = [], []
    for idx, pattern in enumerate(grid.PATTERNS):
        x, y = (idx % 12) * 18, (idx // 12) * 18
        gray[y : y + 18, x : x + 18] = np.repeat(np.repeat(pattern, 3, axis=0), 3, axis=1) * 255
        coords.append([x + 8.5, y + 8.5])
        bases.append(np.eye(2, dtype=np.float32) * 3)
    coords = np.float32(coords + [[210, 180], [8.25, 7.5]])
    bases = np.float32(bases + [bases[0], bases[0]])
    levels = grid._sample(gray, grid.CELLS @ bases + coords[:, None, :])
    black = np.median(levels[:, grid.BORDER], axis=1)
    white = np.sort(levels[:, grid.DATA], axis=1)[:, -3:].mean(axis=1)
    t = ((white + black) / 2)[:, None]
    ids = grid.WORDS[(levels[:, grid.DATA] > t) @ grid.WEIGHTS]
    eligible = (ids[:, 0] >= 0) & (white - black >= grid.MIN_CONTRAST)
    eligible &= (levels[:, grid.BORDER] > t).sum(axis=1) <= 2
    eligible &= (
        abs(levels[:, grid.BORDER] - black[:, None]) > 0.35 * (white - black)[:, None]
    ).sum(axis=1) <= 4
    original = [
        (
            int(ids[i, 0]),
            coords[i],
            grid.TURNS[ids[i, 1]].T @ bases[i],
            abs(levels[i].astype(float) - t[i]).mean(),
        )
        for i in np.flatnonzero(eligible)
    ]
    new = grid._seeds(coords, bases, gray)
    assert len(new) == len(original) and len(new) >= 100
    for a, b in zip(new, original, strict=True):
        assert all(
            np.asarray(x).tobytes() == np.asarray(y).tobytes() for x, y in zip(a, b, strict=True)
        )


def test_native_1088_preserves_complete_output_and_batches_current_fits(monkeypatch):
    src = TRIAL / "instance/frames/0128.json"
    if not src.exists():
        pytest.skip("local sealed radial source")
    raw = src.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "93d2ceba270fcd109adace2d158483aa3aeea6217717fdb9428af5594a4ed501"
    )
    frame = RGBDObservation.model_validate_json(raw)
    archived = json.loads((TRIAL / "instance/online-vision.json").read_bytes())["frames"][
        frame.frame_id
    ]
    scalar = np.linalg.lstsq
    calls = []

    def count(*args, **kwargs):
        calls.append(None)
        return scalar(*args, **kwargs)

    monkeypatch.setattr(grid.np.linalg, "lstsq", count)
    value = vision.measure_frame(
        frame, json.loads((TRIAL / "allocation.json").read_bytes())["geometry"]
    )
    assert json.loads(json.dumps(value)) == archived["measurement"]
    assert len(calls) < 24
