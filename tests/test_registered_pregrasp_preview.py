"""Current RGB-D pregrasp candidates remain separate from execution admission."""

from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from tests.test_registered_grounding_preparation import _r675_repaint, _r675_scene, nominal_scene
from tests.test_registered_object_geometry import revised


def api(module):
    function = getattr(module, "registered_marker_aware_pregrasp_preview_v1", None)
    assert callable(function), "source-bound marker-aware pregrasp preview missing"
    return function


def scene(tmp_path, monkeypatch, *, yaw=0):
    module, ref, current, reg, root, hashes, clock, state = nominal_scene(
        tmp_path, monkeypatch, yaw=yaw
    )
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    clock[0] = current.captured_at
    return module, tracker, current, reg, root, hashes, clock, state


@pytest.mark.parametrize("yaw", [0, 1])
@pytest.mark.parametrize("minimum_height_m", [0.16, 0.20])
def test_pregrasp_moves_away_from_current_marker_and_keeps_height(
    tmp_path, monkeypatch, yaw, minimum_height_m
):
    module, tracker, current, _, _, _, _, state = scene(tmp_path, monkeypatch, yaw=yaw)
    result = api(module)(tracker, current, state, minimum_height_m=minimum_height_m)
    assert result["status"] == "DERIVED", result["reason"]
    grasp = np.asarray(result["approach_target_world_m"])
    above = np.asarray(result["target_world_m"])
    # ID7 is mounted on object +Y; a quarter turn puts it on world -X.
    expected = (0.005, 0) if yaw else (0, -0.005)
    assert above[:2] - grasp[:2] == pytest.approx(expected, abs=1e-8)
    assert np.linalg.norm(above[:2] - grasp[:2]) == pytest.approx(0.005)
    assert above[2] == pytest.approx(max(minimum_height_m, grasp[2] + 0.10))
    assert result["observation_id"] == current.observation_id
    assert result["observation_checksum_sha256"] == current.checksum_sha256
    assert result["source_sha256"] == tracker._provider._source_sha256
    assert result["execution_allowed"] is False and result["native_authority"] == "UNAVAILABLE"
    assert result["geometric_error_bound_m"] is None


@pytest.mark.parametrize("fault", ["marker_missing", "stale", "future", "hard_fault"])
def test_pregrasp_never_reuses_successful_pose_after_current_rejection(
    tmp_path, monkeypatch, fault
):
    module, tracker, current, _, _, _, clock, state = scene(tmp_path, monkeypatch)
    prior = api(module)(tracker, current, state)
    assert prior["status"] == "DERIVED"
    if fault == "marker_missing":
        current = _r675_repaint(
            current, [(y, x, 255) for y in range(current.height) for x in range(current.width)]
        )
        current = revised(
            current,
            frame_id="new-missing",
            observation_id="new-missing",
            captured_at=current.captured_at + timedelta(seconds=0.1),
            sim_time_s=current.sim_time_s + 0.1,
        )
        clock[0] = current.captured_at
    elif fault == "stale":
        clock[0] = current.captured_at + timedelta(seconds=5)
    elif fault == "future":
        clock[0] = current.captured_at - timedelta(microseconds=1)
    else:
        state = state.model_copy(update={"estop_engaged": True})
    result = api(module)(tracker, current, state)
    assert result["status"] == "UNKNOWN"
    assert result["target_world_m"] is result["approach_target_world_m"] is None
    assert result["execution_allowed"] is False


@pytest.mark.parametrize("bad", [None, True, "0.16", float("nan"), float("inf"), -1, 0.15])
def test_pregrasp_rejects_invalid_or_lowered_safety_height(tmp_path, monkeypatch, bad):
    module, tracker, current, _, _, _, _, state = scene(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="minimum.*height"):
        api(module)(tracker, current, state, minimum_height_m=bad)


def test_pregrasp_result_is_detached_and_sources_are_rechecked(tmp_path, monkeypatch):
    module, tracker, current, _, root, _, _, state = scene(tmp_path, monkeypatch)
    function = api(module)
    first = function(tracker, current, state)
    assert first["status"] == "DERIVED"
    first["target_world_m"][0] = 99
    second = function(tracker, current, state)
    assert second["target_world_m"][0] != 99
    path = root / "src/cloud_edge_robot_arm/research/native_collection_grounding.py"
    path.write_bytes(path.read_bytes() + b"\n# changed source\n")
    with pytest.raises(ValueError):
        function(tracker, current, state)


def test_pregrasp_rejects_foreign_owned_tracker(tmp_path, monkeypatch):
    module, _, current, _, _, _, _, state = scene(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        api(module)(SimpleNamespace(), current, state)


def test_pregrasp_does_not_upgrade_legacy_exact_region_recipe(tmp_path, monkeypatch):
    module, ref, current, reg, root, hashes, clock, state = _r675_scene(tmp_path, monkeypatch)
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref, reg, source_root=root, source_hashes=hashes
    )
    clock[0] = current.captured_at
    result = api(module)(tracker, current, state)
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "marker_aware_pregrasp_profile_not_supported"
    assert result["target_world_m"] is result["approach_target_world_m"] is None
    assert result["execution_allowed"] is False
