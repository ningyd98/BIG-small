"""Visual feedback must use current RGBD and its matching camera pose."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_opencv_target_evidence import scene, tracker


def acquisition():
    reference = scene(started=datetime.now(UTC) - timedelta(seconds=0.04), source="mujoco_camera")
    tracked = tracker(reference)
    initial = Pose(**dict(zip("xyz", tracked.initial["center"], strict=True)))
    evidence = {
        "resolved_top_grasp_tcp": {**initial.model_dump(), "z": 0.04},
        "grounded_destination": dict(zip("xyz", tracked.destination["center"], strict=True)),
        "top_grasp_support_height_m": 0.0,
    }
    return reference, tracked, evidence, Pose(**evidence["resolved_top_grasp_tcp"])


def current(reference, **kwargs):
    return scene(
        "current", time=1 / 30, started=reference.captured_at,
        source=reference.source, **kwargs,
    )


def revised(observation, **changes):
    return RGBDObservation.model_validate(
        observation.model_dump() | changes | {"checksum_sha256": ""}
    )


def aimed_frame(frame, position, aim):
    forward = np.subtract(aim, position)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 1, 0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    transform = np.eye(4)
    transform[:3, :3] = np.column_stack((right, down, forward))
    transform[:3, 3] = position
    return revised(frame, camera_to_world=tuple(transform.ravel()),
                   calibration_version=f"aimed-{position}")



def feedback(**kwargs):
    from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback

    reference, tracked, evidence, initial = acquisition()
    return (
        OpenCVServoFeedback(
            reference, tracked, evidence, skill="APPROACH", initial_target=initial, **kwargs
        ), reference, initial,
    )


def test_current_target_moves_during_same_skill():
    provider, reference, initial = feedback()
    target = provider.update(current(reference, x=11))
    assert target.x - initial.x == pytest.approx(0.0094, abs=1e-6)
    assert target.y == initial.y
    assert target.z == pytest.approx(initial.z, abs=1e-12)
    assert provider.records[-1]["ground_truth_used_for_control"] is False


def test_camera_translation_does_not_become_object_motion():
    provider, reference, initial = feedback()
    moved = current(reference, x=9, calibration_version="translated-camera")
    transform = np.array(moved.camera_to_world).reshape(4, 4)
    transform[0, 3] += 0.0094
    moved = revised(moved, camera_to_world=tuple(transform.ravel()))
    target = provider.update(moved)
    assert target.x == pytest.approx(initial.x, abs=1e-6)
    assert target.y == initial.y
    assert provider.records[-1]["camera_position_m"] == pytest.approx([0.0094, 0, 1])


@pytest.mark.parametrize("damage", ["missing", "decoy", "depth", "edge_occluder"])
def test_bad_current_geometry_never_reuses_previous_target(damage):
    provider, reference, _ = feedback()
    with pytest.raises(ValueError, match="geometry"):
        provider.update(current(reference, damage=damage))
    assert provider.records == []


@pytest.mark.parametrize("fault", ["stale", "future", "episode", "gap", "jump", "old_calibration"])
def test_invalid_frame_or_discontinuity_is_rejected(fault):
    provider, reference, _ = feedback()
    observation = current(reference)
    if fault == "stale":
        observation = revised(observation, captured_at=datetime.now(UTC) - timedelta(seconds=1))
    elif fault == "future":
        observation = revised(observation, captured_at=datetime.now(UTC) + timedelta(seconds=1))
    elif fault == "episode":
        observation = revised(observation, episode_id="another-episode")
    elif fault == "gap":
        observation = revised(observation, sim_time_s=0.2)
    elif fault == "jump":
        observation = current(reference, x=14)
    else:
        matrix = list(observation.camera_to_world)
        matrix[3] += 0.01
        observation = revised(observation, camera_to_world=tuple(matrix))
    with pytest.raises(ValueError):
        provider.update(observation)


def test_repeated_frame_and_old_fixed_camera_binding_remain_rejected():
    provider, reference, _ = feedback()
    observation = current(reference)
    provider.update(observation)
    with pytest.raises(ValueError, match="repeated"):
        provider.update(observation)
    tracked = tracker(reference)
    matrix = list(observation.camera_to_world)
    matrix[3] += 0.01
    moved = revised(observation, camera_to_world=tuple(matrix), calibration_version="moved")
    assert tracked._binding_reason(moved) is not None


def test_reference_frame_is_not_a_new_servo_sample():
    provider, reference, _ = feedback()
    with pytest.raises(ValueError, match="repeated"):
        provider.update(reference)


def test_future_frame_within_legacy_tolerance_is_rejected():
    provider, reference, _ = feedback()
    future = revised(current(reference), captured_at=datetime.now(UTC) + timedelta(seconds=0.04))
    with pytest.raises(ValueError, match="fresh"):
        provider.update(future)


@pytest.mark.parametrize("failure", [
    "servo registered marker geometry unavailable",
    "servo region geometry unavailable: region_color_boundary_depth_unresolved",
    "servo registered object is not upright",
    "servo region geometry unavailable: region_occluder_depth_invalid",
])
@pytest.mark.parametrize("current_view", [None, 0, 1, 3])
def test_camera_recovery_is_bounded_and_only_for_observability_failures(
    monkeypatch, failure, current_view,
):
    recoverable = failure.endswith(("geometry unavailable", "color_boundary_depth_unresolved"))
    provider, reference, initial = feedback()
    observations = [revised(current(reference), frame_id=f"view-{i}", observation_id=f"view-{i}")
                    for i in range(3)]
    measured, changes, captured = [], [], []

    def update(observation):
        measured.append(observation.observation_id)
        if len(measured) < 3:
            raise ValueError(failure)
        return initial

    monkeypatch.setattr(provider, "update", update)
    views = [((0.1 * i, 0.2, 0.6), (0.2, 0.2, 0.1)) for i in (1, 2, 3, 4)]
    if current_view is not None:
        transform = np.array(observations[0].camera_to_world).reshape(4, 4)
        transform[:3, 3] = views[current_view][0]
        observations[0] = revised(observations[0], camera_to_world=tuple(transform.ravel()),
                                  calibration_version="current-side-view")

    def capture(attempt):
        captured.append(attempt)
        item = observations[attempt]
        return aimed_frame(item, *changes[-1][:2]) if changes else item

    def set_view(position, aim, reason):
        changes.append((position, aim, reason))

    if recoverable:
        result = provider.update_with_camera_views(capture, set_view, views)
        assert result == initial and captured == [0, 1, 2] and len(changes) == 2
        preferred = 1 if current_view == 0 else 0
        assert changes[0][0] == views[preferred][0]
        if current_view is not None:
            assert all(change[0] != views[current_view][0] for change in changes)
        assert changes[0][0] != changes[1][0]
    else:
        with pytest.raises(ValueError, match=failure):
            provider.update_with_camera_views(capture, set_view, views)
        assert captured == [0] and changes == []


def test_camera_position_changes_calibration_without_advancing_physics():
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        before = backend.get_sensor_frame()
        backend.set_camera_position((0.36, 0.01, 1.35))
        after = backend.capture_sensor_frame()
        assert backend.total_physics_steps == 0
        assert after.calibration_version != before.calibration_version
        transform = np.array(after.camera_to_world).reshape(4, 4)
        assert transform[:3, 3] == pytest.approx([0.36, 0.01, 1.35])
        assert transform[:3, 2] == pytest.approx([0, 0, -1])
    finally:
        backend.shutdown()


def test_camera_can_look_at_workspace_from_an_oblique_position():
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        before = backend.get_sensor_frame()
        position, aim = (-0.05, 0.4, 0.7), (0.3, 0.15, 0.05)
        backend.set_camera_position(position, look_at_m=aim)
        after = backend.capture_sensor_frame()
        transform = np.array(after.camera_to_world).reshape(4, 4)
        direction = np.array(aim) - position
        direction /= np.linalg.norm(direction)
        assert transform[:3, 2] == pytest.approx(direction)
        assert after.calibration_version != before.calibration_version
        assert backend.total_physics_steps == 0
        assert backend.command_records[-1]["look_at_m"] == list(aim)
        with pytest.raises(ValueError, match="look-at"):
            backend.set_camera_position(position, look_at_m=position)
        unchanged = backend.capture_sensor_frame()
        assert unchanged.calibration_version == after.calibration_version
    finally:
        backend.shutdown()


def test_explicit_on_demand_scope_preserves_fresh_owned_frames_without_redundant_renders():
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        before = backend.get_sensor_frame()
        with backend.sensor_capture_on_demand():
            backend.step(5)
            assert backend.get_sensor_frame() is before
            owned = backend.capture_sensor_frame()
            assert owned.sim_time_s == backend.get_sim_time()
            assert owned.frame_id != before.frame_id
        assert backend.get_sensor_frame().sim_time_s == backend.get_sim_time()
        backend.step(5)
        assert backend.get_sensor_frame().frame_id != owned.frame_id
    finally:
        backend.shutdown()


def test_ranked_recovery_keeps_two_distinct_alternatives_and_stops_when_all_reject(monkeypatch):
    provider, reference, _ = feedback()
    order = []
    view = (0.0, 0.0, 1.0)
    first = ((0.10, 0.20, 0.8), (0.20, 0.20, 0.1))
    second = ((0.50, 0.20, 0.8), (0.20, 0.20, 0.1))
    unused = ((0.60, 0.20, 0.8), (0.20, 0.20, 0.1))

    def capture(attempt):
        order.append(("capture", attempt, view))
        transform = np.array(reference.camera_to_world).reshape(4, 4)
        transform[:3, 3] = view
        item = revised(
            current(reference), frame_id=f"ranked-{attempt}", observation_id=f"ranked-{attempt}",
            camera_to_world=tuple(transform.ravel()),
        )
        return aimed_frame(item, view, first[1]) if attempt else item

    def set_view(position, _aim, _reason):
        nonlocal view
        view = position
        order.append(("set", view))

    def reject(_observation):
        raise ValueError("servo registered marker geometry unavailable")

    monkeypatch.setattr(provider, "update", reject)
    with pytest.raises(ValueError, match="registered marker geometry unavailable"):
        provider.update_with_camera_views(
            capture, set_view, [first, unused],
            prioritize=lambda _reason, old: [*old[:1], (view, first[1]), first, second, unused],
        )
    assert order == [
        ("capture", 0, (0.0, 0.0, 1.0)), ("set", first[0]),
        ("capture", 1, first[0]), ("set", second[0]), ("capture", 2, second[0]),
    ]
    assert provider.records == []


@pytest.mark.parametrize("skill", ["MOVE_TO_REGION", "PLACE"])
def test_accepted_transport_sample_refreshes_its_current_observation_proposal(monkeypatch, skill):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.research import sol_molmo_components as component

    observation = SimpleNamespace(observation_id=f"current-{skill}")
    estimate = SimpleNamespace(observation_id=observation.observation_id)
    provider = SimpleNamespace(last_accepted_marker=estimate, last_observation=observation)
    old = {"observation_id": "earlier-in-this-skill"}

    def propose(observation, marker, _tracker, _family, _backend, _height):
        assert marker.observation_id == observation.observation_id
        return {"observation_id": observation.observation_id}

    monkeypatch.setattr(component, "_current_transport_view_proposals", propose)
    result = component._refresh_transport_camera_proposal(
        skill, provider, None, "fixture", None, 0.07, old,
    )
    assert result == {"observation_id": observation.observation_id}
    provider.last_accepted_marker = None
    assert component._refresh_transport_camera_proposal(
        skill, provider, None, "fixture", None, 0.07, None,
    ) is None


@pytest.mark.parametrize("all_bad", [False, True])
@pytest.mark.parametrize("reason", [
    "servo registered marker geometry unavailable",
    "servo region geometry unavailable: region_current_corner_anchors_insufficient",
    "servo region geometry unavailable: region_missing_color_not_explained_by_foreground",
    "servo region geometry unavailable: region_color_boundary_depth_unresolved",
])
def test_component_recovery_first_uses_declared_then_ranked_view(monkeypatch, reason, all_bad):
    from cloud_edge_robot_arm.research import sol_molmo_components as component

    provider, reference, initial = feedback()
    position = (0.0, 0.0, 1.0)
    aim = (0.2, 0.2, 0.1)
    before_ranked = (0.10, 0.20, 0.8)
    ranked = (0.50, 0.20, 0.8)
    unused = (0.60, 0.20, 0.8)
    seen = []
    proposal = {"ranked": [
        {"camera_position_m": before_ranked, "camera_look_at_m": aim},
        {"camera_position_m": ranked, "camera_look_at_m": aim},
    ]}

    def capture(attempt):
        transform = np.array(reference.camera_to_world).reshape(4, 4)
        transform[:3, 3] = position
        item = revised(
            current(reference), frame_id=f"place-{attempt}", observation_id=f"place-{attempt}",
            camera_to_world=tuple(transform.ravel()),
        )
        return aimed_frame(item, position, aim) if attempt else item

    def set_view(next_position, _aim, _reason):
        nonlocal position
        position = next_position
        seen.append(position)

    def measure(_observation):
        if position != ranked or all_bad:
            raise ValueError(reason)
        return initial

    def run():
        return provider.update_with_camera_views(
            capture, set_view, [(before_ranked, aim), (unused, aim)],
            prioritize=lambda error, declared: component._prioritize_transport_camera_views(
                error, declared, proposal,
            ),
        )

    monkeypatch.setattr(provider, "update", measure)
    if all_bad:
        with pytest.raises(ValueError, match=reason):
            run()
    else:
        assert run() == initial
    assert seen == [before_ranked, ranked]


_NONPLANAR = "servo registered marker rejected: marker_depth_not_planar"


def _place_reobserve_fixture(monkeypatch, *, fail_all=False):
    provider, reference, initial = feedback()
    provider.skill = "PLACE"
    provider.marker_family_id = "fixture-registered-family"
    alternate = [((x, 0.0, 1.0), (0.2, 0.2, 0.1)) for x in (0.1, 0.2, 0.3)]
    camera = tuple(reference.camera_to_world[i] for i in (3, 7, 11))
    changes = []
    captured = []

    def capture(attempt):
        transform = np.array(reference.camera_to_world).reshape(4, 4)
        transform[:3, 3] = camera
        observation = revised(
            current(reference), frame_id=f"nonplanar-{attempt}",
            observation_id=f"nonplanar-{attempt}", camera_to_world=tuple(transform.ravel()),
            calibration_version=f"nonplanar-camera-{camera[0]}" if camera[0] else
            reference.calibration_version,
        )
        if changes:
            observation = aimed_frame(observation, camera, alternate[0][1])
        captured.append(observation)
        return observation

    def set_view(position, _aim, _reason):
        nonlocal camera
        camera = position
        changes.append(position)

    def update(observation):
        provider._validate(observation)
        if fail_all or observation.camera_to_world[3] != alternate[1][0][0]:
            raise ValueError(_NONPLANAR)
        provider.records.append({"observation_id": observation.observation_id})
        return initial

    monkeypatch.setattr(provider, "update", update)
    return provider, reference, initial, alternate, changes, captured, capture, set_view


def test_default_nonplanar_marker_remains_immediately_fatal(monkeypatch):
    provider, ref, _, alt, changes, captured, capture, set_view = _place_reobserve_fixture(
        monkeypatch,
    )
    with pytest.raises(ValueError, match=_NONPLANAR):
        provider.update_with_camera_views(capture, set_view, alt)
    assert len(captured) == 1 and changes == []
    assert provider.last_observation is ref and provider.records == []


def test_explicit_place_nonplanarity_requires_an_independently_valid_distinct_view(monkeypatch):
    provider, _, initial, alt, changes, captured, capture, set_view = _place_reobserve_fixture(
        monkeypatch,
    )
    result = provider.update_with_camera_views(
        capture, set_view, [], allow_marker_depth_reobserve=True,
        prioritize=lambda _reason, declared: [*declared, *alt],
    )
    assert result == initial and changes == [alt[0][0], alt[1][0]] and len(captured) == 3
    assert provider.records[0]["observation_id"] == captured[2].observation_id
    assert [x["reason"] for x in provider.camera_reobservation_rejections] == [_NONPLANAR] * 2
    assert [x["checksum_sha256"] for x in provider.camera_reobservation_rejections] == [
        frame.checksum_sha256 for frame in captured[:2]
    ]


@pytest.mark.parametrize("skill,marker,policy", [
    ("MOVE_TO_REGION", "fixture", True), ("PLACE", None, True), ("PLACE", "fixture", 1),
])
def test_nonplanarity_policy_requires_explicit_bool_registered_place(
    monkeypatch, skill, marker, policy,
):
    provider, _, _, alt, _, captured, capture, set_view = _place_reobserve_fixture(monkeypatch)
    provider.skill = skill
    provider.marker_family_id = marker
    with pytest.raises(ValueError, match="nonplanarity reobservation"):
        provider.update_with_camera_views(
            capture, set_view, alt, allow_marker_depth_reobserve=policy,
        )
    assert captured == []


@pytest.mark.parametrize("scenario", ["persistent", "none", "same_view", "repeat_id"])
def test_place_reobservation_rejects_bad_or_repeated_frames_without_state_commit(
    monkeypatch, scenario,
):
    provider, ref, _, alt, changes, captured, capture, set_view = _place_reobserve_fixture(
        monkeypatch, fail_all=True,
    )
    previous_marker = provider.last_accepted_marker
    previous_target = provider._last_target.copy()
    selected = alt if scenario != "none" else []
    def apply_view(*args):
        if scenario != "same_view":
            set_view(*args)

    def acquire(attempt):
        if attempt > 0 and scenario == "repeat_id":
            return captured[0]
        return capture(attempt)

    message = {
        "persistent": _NONPLANAR, "none": _NONPLANAR,
        "same_view": "did not capture the requested distinct camera",
        "repeat_id": "repeated rejected camera observation",
    }
    with pytest.raises(ValueError, match=message[scenario]):
        provider.update_with_camera_views(
            acquire, apply_view, [], allow_marker_depth_reobserve=True,
            prioritize=lambda *_: selected,
        )
    assert provider.last_observation is ref and provider.last_accepted_marker is previous_marker
    np.testing.assert_array_equal(provider._last_target, previous_target)
    assert provider.records == []
    if scenario == "persistent":
        assert len(changes) == 2 and len(captured) == 3
        assert len(provider.camera_reobservation_rejections) == 3
    if scenario == "none":
        assert changes == [] and len(captured) == 1


@pytest.mark.parametrize("fault,match", [
    ("episode", "episode_id changed"),
    ("source", "source changed"),
    ("calibration", "camera pose and calibration version disagree"),
    ("stale", "frame not fresh"),
    ("orientation", "object is not upright"),
    ("invalid_depth", "marker_metric_depth_unavailable"),
    ("unsupported_region", "region_current_color_depth_invalid"),
])
def test_place_reobservation_keeps_fresh_measurement_hard_errors_fatal(monkeypatch, fault, match):
    provider, ref, _, alt, changes, captured, acquire, set_view = _place_reobserve_fixture(
        monkeypatch,
    )
    validate_and_update = provider.update

    def acquire_fault(attempt):
        observation = acquire(attempt)
        if attempt == 1:
            edits = {
                "episode": {"episode_id": "other"},
                "source": {"source": "rgbd_camera"},
                "calibration": {"calibration_version": ref.calibration_version},
                "stale": {"captured_at": datetime.now(UTC) - timedelta(seconds=1)},
            }
            if fault in edits:
                return revised(observation, **edits[fault])
        return observation

    def update(observation):
        if observation.camera_to_world[3] and fault in {
            "orientation", "invalid_depth", "unsupported_region",
        }:
            raise ValueError({
                "orientation": "servo registered object is not upright",
                "invalid_depth": (
                    "servo registered marker rejected: marker_metric_depth_unavailable"
                ),
                "unsupported_region": (
                    "servo region geometry unavailable: region_current_color_depth_invalid"
                ),
            }[fault])
        return validate_and_update(observation)

    monkeypatch.setattr(provider, "update", update)
    with pytest.raises(ValueError, match=match):
        provider.update_with_camera_views(
            acquire_fault, set_view, [], allow_marker_depth_reobserve=True,
            prioritize=lambda *_: alt,
        )
    assert changes == [alt[0][0]] and len(captured) == 2
    assert provider.last_observation is ref and provider.records == []


@pytest.mark.parametrize("outcome", ["valid_region", "invalid_region", "advanced_physics"])
def test_retreat_clearance_recovery_checks_current_region_before_commit(monkeypatch, outcome):
    from cloud_edge_robot_arm.vision import servo

    provider, reference, initial, alt, moves, _, capture, set_view = _place_reobserve_fixture(
        monkeypatch,
    )
    provider.skill = "RETREAT"
    monkeypatch.setattr(provider, "update", servo.OpenCVServoFeedback.update.__get__(provider))
    checked = []

    def acquire(attempt):
        frame = capture(attempt)
        if attempt and outcome == "advanced_physics":
            return revised(frame, sim_time_s=frame.sim_time_s + 0.01)
        return frame

    def marker(frame):
        if frame.camera_to_world[3] == reference.camera_to_world[3]:
            raise ValueError(_NONPLANAR)
        return np.array([2.0, 2.0, 2.0]), "CURRENT_REGISTERED_MARKER_DEVELOPMENT_ESTIMATE"

    def region(frame, _tracker):
        checked.append(frame.observation_id)
        if outcome == "invalid_region":
            return None, "region_current_corner_anchors_insufficient"
        return {"source": "CURRENT_OPENCV_RGBD", "center": [0, 0, 0],
                "observed_corner_anchors": 4}, None

    monkeypatch.setattr(provider, "_measure_target", marker)
    monkeypatch.setattr(servo, "measure_servo_region", region)

    def run():
        return provider.update_with_camera_views(
            acquire, set_view, [], allow_marker_depth_reobserve=True, prioritize=lambda *_: alt,
        )

    if outcome == "valid_region":
        assert run() == initial
        assert provider.records[0]["region_support"]["observed_corner_anchors"] == 4
        assert checked == [provider.last_observation.observation_id]
    else:
        message = "current region" if outcome == "invalid_region" else "physics time advanced"
        with pytest.raises(ValueError, match=message):
            run()
        assert provider.last_observation is reference and provider.records == []
        assert len(checked) == int(outcome == "invalid_region")
    assert moves == [alt[0][0]]


def test_default_retreat_nonplanarity_stops_before_any_camera_change(monkeypatch):
    provider, reference, _, alt, moves, captured, capture, set_view = _place_reobserve_fixture(
        monkeypatch,
    )
    provider.skill = "RETREAT"
    with pytest.raises(ValueError, match=_NONPLANAR):
        provider.update_with_camera_views(capture, set_view, alt)
    assert len(captured) == 1 and moves == [] and provider.last_observation is reference


@pytest.mark.parametrize("first_error", [
    "servo registered marker geometry unavailable",
    "servo region geometry unavailable: region_current_corner_anchors_insufficient",
    "servo region geometry unavailable: region_missing_color_not_explained_by_foreground",
    "servo region geometry unavailable: region_color_boundary_depth_unresolved",
])
@pytest.mark.parametrize("corrupt_second", [False, True])
def test_second_nonplanarity_does_not_reset_time_identity_or_attempt_budget(
    monkeypatch, first_error, corrupt_second,
):
    provider, reference, _, alt, changes, captured, acquire, set_view = _place_reobserve_fixture(
        monkeypatch,
    )
    inspected = []

    def update(frame):
        inspected.append(frame.observation_id)
        raise ValueError(first_error if len(inspected) == 1 else _NONPLANAR)

    def capture(attempt):
        frame = acquire(attempt)
        if corrupt_second and attempt == 2:
            return revised(frame, sim_time_s=frame.sim_time_s + 1 / 240)
        return frame

    monkeypatch.setattr(provider, "update", update)
    with pytest.raises(ValueError, match="physics time advanced" if corrupt_second else _NONPLANAR):
        provider.update_with_camera_views(
            capture, set_view, alt, allow_marker_depth_reobserve=True,
            prioritize=lambda reason, ordered: alt if reason == _NONPLANAR else ordered,
        )
    assert changes == [alt[0][0], alt[1][0]] and len(captured) == 3
    assert len(inspected) == (2 if corrupt_second else 3)
    assert provider.last_observation is reference and provider.records == []


def test_explicit_mujoco_source_requires_matching_calibration_before_reference_commit():
    import hashlib
    import struct

    from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback

    ref, tracked, evidence, initial = acquisition()
    kwargs = {"skill": "APPROACH", "initial_target": initial}
    OpenCVServoFeedback(ref, tracked, evidence, **kwargs)
    with pytest.raises(ValueError, match="MuJoCo calibration does not match"):
        OpenCVServoFeedback(ref, tracked, evidence, **kwargs, verify_mujoco_calibration=True)
    with pytest.raises(ValueError, match="explicitly boolean"):
        OpenCVServoFeedback(ref, tracked, evidence, **kwargs, verify_mujoco_calibration=1)
    valid = revised(ref, calibration_version=hashlib.sha256(struct.pack(
        "<20d", *ref.intrinsics, *ref.camera_to_world,
    )).hexdigest()[:16])
    session = OpenCVServoFeedback(valid, tracker(valid), evidence, **kwargs,
                                  verify_mujoco_calibration=True)
    bad_source = revised(current(valid), source="rgbd_camera",
                         calibration_version=valid.calibration_version)
    with pytest.raises(ValueError, match="source changed"):
        session.update(bad_source)
    assert session.last_observation is valid
