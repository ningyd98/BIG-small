"""SOFTWARE_ONLY original graphs from real recorder callbacks and byte spooling.

No MuJoCo initialization, physics, renderer or collection certificate is created.
The local camera substitutes pixels only; reader validation stays intact.
"""

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

from cloud_edge_robot_arm.research.native_calibration_collection import (
    canonical,
    detached,
    digest,
    load_json,
)
from cloud_edge_robot_arm.research.native_collection_application import _collection_guard
from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalScenarioConfig,
    SensorFrame,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from tests.test_native_collection_authority import source_recorder


def install_original_shape_camera(backend, geometry):
    """Match producer sentinel/labels and two/three-pass output shapes locally."""
    camera = geometry["camera"]
    counter = 0

    def render(data, *, include_instances=True, **_kwargs):
        nonlocal counter
        counter += 1
        count = camera["width"] * camera["height"]
        frame = SensorFrame(
            frame_id=f"software-original-{counter}",
            sim_time_s=backend.get_sim_time(),
            width=camera["width"],
            height=camera["height"],
            rgb=bytes([100, 120, 150]) * count,
            depth=(0.5,) * count,
            intrinsics=tuple(camera["intrinsics"]),
            camera_to_world=tuple(camera["camera_to_world"]),
            captured_at=datetime.now(UTC),
            episode_id=backend._episode_id,
            scene_id="SOFTWARE_ONLY",
            calibration_version=camera["calibration_version"],
            valid_mask=bytes([1]) * count,
        )
        state_hash = MuJoCoRGBDCamera._physics_state_hash(data)
        ids = (-1, 7) * (count // 2) if include_instances else ()
        labels = {7: "software_geometry"} if include_instances else {}
        return frame, ids, labels, (state_hash,) * (3 if include_instances else 2)

    backend._camera = SimpleNamespace(
        capture_with_instances=render, _capture=render, close=lambda: None
    )


def install_software_reset_engine(backend):
    """Substitute engine/model storage only; retain the real RESET wrapper and body."""
    joints = {"joint1": 0, "finger_left_joint": 7, "finger_right_joint": 8}
    backend._model.joint = lambda name: SimpleNamespace(id=joints[name], qposadr=[joints[name]])
    backend._model.jnt_qposadr = list(range(9))

    def reset_data(_model, data):
        data.time = 0.0
        for name in ("qpos", "qvel", "act", "ctrl"):
            getattr(data, name)[:] = 0

    backend._mujoco.mj_resetData = reset_data
    backend._mujoco.mj_forward = lambda *_args: None
    backend._set_free_body_pose = lambda *_args: None
    backend._set_body_mass = lambda *_args: None
    backend._set_geom_friction = lambda *_args: None
    backend._update_sensor_frame = MuJoCoPhysicsBackend._update_sensor_frame.__get__(backend)


def recorded_frame_graph(root):
    """Freeze producer-shaped originals at S=0; missing reset/full H stays incomplete."""
    recorder, backend, capture, owner, _ = source_recorder(root)
    geometry = geometry_registration()
    install_original_shape_camera(backend, geometry)
    try:
        with capture, recorder:
            recorder._write_original(
                "software-state.json",
                dict(
                    evidence_scope="SOFTWARE_ONLY",
                    state=detached(backend.current_physics_observation()),
                ),
            )
            recorder.capture()
            backend._capture_cached_observed()
            assert not recorder.failures and not backend.operation_observer_failures
            recorder.freeze()
    finally:
        owner.close()
    protocol = dict(
        geometry=geometry,
        settings=dict(raw_bytes=2**30),
        source_hashes=dict(recorder.source_hashes),
    )
    return protocol, recorder.allocated_acquisition_ids


def frame_audit(root, protocol):
    audit = _Audit(protocol, {}, root)
    audit.inventory()
    audit.intervals = {row["interval_id"]: row for row in audit.raw["intervals"]}
    state = audit.read("software-state.json")
    assert state["evidence_scope"] == "SOFTWARE_ONLY"
    audit.states = {0: state["state"]}
    return audit


def write_software_json(path, value):
    """Mutations are confined to copied test graphs, never research originals."""
    path.write_bytes(canonical(value) + b"\n")


def reseal_software_inventory(directory):
    manifest = load_json(directory / "inventory.json")
    for name in manifest["files"]:
        raw = (directory / name).read_bytes()
        manifest["files"][name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest["original_bytes"] = sum(row["bytes"] for row in manifest["files"].values())
    manifest["inventory_sha256"] = digest(manifest["files"])
    write_software_json(directory / "inventory.json", manifest)


def recorded_effect_graph(root):
    """Short real dispatch/guard graph; only engine and camera are SOFTWARE_ONLY."""
    recorder, backend, capture, owner, _ = source_recorder(root)
    geometry = geometry_registration()
    install_original_shape_camera(backend, geometry)
    install_software_reset_engine(backend)
    backend._episode_id = None
    backend._actuator_delay_steps = 2
    origin = owner.begin_event("SOFTWARE_ONLY")
    owner.mark_event(origin)
    started = owner.end_event(origin)
    checks = []
    lease_id = "SOFTWARE_ONLY-lease"
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})

    def guard(checkpoint):
        checks.append(
            dict(
                checkpoint=detached(checkpoint),
                step=backend.total_physics_steps,
                current=detached(owner.read_current(after=origin)),
                lease_id=lease_id,
            )
        )

    try:
        with capture, recorder:
            backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
            recorder.require_clean_reset()
            with _collection_guard(live, guard, 1024):
                with backend.capture_each_physics_step(max_captures=16):
                    with recorder.purpose("SETTLE"):
                        backend.apply_joint_targets(JointCommand(positions=[4.0] * 7))
                        backend.apply_gripper_command(GripperCommand(open=False))
                        backend.step(3)
                        backend.apply_joint_targets(JointCommand(positions=[0.4] * 7))
                    with recorder.purpose("HOLD"):
                        backend.hold_current_joints()
                    with recorder.purpose("SETTLE"):
                        backend.step(3)
                        recorder.capture()
                        backend.step(1)
            assert not recorder.failures and not recorder._audit_failures
            assert not backend.operation_observer_failures and not live.failures
            recorder._write_original("active-checks.json", checks)
            recorder._write_original(
                "software-effect-context.json",
                dict(
                    evidence_scope="SOFTWARE_ONLY",
                    domain=detached(owner.domain),
                    deadline=started.lower_ns + 100 * 10**9,
                    lease_id=lease_id,
                ),
            )
            recorder.freeze()
    finally:
        owner.close()
    return dict(
        geometry=geometry,
        settings=dict(raw_bytes=2**30),
        source_hashes=dict(recorder.source_hashes),
    )


def effect_audit(root, protocol):
    audit = _Audit(protocol, {}, root)
    audit.inventory()
    audit.physics()
    context = audit.read("software-effect-context.json")
    assert context["evidence_scope"] == "SOFTWARE_ONLY"
    audit.domain, audit.deadline = context["domain"], context["deadline"]
    audit.identity = SimpleNamespace(owner_identity=SimpleNamespace(lease_id=context["lease_id"]))
    audit.operations()
    return audit
