"""Software workflow seams exercise PRE/POST context wiring without native effects."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from tests.test_native_registered_teacher_release import CONFIG as V9_CONFIG
from tests.test_native_registered_teacher_release import V10_CONFIG
from tests.test_native_single_teacher_release import CONFIG, SCHEMA, application
from tests.test_visual_owner_registration import values


@pytest.mark.parametrize(
    "config,schema,expected_counts",
    [
        (CONFIG, SCHEMA, (120, 2041)),
        (V9_CONFIG, "native.calibration.operational.v9", (120, 2041)),
        (V10_CONFIG, "native.calibration.operational.v10", (0, 1921)),
    ],
)
def test_worker_passes_protocol_settings_and_refreshes_post_physics_step(
    tmp_path,
    monkeypatch,
    config,
    schema,
    expected_counts,
):
    from cloud_edge_robot_arm.edge.runtime import skill_executor
    from cloud_edge_robot_arm.research import native_collection_application as module
    from cloud_edge_robot_arm.research import native_collection_grounding as grounding_module
    from cloud_edge_robot_arm.research import native_full_horizon_recorder as recorder_module
    from cloud_edge_robot_arm.simulation.mujoco import backend, native_horizon, skill_robot
    from cloud_edge_robot_arm.vision import capture, top_grasp

    app = application(tmp_path, config=config)
    fixture = values()
    original = fixture["original"]
    observation = fixture["online"].observation
    state = fixture["online"].robot_state
    settings_seen = []
    contexts = []

    class Backend:
        def __init__(self):
            self.total_physics_steps = 0
            self.execution_guard_events = []
            self._model = object()

        def initialize(self, config):
            self._config = config

        def reset(self, scenario):
            pass

        def step(self, steps):
            self.total_physics_steps += steps

        def capture_each_physics_step(self, **kwargs):
            return nullcontext()

        def get_joint_state(self):
            return SimpleNamespace(velocities=[0.0] * 7)

        def shutdown(self):
            pass

    class Capture:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Recorder(Capture):
        bytes_written = 0
        render_accounting = {"exact_passes": 0, "known_completed_passes": 0, "status": "EXACT"}
        last_captured_frame = SimpleNamespace(observation=observation)

        def require_clean_reset(self):
            pass

        def purpose(self, purpose):
            return nullcontext()

        def capture(self):
            return observation

        def acquisition_source(self):
            return {"acquisition_id": "software-frame"}

        def bind_collection_source(self, source):
            pass

        def _write_original(self, *args):
            pass

        def record_shield_config(self, shield):
            pass

        def check_shield(self, shield, context, *, index, phase):
            contexts.append((phase, context))
            if phase == "POST":
                raise RuntimeError("software POST context recorded")
            return SimpleNamespace(allowed=True), {}

        def record_failure(self, *args):
            pass

        def freeze(self):
            pass

    def build(**kwargs):
        settings_seen.append(kwargs.get("protocol_settings"))
        return original

    def execute(**kwargs):
        live = module._live(app)
        dispatch = live.backend.total_physics_steps
        live.backend.step(1921)
        return SimpleNamespace(
            dispatch_step=dispatch,
            terminal_step=live.backend.total_physics_steps,
        )

    step = original.contract.steps[0]
    monkeypatch.setattr(backend, "MuJoCoPhysicsBackend", Backend)
    monkeypatch.setattr(
        skill_robot, "MuJoCoSkillRobot", lambda value: SimpleNamespace(get_state=lambda: state)
    )
    monkeypatch.setattr(skill_executor, "SkillExecutor", lambda **kwargs: object())
    monkeypatch.setattr(capture, "MuJoCoCaptureSession", Capture)
    monkeypatch.setattr(recorder_module, "NativeFullHorizonRecorder", Recorder)
    monkeypatch.setattr(top_grasp, "matches_calibrated_gripper", lambda *args: True)
    monkeypatch.setattr(module, "_collection_guard", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(module, "_record_bootstrap_tracker", lambda *args, **kwargs: (object(), {}))
    monkeypatch.setattr(module, "build_collection_contract", build)
    monkeypatch.setattr(grounding_module, "build_collection_contract_v2", build)
    monkeypatch.setattr(
        grounding_module,
        "bootstrap_registered_collection_tracker_v2",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        module,
        "_handoff_registered_capture",
        lambda live, observation, *args, **kwargs: observation,
    )
    monkeypatch.setattr(
        native_horizon, "_issue_collection_session", lambda *args: SimpleNamespace(execute=execute)
    )
    monkeypatch.setattr(
        module,
        "_collect_grounded_step",
        lambda *args, **kwargs: (original.contract, step, None, None, None),
    )
    monkeypatch.setattr(
        module.NativeCollectionApplication,
        "_evaluate_collection_admission",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(RuntimeError, match="software POST context recorded"):
        app.execute_once()

    timeout_basis = "physics_steps" if config == V10_CONFIG else None
    assert settings_seen == [{"timeout_basis": timeout_basis, "schema_version": schema}]
    assert [(phase, ctx.physics_step) for phase, ctx in contexts] == [
        ("PRE", expected_counts[0]),
        ("POST", expected_counts[1]),
    ]
