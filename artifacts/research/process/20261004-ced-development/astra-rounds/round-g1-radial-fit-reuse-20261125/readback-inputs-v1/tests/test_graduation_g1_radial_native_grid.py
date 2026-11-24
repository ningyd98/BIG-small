"""Pin complete native output and the strict photometric boundary on adjacent radial frames."""

import gzip
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from scripts.graduation import g1_visibility_grid as grid
from scripts.graduation import g1_visibility_vision as vision

from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROOT = Path(__file__).resolve().parents[1]
TRIAL = (
    ROOT / "experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/d02"
)
ROUND = (
    ROOT
    / "artifacts/research/process/20261004-ced-development/astra-rounds"
    / "round-g1-radial-native-timing-20261125"
)


def test_radial_feedback_retains_every_measurement_without_duplicate_failed_scalar_fits(
    monkeypatch,
):
    evidence = json.loads(
        gzip.decompress((ROUND / "baseline-seed-profile.public.json.gz").read_bytes())
    )
    if not (TRIAL / "instance/frames/0128.json").is_file():
        pytest.skip("immutable local historical RGB-D witness")
    geometry = json.loads((TRIAL / "allocation.json").read_bytes())["geometry"]
    original = grid._verify
    calls = []

    def count(gray, code, center, basis):
        calls.append(code)
        return original(gray, code, center, basis)

    monkeypatch.setattr(grid, "_verify", count)
    for key, row in evidence["frames"].items():
        raw = (TRIAL / "instance" / key).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["file_sha256"]
        calls.clear()
        value = vision.measure_frame(RGBDObservation.model_validate_json(raw), geometry)
        full = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        assert hashlib.sha256(full).hexdigest() == row["measurement_sha256"]
        assert len(calls) <= 5, (key, calls)


@pytest.mark.parametrize(
    ("white", "patched_white", "strong_negative", "scalar_negative"),
    [
        (200, 124, True, True),
        (200, 125, True, True),
        (194, 122, False, True),
        (200, 126, False, False),
        (200, 127, False, False),
        (200, 200, False, False),
    ],
)
def test_equal_or_near_threshold_and_legitimate_word_keep_complete_scalar_evidence(
    white, patched_white, strong_negative, scalar_negative
):
    # One white data cell has a controlled native gray value. Its interior stays constant
    # during refinement. A 0.25 gray-level neighborhood of the strict boundary is scalar.
    bits = grid.PATTERNS[13]
    image = np.full((190, 190), white, np.uint8)
    patch = bits.astype(np.uint8) * white
    y, x = np.argwhere(bits)[0]
    patch[y, x] = patched_white
    image[35:155, 35:155] = cv2.resize(patch, (120, 120), interpolation=cv2.INTER_NEAREST)
    basis = np.diag(np.float32([20, 20]))
    seeds = [(13, np.float32([94.5 + dx, 94.5]), basis, 1) for dx in (-0.2, 0, 0.2)]
    batched = set(grid._weak_grid_cells(image, 13, seeds))
    assert batched == (set(range(len(seeds))) if strong_negative else set())
    for code, center, pose, _ in seeds:
        assert (grid._verify(image, code, center, pose) is None) is scalar_negative


def test_unstable_black_population_is_already_a_scalar_failure_at_the_first_iteration():
    code = 13
    bits = grid.PATTERNS[code]
    patch = bits.astype(np.uint8) * 200
    patch.flat[np.flatnonzero(~bits.ravel())[:8]] = 80
    image = np.full((190, 190), 200, np.uint8)
    image[35:155, 35:155] = cv2.resize(patch, (120, 120), interpolation=cv2.INTER_NEAREST)
    seeds = [
        (code, np.float32([94.5 + dx, 94.5]), np.eye(2, dtype=np.float32) * 20, 1)
        for dx in (-0.2, 0, 0.2)
    ]
    assert all(grid._verify(image, c, center, basis) is None for c, center, basis, _ in seeds)
    assert set(grid._weak_grid_cells(image, code, seeds)) == set(range(len(seeds)))
