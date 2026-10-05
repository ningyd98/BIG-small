"""Read-only, per-mj_step evidence for the independent T5 evaluator."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    MuJoCoPhysicsBackend,
    PhysicsStepObservation,
)


@pytest.fixture
def backend() -> MuJoCoPhysicsBackend:
    physical = MuJoCoPhysicsBackend()
    physical.initialize(SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"))
    physical.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=41))
    try:
        yield physical
    finally:
        physical.shutdown()


def test_observer_receives_each_step_after_clock_and_contacts_update(
    backend: MuJoCoPhysicsBackend,
) -> None:
    observed: list[PhysicsStepObservation] = []

    def record(snapshot: PhysicsStepObservation) -> None:
        observed.append(snapshot)
        assert snapshot.physics_step == backend.total_physics_steps
        assert snapshot.sim_time_s == backend.get_sim_time()
        current_pairs = tuple((contact.geom1, contact.geom2) for contact in backend.get_contacts())
        assert snapshot.contact_pairs == current_pairs

    with backend.observe_physics_steps(record):
        result = backend.step(steps=7)

    assert result.physics_steps == 7
    assert [snapshot.physics_step for snapshot in observed] == list(range(1, 8))
    assert all(
        later.sim_time_s > earlier.sim_time_s
        for earlier, later in zip(observed, observed[1:], strict=False)
    )
    assert all(
        {"table", "object_geom"} in [set(pair) for pair in snapshot.contact_pairs]
        for snapshot in observed
    )


def test_step_zero_snapshot_has_detached_immutable_physics_values(
    backend: MuJoCoPhysicsBackend,
) -> None:
    initial = backend.current_physics_observation()

    assert initial.physics_step == 0
    assert initial.sim_time_s == 0.0
    assert initial.episode_id
    assert initial.object_position_m == pytest.approx((0.45, 0.0, 0.035))
    assert initial.object_half_extent_m == pytest.approx((0.035, 0.035, 0.035))
    assert initial.region_center_m[:2] == pytest.approx((0.20, 0.25))
    assert initial.region_half_extent_m[:2] == pytest.approx((0.08, 0.08))
    assert initial.table_top_m == pytest.approx(0.0)
    assert initial.gripper_open
    assert len(initial.joint_positions_rad) == len(initial.joint_ranges_rad) == 7
    assert len(initial.object_geom_rotation_row_major) == 9
    with pytest.raises(FrozenInstanceError):
        initial.physics_step = 99
    with pytest.raises(TypeError):
        initial.object_position_m[0] = 99.0


def test_snapshot_records_only_nonadjacent_arm_geom_distances(
    backend: MuJoCoPhysicsBackend,
) -> None:
    snapshot = backend.current_physics_observation()
    distances = {(a, b): distance for a, b, distance in snapshot.self_collision_distances_m}

    assert len(distances) == 33
    assert distances[("link4", "link6")] == pytest.approx(0.045)
    assert distances[("link5", "hand")] == pytest.approx(0.042)
    assert ("link4", "link5") not in distances
    assert distances[("link5", "left_finger_geom")] > 0.11
    assert distances[("link5", "right_finger_geom")] > 0.11
    assert ("link6", "left_finger_geom") not in distances
    assert ("hand", "right_finger_geom") not in distances
    assert ("left_finger_geom", "right_finger_geom") not in distances


def test_callback_exception_and_reset_do_not_leak_observer(
    backend: MuJoCoPhysicsBackend,
) -> None:
    calls: list[int] = []

    def fail_on_second(snapshot: PhysicsStepObservation) -> None:
        calls.append(snapshot.physics_step)
        if len(calls) == 2:
            raise RuntimeError("observer failed")

    with pytest.raises(RuntimeError, match="observer failed"):
        with backend.observe_physics_steps(fail_on_second):
            backend.step(steps=5)
    assert calls == [1, 2]
    backend.step(steps=1)
    assert calls == [1, 2]

    with backend.observe_physics_steps(lambda snapshot: calls.append(snapshot.physics_step)):
        backend.step(steps=2)
        before_reset = len(calls)
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=42))
        backend.step(steps=2)
        assert len(calls) == before_reset
    assert backend.current_physics_observation().physics_step == 2


def test_shutdown_and_reinitialize_clear_observer(
    backend: MuJoCoPhysicsBackend,
) -> None:
    observed: list[int] = []
    with backend.observe_physics_steps(lambda snapshot: observed.append(snapshot.physics_step)):
        backend.step()
        backend.shutdown()
        backend.initialize(SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=43))
        backend.step()
    assert observed == [1]


def test_observer_cannot_reenter_backend_actions(backend: MuJoCoPhysicsBackend) -> None:
    def attempt_mutation(_snapshot: PhysicsStepObservation) -> None:
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.step(steps=1)
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.apply_joint_targets(JointCommand(positions=[0.0] * 7))
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=44))
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.emergency_stop()

    with backend.observe_physics_steps(attempt_mutation):
        backend.step(steps=1)
    assert backend.total_physics_steps == 1


def test_only_one_observer_can_be_active(backend: MuJoCoPhysicsBackend) -> None:
    with backend.observe_physics_steps(lambda _snapshot: None):
        with pytest.raises(RuntimeError, match="already active"):
            with backend.observe_physics_steps(lambda _snapshot: None):
                pass


def test_default_batch_step_keeps_single_contact_scan(
    backend: MuJoCoPhysicsBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = backend._read_contacts
    calls = 0

    def counted():
        nonlocal calls
        calls += 1
        return original()

    def unexpected_snapshot(_contacts: object) -> None:
        raise AssertionError("default step must not build evaluator snapshots")

    monkeypatch.setattr(backend, "_read_contacts", counted)
    monkeypatch.setattr(backend, "_build_physics_observation", unexpected_snapshot)
    backend.step(steps=7)
    assert calls == 1
